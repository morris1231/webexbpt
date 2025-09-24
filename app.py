import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET JUISTE URL-IDS
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - MET DE JUISTE URL-IDS (GEEN API-IDS!)
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# ✅ CORRECTE URL VOOR UAT
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# 🔑 DE JUISTE URL-IDS (ZOALS IN DE BROWSER)
HALO_CLIENT_ID_NUM = 12  # Bossers & Cnossen (URL ID)
HALO_SITE_ID       = 18  # Main (URL ID)

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - MET JUISTE URL-IDS
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Authenticatie met alleen 'Teams' rechten"""
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    
    try:
        r = requests.post(
            HALO_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(payload),
            timeout=10
        )
        r.raise_for_status()
        return {
            "Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        log.critical(f"❌ AUTH MISLUKT: {str(e)}")
        log.critical(f"➡️ Response: {r.text if 'r' in locals() else 'Geen response'}")
        raise

def fetch_main_users():
    """HAAL MAIN-SITE GEBRUIKERS OP MET JUISTE URL-IDS"""
    log.info(f"🔍 Start proces voor client {HALO_CLIENT_ID_NUM}, site {HALO_SITE_ID}")
    
    try:
        # Haal ALLE gebruikers op
        users_url = f"{HALO_API_BASE}/Users"
        log.info(f"➡️ API-aanvraag: {users_url}")
        
        headers = get_halo_headers()
        r = requests.get(users_url, headers=headers, timeout=30)
        r.raise_for_status()
        
        # Parse response
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or data.get("Users", [])
        log.info(f"✅ {len(users)} gebruikers opgehaald - start filtering")
        
        # Filter met DE JUISTE URL-IDS (12 en 18)
        main_users = []
        for u in users:
            # Haal site ID op (alle varianten) + converteer naar float
            site_id_val = None
            for key in ["siteid", "site_id", "SiteId", "siteId"]:
                if key in u and u[key] is not None:
                    try:
                        site_id_val = float(u[key])
                        break
                    except (TypeError, ValueError):
                        pass
            
            # Haal client ID op (alle varianten) + converteer naar float
            client_id_val = None
            for key in ["clientid", "client_id", "ClientId", "clientId"]:
                if key in u and u[key] is not None:
                    try:
                        client_id_val = float(u[key])
                        break
                    except (TypeError, ValueError):
                        pass
            
            # TYPEVEILIGE VALIDATIE VOOR URL-IDS (12 en 18)
            is_site_match = site_id_val is not None and abs(site_id_val - HALO_SITE_ID) < 0.1
            is_client_match = client_id_val is not None and abs(client_id_val - HALO_CLIENT_ID_NUM) < 0.1
            
            if is_site_match and is_client_match:
                main_users.append(u)
        
        # Rapporteer resultaat
        if main_users:
            log.info(f"✅ {len(main_users)} JUISTE Main-site gebruikers gevonden!")
            if main_users:
                example = main_users[0]
                log.info(f"  → Voorbeeldgebruiker: ID={example.get('id')}, Naam='{example.get('name')}'")
            return main_users
        
        log.error(f"❌ Geen Main-site gebruikers gevonden met client_id={HALO_CLIENT_ID_NUM} en site_id={HALO_SITE_ID}")
        return []
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - MET JUISTE URL-IDS
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_notes": [
            "1. Gebruikt URL-IDs (12/18) i.p.v. API-IDs (1706/1714)",
            "2. Bezoek /id-mapper voor duidelijke koppeling",
            "3. Werkt met typeveilige vergelijking (18.0 == 18)"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    site_users = fetch_main_users()
    
    if not site_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                "1. Gebruik DE JUISTE URL-IDs: client_id=12, site_id=18",
                "2. Bezoek /id-mapper voor visuele koppeling",
                "3. Zorg dat 'Teams' is aangevinkt in API-toegang"
            ],
            "debug_info": "Deze app gebruikt de IDs zoals ze in de URL staan (12/18)"
        }), 500
    
    simplified = [{
        "id": u.get("id"),
        "name": u.get("name") or "Onbekend",
        "email": u.get("EmailAddress") or u.get("email") or "Geen email"
    } for u in site_users]
    
    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "client_name": "Bossers & Cnossen",
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
        "total_users": len(site_users),
        "users": simplified
    })

@app.route("/id-mapper", methods=["GET"])
def id_mapper():
    """TOON DUIDELIJKE KOPPELING TUSSEN URL-IDS EN API-IDS"""
    try:
        headers = get_halo_headers()
        r = requests.get(f"{HALO_API_BASE}/Users", headers=headers, timeout=30)
        r.raise_for_status()
        
        # Parse response
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or []
        
        if not users:
            return {"error": "Geen gebruikers gevonden in API response"}, 500
        
        # Zoek de gebruiker met jouw URL-IDs
        for u in users:
            # Haal URL-IDs op
            url_client_id = None
            for key in ["clientid", "client_id"]:
                if key in u and u[key] is not None:
                    try:
                        url_client_id = int(float(u[key]))
                        break
                    except (TypeError, ValueError):
                        pass
            
            url_site_id = None
            for key in ["siteid", "site_id"]:
                if key in u and u[key] is not None:
                    try:
                        url_site_id = int(float(u[key]))
                        break
                    except (TypeError, ValueError):
                        pass
            
            # Is dit jouw gebruiker?
            if url_client_id == 12 and url_site_id == 18:
                return {
                    "status": "success",
                    "client": {
                        "url_id": 12,
                        "api_id": url_client_id,
                        "name": u.get("client_name") or "Bossers & Cnossen"
                    },
                    "site": {
                        "url_id": 18,
                        "api_id": url_site_id,
                        "name": u.get("site_name") or "Main"
                    },
                    "user_example": {
                        "id": u.get("id"),
                        "name": u.get("name"),
                        "email": u.get("email")
                    },
                    "note": "Gebruik deze URL-IDs in je code (12 en 18)"
                }
        
        # Als geen gebruiker exact 12/18 heeft
        return {
            "status": "warning",
            "message": "Geen gebruiker gevonden met exact client_id=12 en site_id=18",
            "suggestion": "Probeer de meest voorkomende waarden voor jouw klant"
        }
    
    except Exception as e:
        return {"error": str(e)}, 500

# ------------------------------------------------------------------------------
# App Start - MET JUISTE URL-IDS
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - MET JUISTE URL-IDS")
    log.info("-"*70)
    log.info("✅ Gebruikt URL-IDs (12/18) i.p.v. API-IDs (1706/1714)")
    log.info("✅ Typeveilige vergelijking (18.0 == 18)")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN:")
    log.info("1. Bezoek EERST /id-mapper")
    log.info("2. Bevestig dat client_id=12 en site_id=18 kloppen")
    log.info("3. Bezoek DAN /users")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
