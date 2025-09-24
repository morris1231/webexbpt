import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL      = os.getenv("HALO_AUTH_URL", "https://bncuat.halopsa.com/oauth2/token").strip()
HALO_API_BASE      = os.getenv("HALO_API_BASE", "https://bncuat.halopsa.com/api").strip()

# Jouw specifieke IDs
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))   # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))         # Main site

# ------------------------------------------------------------------------------
# Halo API helpers
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Vraag een bearer token op met JUISTE SCOPE (alleen 'all')"""
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
        token = r.json()["access_token"]
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        log.error(f"❌ Auth mislukt: {str(e)}")
        log.error(f"➡️ API Response: {r.text if 'r' in locals() else 'Geen response'}")
        raise

def dedupe_users(users):
    """Verwijder dubbele users op basis van ID."""
    seen, result = set(), []
    for u in users:
        uid = u.get("id")
        if uid and uid not in seen:
            seen.add(uid)
            result.append(u)
    return result

def fetch_main_users(client_id: int, site_id: int):
    """Haal ALLEEN Main-site gebruikers op via correcte hiërarchische aanpak"""
    h = get_halo_headers()
    
    # Stap 1: Haal EERST de client op om te valideren
    client_url = f"{HALO_API_BASE}/Clients/{client_id}"
    log.info(f"🔍 Valideer client: {client_url}")
    
    try:
        r = requests.get(client_url, headers=h, timeout=10)
        if r.status_code != 200:
            log.error(f"❌ Client validatie mislukt ({r.status_code}): {r.text[:200]}")
            return []
        
        client_data = r.json()
        log.info(f"✅ Client gevonden: {client_data.get('name', 'Onbekend')} (ID: {client_id})")
        
        # Stap 2: Haal de specifieke site op voor deze client
        site_url = f"{HALO_API_BASE}/Sites/{site_id}"
        log.info(f"🔍 Haal site op: {site_url}")
        
        r = requests.get(site_url, headers=h, timeout=10)
        if r.status_code != 200:
            log.error(f"❌ Site ophalen mislukt ({r.status_code}): {r.text[:200]}")
            return []
        
        site_data = r.json()
        
        # CRUCIAAL: Valideer dat de site bij de client hoort!
        if site_data.get("client_id") != client_id:
            log.error(f"❌ Site ID {site_id} behoort NIET tot client {client_id}!")
            log.error(f"➡️ Site behoort tot client ID: {site_data.get('client_id')}")
            log.error("💡 Oplossing: Controleer of je de juiste site ID gebruikt voor deze client")
            return []
        
        log.info(f"✅ Site gevalideerd: {site_data.get('name', 'Onbekend')} (ID: {site_id}) behoort tot client {client_id}")
        
        # Stap 3: Haal NU pas de gebruikers op voor deze site
        users_url = f"{HALO_API_BASE}/Sites/{site_id}/Users"
        log.info(f"🔍 Haal gebruikers op voor site: {users_url}")
        
        r = requests.get(users_url, headers=h, timeout=20)
        if r.status_code != 200:
            log.error(f"❌ Gebruikers ophalen mislukt ({r.status_code}): {r.text[:200]}")
            return []
        
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or data.get("Users", [])
        
        if not users:
            log.warning("⚠️ Geen gebruikers gevonden voor deze site")
            return []
        
        log.info(f"✅ {len(users)} Main-users gevonden voor site {site_id} (client {client_id})")
        return dedupe_users(users)
    
    except Exception as e:
        log.error(f"❌ API verbindingsfout: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Halo Main users app draait! Bezoek /users voor data"}

@app.route("/users", methods=["GET"])
def users():
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    
    if not site_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                "1. Zorg dat 'Teams' is aangevinkt in API-toegang (Instellingen → API-toegang)",
                "2. Controleer of site_id=18 daadwerkelijk bij client_id=12 hoort",
                "3. Bezoek /debug voor technische details"
            ],
            "hint": "In Halo PSA: Eerst Client, dan Site, dan Gebruikers"
        }), 500
    
    simplified = [{
        "id"   : u.get("id"),
        "name" : u.get("name") or u.get("Name") or "Onbekend",
        "email": u.get("EmailAddress") or u.get("emailaddress") or u.get("email") or "Geen email"
    } for u in site_users]
    
    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
        "client_name": "Bossers & Cnossen",  # Kan uit API gehaald worden, maar voor nu hardcoded
        "total_users": len(site_users),
        "users": simplified
    })

@app.route("/debug", methods=["GET"])
def debug():
    """Toon technische details voor debugging"""
    return {
        "config": {
            "HALO_AUTH_URL": HALO_AUTH_URL,
            "HALO_API_BASE": HALO_API_BASE,
            "HALO_CLIENT_ID_NUM": HALO_CLIENT_ID_NUM,
            "HALO_SITE_ID": HALO_SITE_ID
        },
        "api_flow": [
            f"1. Haal client op: GET {HALO_API_BASE}/Clients/{HALO_CLIENT_ID_NUM}",
            f"2. Haal site op: GET {HALO_API_BASE}/Sites/{HALO_SITE_ID}",
            f"3. Haal gebruikers op: GET {HALO_API_BASE}/Sites/{HALO_SITE_ID}/Users"
        ],
        "halo_structure": "Halo PSA structuur: Client → Site → Users (NIET Client → Users → Site!)",
        "debug_hints": [
            "LET OP: Site ID is NIET globaal uniek - het is uniek PER CLIENT",
            "Een site behoort altijd tot precies 1 client",
            "Gebruik altijd de volgende volgorde: Client → Site → Users"
        ]
    }

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 App gestart op poort {port}")
    log.info("💡 Belangrijk: Volgorde is CRUCIAAL: Eerst Client valideren, dan Site, dan Users")
    app.run(host="0.0.0.0", port=port, debug=True)
