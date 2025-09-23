import os, urllib.parse, logging, sys, time
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests
from collections import Counter

# ------------------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("ticketbot")

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
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))       # Main site

USER_CACHE = {"all_users": [], "main_users": []}

# ------------------------------------------------------------------------------
# Halo helpers & Cache preload
# ------------------------------------------------------------------------------
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    r = requests.post(HALO_AUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(payload), timeout=10)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}

def fetch_all_client_users(client_id: int, max_pages=30):
    """ALLE users ophalen voor ClientID (ongeacht site)."""
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50
    while page <= max_pages:
        url = f"{HALO_API_BASE}/Users?$filter=ClientID eq {client_id}&pageSize={page_size}&pageNumber={page}"
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code != 200:
            log.error(f"❌ Error page {page}: {r.status_code}")
            break
        users = r.json().get("users", [])
        if not users: break
        all_users.extend(users)
        if len(users) < page_size: break
        page += 1
    return all_users

def preload_user_cache():
    """Cache vullen en loggen."""
    if USER_CACHE["all_users"]:
        return USER_CACHE
    log.info("🔄 Ophalen users voor Bossers & Cnossen…")
    all_users = fetch_all_client_users(HALO_CLIENT_ID_NUM)

    # Verdeling per site tellen
    from collections import Counter
    site_counts = Counter([str(u.get("site_id"))+"-"+str(u.get("site_name")) for u in all_users])
    for site,count in site_counts.items():
        log.info(f"   Site {site}: {count} users")

    main_users = [u for u in all_users if str(u.get("site_id")) == str(HALO_SITE_ID)
                                       or str(u.get("site_name") or "").lower() == "main"]

    USER_CACHE["all_users"] = all_users
    USER_CACHE["main_users"] = main_users
    log.info(f"👥 In totaal {len(all_users)} users bij klant {HALO_CLIENT_ID_NUM}")
    log.info(f"✅ {len(main_users)} users in SiteID={HALO_SITE_ID} (Main) gecached")

    # Log een paar voorbeeldusers
    for u in main_users[:5]:
        log.info(f"   Example: ID={u.get('id')}, Name={u.get('name')}, Email={u.get('EmailAddress')}, Site={u.get('site_name')}")
    return USER_CACHE

# ------------------------------------------------------------------------------
# Debug endpoints
# ------------------------------------------------------------------------------
@app.route("/debug/allusers")
def debug_all():
    preload_user_cache()
    users = USER_CACHE["all_users"]
    return jsonify({"total_all_users": len(users)})

@app.route("/debug/users")
def debug_users():
    preload_user_cache()
    return jsonify({"main_count": len(USER_CACHE["main_users"]),
                    "sample": [{"id": u.get("id"), "email": u.get("EmailAddress")} for u in USER_CACHE["main_users"][:10]]})

# ------------------------------------------------------------------------------
# Health
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}

# ------------------------------------------------------------------------------
# PRELOAD direct bij import (Render/Gunicorn safe!)
# ------------------------------------------------------------------------------
log.info("🚀 App import → preload users direct")
preload_user_cache()

if __name__=="__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
