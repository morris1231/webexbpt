import os, urllib.parse, logging, sys
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests
import csv, io

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

# IDs → Bossers & Cnossen (12), Main (18)
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))

# ------------------------------------------------------------------------------
# Halo API helpers
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Vraag een bearer token op en stel headers samen."""
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

def fetch_main_users(client_id: int, site_id: int, max_pages=50):
    """Haal ALLE users van de opgegeven client & site (Main)."""
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50

    while page <= max_pages:
        url = (f"{HALO_API_BASE}/Users"
               f"?$filter=ClientID eq {client_id} and SiteId eq {site_id}"
               f"&pageSize={page_size}&pageNumber={page}")

        r = requests.get(url, headers=h, timeout=15)
        if r.status_code != 200:
            log.error(f"❌ Error page {page}: {r.status_code} {r.text}")
            break

        data = r.json()
        users = data.get("users") or data.get("Users") or []
        count = data.get("count") or data.get("totalCount")

        if not users:  # Geen data meer
            break

        all_users.extend(users)
        log.info(f"📄 Page {page}: {len(users)} users, totaal {len(all_users)}")

        # Stopcriteria: minder dan page_size of totaal bereikt
        if len(users) < page_size:
            break
        if count and len(all_users) >= count:
            break

        page += 1

    return all_users

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Halo Main users app draait!"}

@app.route("/users", methods=["GET"])
def users():
    """JSON lijst van alle Main users."""
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    simplified = [{
        "id"   : u.get("id"),
        "name" : u.get("name"),
        "email": u.get("EmailAddress") or u.get("emailaddress"),
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
    """Download alle Main users als CSV-bestand."""
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "email"])
    for u in site_users:
        writer.writerow([
            u.get("id"),
            u.get("name"),
            u.get("EmailAddress") or u.get("emailaddress"),
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
    app.run(host="0.0.0.0", port=port, debug=False)
