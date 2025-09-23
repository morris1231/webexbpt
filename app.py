import os, urllib.parse, logging, sys
from flask import Flask, jsonify
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
log = logging.getLogger("halo-debug")

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL      = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE      = os.getenv("HALO_API_BASE", "").strip()

HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12")) # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))       # Main

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
        data=urllib.parse.urlencode(payload), timeout=10
    )
    r.raise_for_status()
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "Content-Type": "application/json"
    }

def fetch_main_users(client_id: int, site_id: int, max_pages=30):
    """Haal ALLEEN users van de Main site (site_id=18) via Halo paging."""
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50

    while page <= max_pages:
        url = (f"{HALO_API_BASE}/Users?"
               f"$filter=ClientID eq {client_id} and SiteID eq {site_id}"
               f"&pageSize={page_size}&pageNumber={page}")
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code != 200:
            log.error(f"❌ Error page {page}: {r.status_code} {r.text}")
            break
        users = r.json().get("users", [])
        if not users:
            break
        all_users.extend(users)
        if len(users) < page_size:
            break
        page += 1

    # ✅ HARD filter: alleen SiteID=18
    main = [u for u in all_users if str(u.get("site_id")) == str(site_id)]
    log.info(f"👥 Totaal {len(main)} users uit Site {site_id} (Main)")
    return main

# ------------------------------------------------------------------------------
# Debug endpoints
# ------------------------------------------------------------------------------
@app.route("/debug/users", methods=["GET"])
def debug_users():
    users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    sample = []
    for u in users[:20]:
        sample.append({
            "id": u.get("id"),
            "name": u.get("name"),
            "site_id": u.get("site_id"),
            "site_name": u.get("site_name"),
            "email": u.get("EmailAddress") or u.get("emailaddress"),
        })
    return jsonify({
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
        "total_users": len(users),
        "sample_users": sample
    })

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Debug Halo Main users draait!"}

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("🚀 Startup: ophalen Main users (site 18)")
    users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    log.info(f"✅ {len(users)} users gecached voor Site {HALO_SITE_ID} (Main)")
    for u in users[:5]:
        log.info(f"   Example: ID={u.get('id')}, Name={u.get('name')}, Email={u.get('EmailAddress')}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
