import os, urllib.parse, logging, sys
from flask import Flask, request, jsonify
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

HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12")) # Jouw klant
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
        data=urllib.parse.urlencode(payload),
        timeout=10
    )
    r.raise_for_status()
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "Content-Type": "application/json"
    }


def fetch_all_main_users(client_id: int, site_id: int, max_pages=500):
    """Haal ALLE users van specifieke site (Main)."""
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50

    while page <= max_pages:
        url = (f"{HALO_API_BASE}/Users"
               f"?$filter=ClientID eq {client_id} and Site_Id eq {site_id}"
               f"&pageSize={page_size}&pageNumber={page}")
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code != 200:
            log.error(f"❌ Error page {page}: {r.status_code} {r.text}")
            break

        users = r.json().get("users", [])
        if not users:
            break

        all_users.extend(users)
        log.info(f"📄 Page {page}: {len(users)} users, totaal {len(all_users)}")

        if len(users) < page_size:  # geen volgende pagina
            break
        page += 1

    return all_users

# ------------------------------------------------------------------------------
# Debug endpoints
# ------------------------------------------------------------------------------
@app.route("/debug/users", methods=["GET"])
def debug_users():
    """Main (site_id=18) users. Geef alles terug of een subset als ?limit=20"""
    all_users = fetch_all_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)

    limit_arg = request.args.get("limit", "20")
    if limit_arg == "ALL":
        selected = all_users
    else:
        try:
            limit = int(limit_arg)
        except:
            limit = 20
        selected = all_users[:limit]

    sample = []
    for u in selected:
        sample.append({
            "id"       : u.get("id"),
            "name"     : u.get("name"),
            "site_id"  : u.get("site_id"),
            "site_name": u.get("site_name"),
            "email"    : u.get("EmailAddress") or u.get("emailaddress"),
        })

    return jsonify({
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
        "total_users": len(all_users),
        "sample_users": sample
    })


@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Halo Main users debug draait!"}

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
