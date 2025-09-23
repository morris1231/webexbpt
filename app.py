import os, urllib.parse, logging, sys, csv, io
from flask import Flask, request, jsonify, Response
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

HALO_CLIENT_ID_NUM = 12   # Bossers & Cnossen
HALO_SITE_ID       = 18   # Main

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

def fetch_main_users(client_id: int, site_id: int, max_pages=500):
    """
    Haal ALLE users van specifiek client + site (Main).
    Met fallback: als server-side filter niks oplevert, dan filteren we lokaal.
    """
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50

    while page <= max_pages:
        # Eerst proberen met filter op client + site
        url = (f"{HALO_API_BASE}/Users"
               f"?$filter=ClientID eq {client_id} and SiteId eq {site_id}"
               f"&pageSize={page_size}&pageNumber={page}")
        r = requests.get(url, headers=h, timeout=15)

        if r.status_code != 200:
            log.error(f"❌ Error page {page}: {r.status_code} {r.text}")
            break

        data = r.json()
        users = data.get("users") or data.get("Users") or []
        if page == 1 and not users:
            log.warning("⚠️ Server-side filter gaf niks, fallback naar client filteren…")
            return fetch_all_then_filter_locally(client_id, site_id, max_pages)

        if not users:
            break

        all_users.extend(users)
        if len(users) < page_size:
            break
        page += 1

    return all_users

def fetch_all_then_filter_locally(client_id: int, site_id: int, max_pages=500):
    """Fallback -> haal alle client-users en filter lokaal op site_id."""
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50

    while page <= max_pages:
        url = (f"{HALO_API_BASE}/Users"
               f"?$filter=ClientID eq {client_id}"
               f"&pageSize={page_size}&pageNumber={page}")
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code != 200:
            log.error(f"❌ Error page {page}: {r.status_code} {r.text}")
            break

        data = r.json()
        users = data.get("users") or data.get("Users") or []
        if not users:
            break

        all_users.extend(users)
        if len(users) < page_size:
            break
        page += 1

    # filter lokaal op site_id=18
    filtered = [u for u in all_users
                if str(u.get("site_id") or u.get("SiteId")) == str(site_id)]
    return filtered

# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------
@app.route("/debug/users", methods=["GET"])
def debug_users():
    """Alle users van Bossers & Cnossen (client=12), site=18 (Main)."""
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)

    limit_arg = request.args.get("limit", "20")
    if limit_arg == "ALL":
        selected = site_users
    else:
        try:
            limit = int(limit_arg)
        except:
            limit = 20
        selected = site_users[:limit]

    sample = [{
        "id": u.get("id"),
        "name": u.get("name"),
        "site_id": u.get("site_id") or u.get("SiteId"),
        "site_name": u.get("site_name") or u.get("SiteName"),
        "email": u.get("EmailAddress") or u.get("emailaddress"),
    } for u in selected]

    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
        "total_users": len(site_users),
        "sample_users": sample
    })

@app.route("/debug/users.csv", methods=["GET"])
def users_csv():
    """Download alle Main users als CSV."""
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)

    # CSV in memory schrijven
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "site_id", "site_name", "email"])
    for u in site_users:
        writer.writerow([
            u.get("id"),
            u.get("name"),
            u.get("site_id") or u.get("SiteId"),
            u.get("site_name") or u.get("SiteName"),
            u.get("EmailAddress") or u.get("emailaddress"),
        ])

    csv_data = output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=main_users.csv"}
    )

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Halo Main users debug draait!"}

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
