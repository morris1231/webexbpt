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

# 👇 Specifieke klant en site (Bossers & Cnossen → Main)
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
    """Haal users van Client 12 en filter op Site Main (18)."""
    print("⚡ dump_site_users() wordt uitgevoerd...", flush=True)
    try:
        h = get_halo_headers()
        url = f"{HALO_API_BASE}/Users?$filter=ClientID eq {HALO_CLIENT_ID_NUM}"
        print(f"➡️ API call: {url}", flush=True)
        r = requests.get(url, headers=h)
        print(f"⬅️ Status {r.status_code}", flush=True)
        if r.status_code != 200:
            print(f"❌ Error: {r.text[:200]}", flush=True)
            return
        data = r.json()
        users = data.get("users", [])
        main_users = [u for u in users if str(u.get("site_id")) == str(HALO_SITE_ID)
                                        or str(u.get("site_name", "")).lower() == "main"]

        print(f"✅ Client {HALO_CLIENT_ID_NUM} had {len(users)} users totaal", flush=True)
        print(f"✅ Daarvan {len(main_users)} gekoppeld aan SiteID {HALO_SITE_ID} (Main)", flush=True)

        for u in main_users:
            print(
                f"UserID={u.get('id')} | Name={u.get('name')} | "
                f"Email={u.get('emailaddress')} | "
                f"Site={u.get('site_name')}", flush=True
            )
    except Exception as e:
        print(f"❌ dump_site_users error: {e}", flush=True)

def get_halo_user_id(email: str):
    """Zoek gebruiker met email in Client 12, maar alleen als deze bij Site Main hoort."""
    if not email:
        return None
    h = get_halo_headers()
    url = f"{HALO_API_BASE}/Users?$filter=ClientID eq {HALO_CLIENT_ID_NUM}"
    r = requests.get(url, headers=h)
    if r.status_code != 200:
        log.error(f"❌ User lookup failed: {r.status_code} {r.text}")
        return None

    users = r.json().get("users", [])
    email = email.strip().lower()

    for u in users:
        site_ok = str(u.get("site_id")) == str(HALO_SITE_ID) or str(u.get("site_name", "")).lower() == "main"
        if not site_ok:
            continue

        emails = {
            str(u.get("emailaddress") or "").lower(),
            str(u.get("networklogin") or "").lower(),
            str(u.get("adobject") or "").lower()
        }
        if email in emails:
            log.info(f"✅ Match gevonden: {email} → UserID {u.get('id')} (Site={u.get('site_name')})")
            return u.get("id")

    log.warning(f"❌ {email} niet gevonden in Bossers & Cnossen/Main")
    return None

# ------------------------------------------------------------------------------
# Example health
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}

# ------------------------------------------------------------------------------
# Startup dump bij module import (Render/Gunicorn safe)
# ------------------------------------------------------------------------------
print("🚀 Ticketbot start op", flush=True)
dump_site_users()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
