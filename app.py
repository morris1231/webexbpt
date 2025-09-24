import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET JUISTE ID VALIDATIE
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - MET DE GEVONDEN ECHTE IDs
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# ✅ CORRECTE URL VOOR UAT
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# 🔑 DE ECHTE IDs ZOALS GEVONDEN IN DE API (NIET DE URL IDS!)
HALO_CLIENT_ID_NUM = 1706  # ✅ ECHTE client ID (Bossers & Cnossen)
HALO_SITE_ID       = 1714  # ✅ ECHTE site ID (Main)

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - MET EXPLICIETE ID VALIDATIE
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Authenticatie met UAT-specifieke instellingen"""
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
    """HAAL MAIN-SITE GEBRUIKERS OP MET DE ECHTE IDs"""
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
# Routes - MET ID VALIDATIE
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_info": [
            f"1. Gebruikt ECHTE client ID: {HALO_CLIENT_ID_NUM} (Bossers & Cnossen)",
            f"2. Gebruikt ECHTE site ID: {HALO_SITE_ID} (Main)",
            "3. Deze IDs komen UIT DE API - niet uit de URL!"
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
                "2. Bezoek /id-mapper om de juiste IDs te vinden",
                "3. Zorg dat 'Teams' is aangevinkt in API-toegang"
            ],
            "debug_info": "Deze app gebruikt de IDs zoals gevonden in de API response"
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
    """Toon de KOPPELING tussen URL-IDS en API-IDS"""
    try:
        headers = get_halo_headers()
        
        # Haal alle clients op
        clients_url = f"{HALO_API_BASE}/Clients"
        r_clients = requests.get(clients_url, headers=headers, timeout=15)
        
        # Haal alle sites op
        sites_url = f"{HALO_API_BASE}/Sites"
        r_sites = requests.get(sites_url, headers=headers, timeout=15)
        
        if r_clients.status_code != 200 or r_sites.status_code != 200:
            return {
                "error": "Kan clients/sites niet ophalen",
                "solution": [
                    "1. Zorg dat 'Teams' is aangevinkt in API-toegang",
                    "2. Gebruik scope 'all'"
                ]
            }, 500
        
        # Parse responses
        clients = r_clients.json() if isinstance(r_clients.json(), list) else r_clients.json().get("clients", [])
        sites = r_sites.json() if isinstance(r_sites.json(), list) else r_sites.json().get("sites", [])
        
        # Maak koppeling
        client_mapping = {}
        for c in clients:
            url_id = str(c.get("external_id", ""))  # Dit is de ID uit de URL
            api_id = str(c.get("id", ""))
            name = c.get("name", "Onbekend")
            if url_id and api_id:
                client_mapping[url_id] = {
                    "api_id": api_id,
                    "name": name
                }
        
        site_mapping = {}
        for s in sites:
            url_id = str(s.get("external_id", ""))
            api_id = str(s.get("id", ""))
            name = s.get("name", "Onbekend")
            client_id = str(s.get("client_id", ""))
            if url_id and api_id:
                site_mapping[url_id] = {
                    "api_id": api_id,
                    "name": name,
                    "client_id": client_id
                }
        
        return {
            "status": "success",
            "client_mapping": client_mapping,
            "site_mapping": site_mapping,
            "note": "Gebruik deze mapping om URL-IDs te vertalen naar API-IDs"
        }
    
    except Exception as e:
        return {"error": str(e)}, 500

# ------------------------------------------------------------------------------
# App Start - MET ID VALIDATIE
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - MET ECHTE API IDs")
    log.info("-"*70)
    log.info(f"✅ Gebruikt ECHTE client ID: {HALO_CLIENT_ID_NUM} (Bossers & Cnossen)")
    log.info(f"✅ Gebruikt ECHTE site ID: {HALO_SITE_ID} (Main)")
    log.info("-"*70)
    log.info("💡 BELANGRIJK:")
    log.info("1. Deze IDs KOMEN UIT DE API - niet uit de URL")
    log.info("2. Bezoek /id-mapper om de koppeling te zien")
    log.info("3. Gebruik deze waarden in je code:")
    log.info(f"   HALO_CLIENT_ID_NUM = {HALO_CLIENT_ID_NUM}")
    log.info(f"   HALO_SITE_ID = {HALO_SITE_ID}")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
