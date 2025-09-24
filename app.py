import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET TYPEVEILIGE FILTERING
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - VOLLEDIG TYPEVEILIG
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# ✅ CORRECTE URL VOOR UAT
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# Jouw IDs (als NUMBERS, niet strings)
HALO_CLIENT_ID_NUM = 1706  # Bossers & Cnossen (API ID)
HALO_SITE_ID       = 1714  # Main (API ID)

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - MET TYPEVEILIGE FILTERING
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
    """HAAL MAIN-SITE GEBRUIKERS OP MET TYPEVEILIGE FILTERING"""
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
        log.info(f"✅ {len(users)} gebruikers opgehaald - start TYPEVEILIGE filtering")
        
        # Filter met TYPECONVERSIE (GEEN STRING VERGELIJKING!)
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
            
            # TYPEVEILIGE VALIDATIE (geen string vergelijking!)
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
        log.error("👉 Mogelijke oorzaken:")
        log.error("1. Verkeerde ID types (API gebruikt floats/ints, geen strings)")
        log.error("2. Onjuiste ID waarden (gebruik /id-helper voor correcte waarden)")
        return []
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - MET TYPEVEILIGE ID MAPPING
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_notes": [
            "1. Werkt MET TYPEVEILIGE filtering (geen string vergelijking!)",
            "2. Gebruikt numerieke vergelijking voor IDs (1714.0 == 1714)",
            "3. Bezoek /id-helper voor correcte ID waarden"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    site_users = fetch_main_users()
    
    if not site_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                "1. Bezoek /id-helper om de EXACTE ID waarden te zien",
                "2. Let op: IDs kunnen floats zijn (1714.0 i.p.v. 1714)",
                "3. Gebruik NUMERIEKE vergelijking, niet string"
            ],
            "debug_info": "Deze app gebruikt TYPEVEILIGE filtering voor IDs"
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

@app.route("/id-helper", methods=["GET"])
def id_helper():
    """HULP BIJ ID MAPPING MET TYPEINFORMATIE"""
    try:
        headers = get_halo_headers()
        r = requests.get(f"{HALO_API_BASE}/Users", headers=headers, timeout=30)
        r.raise_for_status()
        
        # Parse response
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or []
        
        if not users:
            return {"error": "Geen gebruikers gevonden in API response"}, 500
        
        # Verzamel unieke client/site IDs MET TYPE
        client_ids = {}
        site_ids = {}
        
        for u in users:
            # Client IDs
            for key in ["clientid", "client_id", "ClientId", "clientId"]:
                if key in u and u[key] is not None:
                    val = u[key]
                    try:
                        num_val = float(val)
                        client_ids[num_val] = client_ids.get(num_val, 0) + 1
                    except (TypeError, ValueError):
                        pass
            
            # Site IDs
            for key in ["siteid", "site_id", "SiteId", "siteId"]:
                if key in u and u[key] is not None:
                    val = u[key]
                    try:
                        num_val = float(val)
                        site_ids[num_val] = site_ids.get(num_val, 0) + 1
                    except (TypeError, ValueError):
                        pass
        
        # Sorteer op count (meeste gebruikers eerst)
        sorted_client_ids = sorted(
            [{"api_id": cid, "count": count} for cid, count in client_ids.items()],
            key=lambda x: x["count"],
            reverse=True
        )
        
        sorted_site_ids = sorted(
            [{"api_id": sid, "count": count} for sid, count in site_ids.items()],
            key=lambda x: x["count"],
            reverse=True
        )
        
        return {
            "status": "success",
            "client_ids": sorted_client_ids,
            "site_ids": sorted_site_ids,
            "note": "Gebruik DEZE NUMMERS in je code (niet als strings!)",
            "example": {
                "api_value": 1714.0,
                "correct_usage": "HALO_SITE_ID = 1714  # Gebruik integer, geen string"
            }
        }
    
    except Exception as e:
        return {"error": str(e)}, 500

# ------------------------------------------------------------------------------
# App Start - MET TYPEVEILIGE FILTERING
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - MET TYPEVEILIGE FILTERING")
    log.info("-"*70)
    log.info("✅ Werkt MET TYPECONVERSIE (1714.0 == 1714)")
    log.info("✅ Gebruikt numerieke vergelijking voor IDs")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN:")
    log.info("1. Bezoek EERST /id-helper")
    log.info("2. Noteer de NUMMERIEKE waarden (geen strings!)")
    log.info("3. Pas HALO_CLIENT_ID_NUM en HALO_SITE_ID aan in de code")
    log.info("4. Bezoek DAN /users")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
