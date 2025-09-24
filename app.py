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

HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL      = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE      = os.getenv("HALO_API_BASE", "").strip()

HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))   # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))         # Main

# ------------------------------------------------------------------------------
# Halo API helpers
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Vraag een bearer token op en retourneer headers."""
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
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

def fetch_main_users(client_id: int, site_id: int):
    """Probeer eerst Site-users direct op te halen, anders Client-users."""
    h = get_halo_headers()

    # Eerst Sites endpoint
    site_url = f"{HALO_API_BASE}/Sites/{site_id}/Users"
    log.info(f"🔎 Probeer {site_url}")
    r = requests.get(site_url, headers=h, timeout=20)
    if r.status_code == 200:
        users = r.json().get("users") or r.json().get("Users") or r.json()
        if users:
            log.info(f"✅ {len(users)} gebruikers gevonden via Site {site_id}")
            return dedupe_users(users)

    log.warning("⚠️ /Sites endpoint gaf niets, val terug naar /Clients endpoint")

    # Fallback Clients endpoint
    client_url = f"{HALO_API_BASE}/Clients/{client_id}/Users"
    log.info(f"🔎 Probeer {client_url}")
    r = requests.get(client_url, headers=h, timeout=20)
    r.raise_for_status()
    users = r.json().get("users") or r.json().get("Users") or r.json()
    log.info(f"✅ {len(users)} gebruikers gevonden via Client {client_id}")
    return dedupe_users(users)

def dedupe_users(users):
    """Verwijder dubbele users op id."""
    seen, result = set(), []
    for u in users:
        uid = u.get("id")
        if uid not in seen:
            seen.add(uid)
            result.append(u)
    return result

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Halo Main users app draait!"}

@app.route("/users", methods=["GET"])
def users():
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    simplified = [{
        "id"   : u.get("id"),
        "name" : u.get("name"),
        "email": u.get("EmailAddress") or u.get("emailaddress") or u.get("email"),
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
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "email"])
    for u in site_users:
        writer.writerow([
            u.get("id"),
            u.get("name"),
            u.get("EmailAddress") or u.get("emailaddress") or u.get("email"),
        ])

    csv_data = output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=main_users.csv"}
    )

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("🚀 App gestart")
    app.run(host="0.0.0.0", port=port, debug=False)
