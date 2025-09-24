import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET ENKEL TEAMS RECHTEN
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - ALLEEN TEAMS RECHTEN NODIG
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# ✅ CORRECTE URL VOOR UAT
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# Jouw IDs (pas aan op basis van /id-mapper)
HALO_CLIENT_ID_NUM = 1706  # Bossers & Cnossen (API ID)
HALO_SITE_ID       = 1714  # Main (API ID)

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - MET ENKEL TEAMS RECHTEN
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
    """HAAL MAIN-SITE GEBRUIKERS OP MET ENKEL TEAMS RECHTEN"""
    log.info(f"🔍 Start proces voor client {HALO_CLIENT_ID_NUM}, site {HALO_SITE_ID}")
    
    try:
        # Haal ALLE gebruikers op (geen externe endpoints nodig)
        users_url = f"{HALO_API_BASE}/Users"
        log.info(f"➡️ API-aanvraag: {users_url}")
        
        headers = get_halo_headers()
        r = requests.get(users_url, headers=headers, timeout=30)
        r.raise_for_status()
        
        # Parse response
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or data.get("Users", [])
        log.info(f"✅ {len(users)} gebruikers opgehaald - start filtering")
        
        # Filter met DE ECHTE IDs (1706 en 1714)
        main_users = []
        for u in users:
            # Haal IDs op (alle varianten)
            site_id_val = str(
                u.get("siteid") or 
                u.get("site_id") or 
                ""
            ).strip()
            
            client_id_val = str(
                u.get("clientid") or 
                u.get("client_id") or 
                ""
            ).strip()
            
            # Valideer met DE ECHTE IDs
            if site_id_val == str(HALO_SITE_ID) and client_id_val == str(HALO_CLIENT_ID_NUM):
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
# Routes - MET ENKEL TEAMS RECHTEN
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_notes": [
            "1. Werkt MET ENKEL 'Teams' rechten (geen Clients/Sites nodig)",
            "2. Gebruikt API IDs (1706/1714) i.p.v. URL IDs (12/18)",
            "3. Bezoek /id-helper voor hulp bij ID mapping"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    site_users = fetch_main_users()
    
    if not site_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                f"1. Gebruik DE ECHTE IDs: client_id={HALO_CLIENT_ID_NUM}, site_id={HALO_SITE_ID}",
                "2. Bezoek /id-helper om jouw juiste IDs te vinden",
                "3. Zorg dat 'Teams' is aangevinkt in API-toegang"
            ],
            "debug_info": "Deze app gebruikt alleen de /Users endpoint (geen Clients/Sites nodig)"
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
    """HULP BIJ ID MAPPING MET ALLEEN /Users ENDPOINT"""
    try:
        headers = get_halo_headers()
        r = requests.get(f"{HALO_API_BASE}/Users", headers=headers, timeout=30)
        r.raise_for_status()
        
        # Parse response
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or []
        
        if not users:
            return {"error": "Geen gebruikers gevonden in API response"}, 500
        
        # Verzamel unieke client/site IDs
        client_ids = {}
        site_ids = {}
        
        for u in users:
            # Client IDs
            client_id_val = str(
                u.get("clientid") or 
                u.get("client_id") or 
                ""
            ).strip()
            if client_id_val:
                client_ids[client_id_val] = client_ids.get(client_id_val, 0) + 1
            
            # Site IDs
            site_id_val = str(
                u.get("siteid") or 
                u.get("site_id") or 
                ""
            ).strip()
            if site_id_val:
                site_ids[site_id_val] = site_ids.get(site_id_val, 0) + 1
        
        return {
            "status": "success",
            "client_ids": [
                {"api_id": cid, "count": count}
                for cid, count in client_ids.items()
            ],
            "site_ids": [
                {"api_id": sid, "count": count}
                for sid, count in site_ids.items()
            ],
            "note": "Gebruik deze IDs in je code (NIET de URL IDs!)",
            "example": {
                "url_example": "https://bncuat.halopsa.com/customer?clientid=12&siteid=18",
                "api_example": "Gebruik client_id=1706, site_id=1714 in je code"
            }
        }
    
    except Exception as e:
        return {"error": str(e)}, 500

# ------------------------------------------------------------------------------
# App Start - MET ENKEL TEAMS RECHTEN
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - MET ENKEL 'Teams' RECHTEN")
    log.info("-"*70)
    log.info("✅ Werkt MET ENKEL 'Teams' aangevinkt (geen Clients/Sites nodig!)")
    log.info("✅ Gebruikt API IDs (1706/1714) i.p.v. URL IDs (12/18)")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN:")
    log.info("1. Bezoek EERST /id-helper")
    log.info("2. Noteer de API IDs voor jouw klant/site")
    log.info("3. Pas HALO_CLIENT_ID_NUM en HALO_SITE_ID aan in de code")
    log.info("4. Bezoek DAN /users")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
