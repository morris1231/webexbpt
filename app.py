import os, requests, urllib.parse, json, logging, sys
from flask import Flask, request
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Logging configuratie
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("ticketbot")

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN", "").strip()
WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}

HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE = os.getenv("HALO_API_BASE", "").strip()

HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", "55"))
HALO_TEAM_ID = int(os.getenv("HALO_TEAM_ID", "1"))
HALO_DEFAULT_IMPACT = int(os.getenv("HALO_IMPACT", "3"))
HALO_DEFAULT_URGENCY = int(os.getenv("HALO_URGENCY", "3"))

HALO_ACTIONTYPE_PUBLIC = int(os.getenv("HALO_ACTIONTYPE_PUBLIC", "78"))

# Specifieke klant en site (Bossers & Cnossen / Main)
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))
HALO_SITE_ID = int(os.getenv("HALO_SITE_ID", "18"))

ticket_room_map = {}

# ------------------------------------------------------------------------------
# Halo helpers
# ------------------------------------------------------------------------------
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    r = requests.post(
        HALO_AUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(payload)
    )
    if r.status_code != 200:
        print(f"❌ Auth faalde: {r.status_code} {r.text}", flush=True)
    r.raise_for_status()
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "Content-Type": "application/json"
    }

def dump_site_users():
    """Haal alle users van Bossers & Cnossen / Main (ClientID+SiteID) bij startup."""
    print("⚡ dump_site_users() wordt uitgevoerd...", flush=True)
    try:
        h = get_halo_headers()

        url = f"{HALO_API_BASE}/Clients/{HALO_CLIENT_ID_NUM}/Sites/{HALO_SITE_ID}/Users"
        print(f"➡️ API call naar: {url}", flush=True)
        r = requests.get(url, headers=h)
        print(f"⬅️ Status {r.status_code}", flush=True)
        print(f"⬅️ Response snippet: {r.text[:300]}", flush=True)

        r.raise_for_status()
        site_users = r.json() if isinstance(r.json(), list) else []
        print(f"✅ Halo gaf {len(site_users)} users terug (Client {HALO_CLIENT_ID_NUM}, Site {HALO_SITE_ID})", flush=True)

        for u in site_users:
            line = (
                f"UserID={u.get('ID')} | Name={u.get('Name')} | "
                f"Email={u.get('Email')} | "
                f"NetworkLogin={u.get('NetworkLogin')} | "
                f"ADObject={u.get('ADObject')}"
            )
            print(line, flush=True)
            log.info(line)
    except Exception as e:
        print(f"❌ dump_site_users error: {e}", flush=True)

def get_halo_user_id(email: str):
    """Zoek user in Bossers & Cnossen / Main via Clients/{clientId}/Sites/{siteId}/Users"""
    if not email:
        return None
    h = get_halo_headers()

    url = f"{HALO_API_BASE}/Clients/{HALO_CLIENT_ID_NUM}/Sites/{HALO_SITE_ID}/Users"
    r = requests.get(url, headers=h)
    if r.status_code != 200:
        log.error(f"❌ User lookup failed: {r.status_code} {r.text}")
        return None

    site_users = r.json() if isinstance(r.json(), list) else []
    email = email.strip().lower()

    for u in site_users:
        emails = {
            str(u.get("Email") or "").lower(),
            str(u.get("NetworkLogin") or "").lower(),
            str(u.get("ADObject") or "").lower()
        }
        if email in emails:
            log.info(f"✅ Match gevonden: {email} → UserID {u.get('ID')}")
            return u.get("ID")

    log.warning(f"❌ {email} niet gevonden in Client {HALO_CLIENT_ID_NUM} / Site {HALO_SITE_ID}")
    return None

# ------------------------------------------------------------------------------
# Voorbeeld gebruik: health endpoint
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}

# ------------------------------------------------------------------------------
# Startup dump uitvoeren bij module import (Render/Gunicorn)
# ------------------------------------------------------------------------------
print("🚀 Ticketbot start op", flush=True)
dump_site_users()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
