import os, urllib.parse, logging, sys, time, threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests
from collections import Counter

# ------------------------------------------------------------------------------
# Logging
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

# ------------------------------------------------------------------------------
# Halo helpers & User Cache
# ------------------------------------------------------------------------------
USER_CACHE = {"all_users": [], "main_users": []}

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
    """Haal alle users van client (ongefilterd per site) met paging."""
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50

    while page <= max_pages:
        url = f"{HALO_API_BASE}/Users?$filter=ClientID eq {client_id}&pageSize={page_size}&pageNumber={page}"
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code != 200:
            log.error(f"❌ Halo error page {page}: {r.status_code} {r.text}")
            break
        users = r.json().get("users", [])
        if not users: break
        all_users.extend(users)
        log.info(f"📄 Page {page}: {len(users)} users (totaal nu {len(all_users)})")
        if len(users) < page_size: break
        page += 1

    return all_users

def preload_user_cache():
    """Haal alle users van client en filter Main users."""
    if USER_CACHE["all_users"]:
        return USER_CACHE

    log.info("🔄 Ophalen ALLE users van Bossers & Cnossen…")
    all_users = fetch_all_client_users(HALO_CLIENT_ID_NUM)

    # Verdeling per site
    site_counts = Counter([str(u.get("site_id")) + " - " + str(u.get("site_name")) for u in all_users])
    for site, count in site_counts.items():
        log.info(f"   Site {site}: {count} users")

    main_users = [u for u in all_users if str(u.get("site_id")) == str(HALO_SITE_ID)
                                       or str(u.get("site_name") or "").lower() == "main"]

    USER_CACHE["all_users"] = all_users
    USER_CACHE["main_users"] = main_users

    log.info(f"👥 Totaal users bij klant {HALO_CLIENT_ID_NUM}: {len(all_users)}")
    log.info(f"✅ Daarvan {len(main_users)} users in SiteID={HALO_SITE_ID} (Main)")

    # Toon voorbeeldgebruikers uit Main
    for u in main_users[:5]:
        log.info(f"   UserID={u.get('id')} | Name={u.get('name')} | Email={u.get('EmailAddress') or u.get('emailaddress')} | Site={u.get('site_name')}")

    return USER_CACHE

def get_halo_user_id(email: str):
    """Zoek UserID op basis van e-mail in de Main-site cache."""
    if not email: return None
    email = email.strip().lower()
    preload_user_cache()
    for u in USER_CACHE["main_users"]:
        check_vals = {
            str(u.get("EmailAddress") or "").lower(),
            str(u.get("PrimaryEmail") or "").lower(),
            str(u.get("emailaddress") or "").lower(),
            str(u.get("username") or "").lower(),
            str(u.get("LoginName") or "").lower(),
            str(u.get("networklogin") or "").lower(),
            str(u.get("adobject") or "").lower()
        }
        if email in check_vals:
            log.info(f"✅ Match {email} → UserID={u.get('id')}")
            return u.get("id")
    log.warning(f"⚠️ Geen match voor {email}")
    return None

# ------------------------------------------------------------------------------
# Debug endpoints
# ------------------------------------------------------------------------------
@app.route("/debug/allusers")
def debug_allusers():
    """Alle users van Client=12, verdeling per site en voorbeeld."""
    cache = preload_user_cache()
    users = cache["all_users"]

    site_counts = Counter([u.get("site_name") for u in users])
    sample = []
    for u in users[:20]:
        sample.append({
            "id": u.get("id"),
            "name": u.get("name"),
            "site_id": u.get("site_id"),
            "site_name": u.get("site_name"),
            "Email": u.get("EmailAddress") or u.get("emailaddress")
        })

    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "total_users": len(users),
        "per_site": site_counts,
        "sample_users": sample
    })

@app.route("/debug/users")
def debug_users():
    """Alleen Main-site users (SiteID=18)."""
    cache = preload_user_cache()
    users = cache["main_users"]
    sample = []
    for u in users[:20]:
        sample.append({
            "id": u.get("id"),
            "name": u.get("name"),
            "site": u.get("site_name"),
            "Email": u.get("EmailAddress") or u.get("emailaddress")
        })
    return jsonify({
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
        "cached_count": len(users),
        "sample_users": sample
    })

@app.route("/debug/match")
def debug_match():
    """Test lookup voor e-mail"""
    email = request.args.get("email","").strip()
    uid = get_halo_user_id(email)
    return jsonify({"email": email, "user_id": uid})

# ------------------------------------------------------------------------------
# Health
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}

# ------------------------------------------------------------------------------
if __name__=="__main__":
    log.info("🚀 Startup → preload users direct")
    preload_user_cache()   # direct ophalen en tonen verdeling in logs
    port=int(os.getenv("PORT",5000))
    app.run(host="0.0.0.0",port=port,debug=False)
