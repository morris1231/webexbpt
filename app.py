import os, urllib.parse, logging, sys, time
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

HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12")) # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))       # Main

USER_CACHE = {"users": []}

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
    """Haal ALLE echte gebruikers van Client+Site Main (excl. IsAgent=true)."""
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50
    while page <= max_pages:
        # 🔑 Filter: ClientID + SiteID + geen agent/categorie
        url = (f"{HALO_API_BASE}/Users?"
               f"$filter=ClientID eq {client_id} and SiteID eq {site_id} and IsAgent eq false"
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
        if len(users) < page_size:
            break
        page += 1

    log.info(f"👥 Eind: {len(all_users)} users opgehaald (Client={client_id}, Site={site_id})")
    return all_users

def preload_user_cache():
    """Cache alleen de Main-users voor debug."""
    if not USER_CACHE["users"]:
        USER_CACHE["users"] = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
        log.info(f"✅ {len(USER_CACHE['users'])} Main users gecached")
        for u in USER_CACHE["users"][:5]:
            log.info(f"   Example: ID={u.get('id')}, Name={u.get('name')}, Email={u.get('EmailAddress')}, Site={u.get('site_name')}")
    return USER_CACHE["users"]

def get_halo_user_id(email: str):
    """Zoek userID van een e-mailadres in de cache."""
    if not email: return None
    email = email.strip().lower()
    for u in preload_user_cache():
        fields = {
            str(u.get("EmailAddress") or "").lower(),
            str(u.get("PrimaryEmail") or "").lower(),
            str(u.get("emailaddress") or "").lower(),
            str(u.get("username") or "").lower(),
            str(u.get("LoginName") or "").lower(),
            str(u.get("networklogin") or "").lower(),
            str(u.get("adobject") or "").lower()
        }
        if email in fields:
            log.info(f"✅ Match: {email} → ID={u.get('id')}")
            return u.get("id")
    log.warning(f"⚠️ {email} niet gevonden in {len(USER_CACHE['users'])} Main-users")
    return None

# ------------------------------------------------------------------------------
# Debug endpoints
# ------------------------------------------------------------------------------
@app.route("/debug/users", methods=["GET"])
def debug_users():
    """Laat alle Main users zien (site=18) met hun email/info."""
    users = preload_user_cache()
    sample = []
    for u in users[:20]:   # alleen eerste 20 tonen om output klein te houden
        sample.append({
            "id": u.get("id"),
            "name": u.get("name"),
            "site_id": u.get("site_id"),
            "site_name": u.get("site_name"),
            "email": u.get("EmailAddress") or u.get("emailaddress"),
            "username": u.get("username"),
            "login": u.get("LoginName") or u.get("networklogin")
        })
    return jsonify({
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
        "total_users": len(users),
        "sample_users": sample
    })

@app.route("/debug/match")
def debug_match():
    """Check of een e-mail matcht in Main users."""
    email = request.args.get("email","").strip()
    uid = get_halo_user_id(email)
    return jsonify({"email": email, "user_id": uid})

# ------------------------------------------------------------------------------
# Health
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Debug Halo Main users draait!"}

# ------------------------------------------------------------------------------
if __name__=="__main__":
    log.info("🚀 Startup → haal Main-users op")
    preload_user_cache()
    port=int(os.getenv("PORT",5000))
    app.run(host="0.0.0.0", port=port, debug=False)
