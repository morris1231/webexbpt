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

# API credentials (zet deze in je .env)
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL      = os.getenv("HALO_AUTH_URL", "https://bncuat.halopsa.com/oauth2/token").strip()
HALO_API_BASE      = os.getenv("HALO_API_BASE", "https://bncuat.halopsa.com/api").strip()

# Jouw specifieke IDs (moeten exact overeenkomen met URL)
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))   # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))         # Main site

# ------------------------------------------------------------------------------
# Halo API helpers
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Vraag een bearer token op met JUISTE SCOPE (all.teams)"""
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all.teams"  # CRUCIAAL: "all" werkt NIET voor gebruikers!
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
        log.error(f"Response: {r.text if 'r' in locals() else 'N/A'}")
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
    
    # EERSTE PROBEER: Direct filteren op siteid (LET OP: GEEN UNDERSCORE!)
    site_url = f"{HALO_API_BASE}/Users?siteid={site_id}"
    log.info(f"🔍 Probeer directe site-filter: {site_url}")
    
    try:
        r = requests.get(site_url, headers=h, timeout=20)
        if r.status_code == 200:
            data = r.json()
            # Verwerk verschillende response formaten
            users = data if isinstance(data, list) else data.get("users", []) or data.get("Users", [])
            
            if isinstance(users, list) and users:
                log.info(f"✅ {len(users)} Main-users gevonden via siteid={site_id}")
                return dedupe_users(users)
            log.warning("⚠️ Site-filter gaf lege lijst terug")
        else:
            log.warning(f"⚠️ Site-filter gaf {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"❌ Site-filter error: {str(e)}")

    # TWEEDE PROBEER: Haal clientgebruikers en filter lokaal
    client_url = f"{HALO_API_BASE}/Users?clientid={client_id}"
    log.info(f"🔍 Probeer client-filter: {client_url}")
    
    try:
        r = requests.get(client_url, headers=h, timeout=20)
        if r.status_code == 200:
            data = r.json()
            users = data if isinstance(data, list) else data.get("users", []) or data.get("Users", [])
            
            if isinstance(users, list):
                # Filter op siteid (LET OP: GEEN UNDERSCORE!)
                filtered = [
                    u for u in users
                    if str(u.get("siteid", "") or u.get("SiteId", "") or u.get("siteId", "")) == str(site_id)
                ]
                if filtered:
                    log.info(f"✅ {len(filtered)} Main-users gevonden via clientid={client_id}")
                    return dedupe_users(filtered)
                log.warning(f"⚠️ Geen gebruikers met siteid={site_id} gevonden")
            else:
                log.warning("⚠️ Client-filter gaf geen user-lijst terug")
        else:
            log.warning(f"⚠️ Client-filter gaf {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"❌ Client-filter error: {str(e)}")

    # DERDE PROBEER: Haal ALLE gebruikers en filter lokaal
    all_url = f"{HALO_API_BASE}/Users"
    log.info(f"🔍 Fallback: haal alle gebruikers op ({all_url})")
    
    try:
        r = requests.get(all_url, headers=h, timeout=30)
        if r.status_code == 200:
            data = r.json()
            users = data if isinstance(data, list) else data.get("users", []) or data.get("Users", [])
            
            if isinstance(users, list):
                filtered = [
                    u for u in users
                    if str(u.get("siteid", "") or u.get("SiteId", "") or u.get("siteId", "")) == str(site_index)
                ]
                if filtered:
                    log.info(f"✅ {len(filtered)} Main-users gevonden via volledige lijst")
                    return dedupe_users(filtered)
                log.warning(f"⚠️ Geen gebruikers met siteid={site_id} gevonden in volledige lijst")
            else:
                log.error("❌ Volledige lijst gaf geen user-lijst terug")
        else:
            log.error(f"❌ Volledige lijst gaf {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"❌ Volledige lijst error: {str(e)}")

    # CRITIEKE FOUTBERICHTEN
    log.error("="*50)
    log.error("❌ GEEN GEBRUIKERS GEVONDEN! Controleer:")
    log.error("1. Scope is 'all.teams' (NIET 'all') in get_halo_headers()")
    log.error("2. Parameter spelling: 'siteid' i.p.v. 'site_id' (geen underscore!)")
    log.error(f"3. Correcte IDs: client_id={client_id}, site_id={site_id}")
    log.error("4. API rechten: Heeft jouw API key toegang tot deze klant/site?")
    log.error("="*50)
    return []

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Halo Main users app draait!"}

@app.route("/users", methods=["GET"])
def users():
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    
    # Valideer of we überhaupt gebruikers hebben
    if not site_users:
        return jsonify({
            "error": "Geen gebruikers gevonden",
            "hint": "Controleer logs voor details - waarschijnlijk API rechten of verkeerde IDs"
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

@app.route("/users.csv", methods=["GET"])
def users_csv():
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    
    if not site_users:
        return "Geen gebruikers gevonden. Controleer API rechten en configuratie.", 500
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "email"])
    
    for u in site_users:
        writer.writerow([
            u.get("id") or "",
            u.get("name") or u.get("Name") or "Onbekend",
            u.get("EmailAddress") or u.get("emailaddress") or u.get("email") or ""
        ])
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=main_users.csv"}
    )

@app.route("/debug", methods=["GET"])
def debug():
    """Toon alle technische details voor debugging"""
    return {
        "config": {
            "HALO_AUTH_URL": HALO_AUTH_URL,
            "HALO_API_BASE": HALO_API_BASE,
            "HALO_CLIENT_ID_NUM": HALO_CLIENT_ID_NUM,
            "HALO_SITE_ID": HALO_SITE_ID,
            "scope_used": "all.teams"  # Hardcoded omdat we dit nu gebruiken
        },
        "endpoints": {
            "site_filter": f"{HALO_API_BASE}/Users?siteid={HALO_SITE_ID}",
            "client_filter": f"{HALO_API_BASE}/Users?clientid={HALO_CLIENT_ID_NUM}"
        },
        "hint": "Bezoek /debug-users voor raw API response"
    }

@app.route("/debug-users", methods=["GET"])
def debug_users():
    """Toon de RAW API response voor debugging"""
    h = get_halo_headers()
    url = f"{HALO_API_BASE}/Users?siteid={HALO_SITE_ID}"
    
    try:
        r = requests.get(url, headers=h, timeout=20)
        return {
            "request": {
                "url": url,
                "headers": {k: v for k, v in h.items() if k != "Authorization"}  # Verberg token
            },
            "response": {
                "status": r.status_code,
                "body": r.json() if r.status_code == 200 else r.text
            }
        }
    except Exception as e:
        return {"error": str(e)}, 500

# ------------------------------------------------------------------------------
if __name__ == "__main__":  # CORRECTE SYNTAX (geen **name**)
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 App gestart op poort {port} – bezoek /users of /debug voor info")
    app.run(host="0.0.0.0", port=port, debug=True)  # debug=True voor betere foutmeldingen
