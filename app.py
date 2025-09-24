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
# Config - Nu met JUISTE DEFAULTS
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials (zet deze in je .env)
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# ✅ CRUCIAAL: Gebruik /oauth2/token (GEEN /auth/token!)
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
        "scope": "all"  # ✅ ALLEEN "all" werkt - geen .teams of andere suffixes!
    }
    try:
        log.info(f"🔐 Authenticatie aanvraag naar: {HALO_AUTH_URL} (scope={payload['scope']})")
        r = requests.post(
            HALO_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(payload),
            timeout=10
        )
        r.raise_for_status()
        token = r.json()["access_token"]
        log.info("✅ Authenticatie geslaagd! Token verkregen.")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        log.error(f"❌ Auth mislukt: {str(e)}")
        log.error(f"➡️ Gebruikte URL: {HALO_AUTH_URL}")
        log.error(f"➡️ Gebruikte scope: {payload['scope']}")
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
    """Haal Main-site gebruikers op via correcte API aanroepen."""
    h = get_halo_headers()
    
    # Probeer direct filteren op siteid (LET OP: GEEN UNDERSCORE!)
    site_url = f"{HALO_API_BASE}/Users?siteid={site_id}"
    log.info(f"🔍 API-aanvraag: {site_url}")
    
    try:
        r = requests.get(site_url, headers=h, timeout=20)
        if r.status_code == 200:
            data = r.json()
            # Verwerk verschillende response formaten
            users = data if isinstance(data, list) else data.get("users", []) or data.get("Users", [])
            
            if isinstance(users, list) and users:
                log.info(f"✅ {len(users)} Main-users gevonden via siteid={site_id}")
                return dedupe_users(users)
            log.warning("⚠️ API gaf lege lijst terug (geen gebruikers gevonden)")
            return []
        
        # Toon duidelijke fout als API error geeft
        log.error(f"❌ API fout ({r.status_code}): {r.text[:500]}")
        log.error("💡 Oplossing:")
        log.error("1. Heb je 'Teams' aangevinkt in API-toegang? (Instellingen → API-toegang)")
        log.error("2. Klopt de siteid? (Moet exact overeenkomen met URL: ?siteid=18)")
        log.error("3. Werkt de token? Test met: curl -H 'Authorization: Bearer ...' ...")
        return []
    
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
            "error": "Geen gebruikers gevonden",
            "solution": [
                "1. Controleer of 'Teams' is aangevinkt in API-toegang (Instellingen → API-toegang)",
                "2. Bezoek /debug voor technische details",
                "3. Test de API direct via Postman/Curl"
            ]
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
        "total_users": len(site_users),
        "users": simplified
    })

@app.route("/debug", methods=["GET"])
def debug():
    """Toon alle technische details voor debugging"""
    return {
        "config": {
            "HALO_AUTH_URL": HALO_AUTH_URL,
            "HALO_API_BASE": HALO_API_BASE,
            "HALO_CLIENT_ID_NUM": HALO_CLIENT_ID_NUM,
            "HALO_SITE_ID": HALO_SITE_ID,
            "scope_used": "all"  # Nu correct
        },
        "api_test": {
            "test_url": f"{HALO_API_BASE}/Users?siteid={HALO_SITE_ID}",
            "auth_url": HALO_AUTH_URL
        },
        "halo_instructions": [
            "1. Ga naar Halo PSA → Instellingen → API-toegang",
            "2. Selecteer jouw API key",
            "3. Vink 'Teams' aan onder Permissions",
            "4. Sla de wijzigingen op"
        ],
        "test_curl": f"curl -X GET '{HALO_API_BASE}/Users?siteid={HALO_SITE_ID}' -H 'Authorization: Bearer $(curl -X POST \"{HALO_AUTH_URL}\" -d \"grant_type=client_credentials&client_id={HALO_CLIENT_ID}&client_secret={HALO_CLIENT_SECRET}&scope=all\" | jq -r '.access_token')'"
    }

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 App gestart op poort {port}")
    log.info("💡 Belangrijk: Zorg dat je API key 'Teams' rechten heeft (Instellingen → API-toegang)")
    app.run(host="0.0.0.0", port=port, debug=True)
