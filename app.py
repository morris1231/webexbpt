import os, urllib.parse, logging, sys, time, threading
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
log = logging.getLogger("ticketbot")

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"}

HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL      = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE      = os.getenv("HALO_API_BASE", "").strip()

HALO_TICKET_TYPE_ID   = int(os.getenv("HALO_TICKET_TYPE_ID", "55"))
HALO_TEAM_ID          = int(os.getenv("HALO_TEAM_ID", "1"))
HALO_DEFAULT_IMPACT   = int(os.getenv("HALO_IMPACT", "3"))
HALO_DEFAULT_URGENCY  = int(os.getenv("HALO_URGENCY", "3"))
HALO_ACTIONTYPE_PUBLIC= int(os.getenv("HALO_ACTIONTYPE_PUBLIC", "78"))

# Specifieke klant/site
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12")) # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))       # Main site

ticket_room_map = {}
USER_CACHE = {"users": [], "timestamp": 0}

# ------------------------------------------------------------------------------
# Halo helpers & User Cache
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

def fetch_all_client_users(client_id: int, site_id: int, max_pages=30):
    """Alle users van klant ophalen, daarna filteren op Site (Main)."""
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
        if len(users) < page_size: break
        page += 1

    # Filter zelf op Main site
    filtered = [u for u in all_users if str(u.get("site_id")) == str(site_id)
                                     or str(u.get("site_name") or "").lower() == "main"]

    log.info(f"👥 Client={client_id}: {len(all_users)} totaal, {len(filtered)} uit Site {site_id} (Main)")
    return filtered

def preload_user_cache():
    if not USER_CACHE["users"]:
        log.info("🔄 Cache leeg → ophalen Bossers & Cnossen Main users...")
        USER_CACHE["users"] = fetch_all_client_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
        USER_CACHE["timestamp"] = time.time()
        log.info(f"✅ {len(USER_CACHE['users'])} Main users gecached")
        # Print ook even 5 voorbeeld users in de logs
        for u in USER_CACHE["users"][:5]:
            log.info(f"   UserID={u.get('id')} | Name={u.get('name')} | "
                     f"Email={u.get('EmailAddress') or u.get('emailaddress')} | "
                     f"Site={u.get('site_name')}")
    return USER_CACHE["users"]

def get_halo_user_id(email: str):
    if not email: return None
    email = email.strip().lower()
    for u in preload_user_cache():
        candidates = {
            str(u.get("EmailAddress") or "").lower(),
            str(u.get("PrimaryEmail") or "").lower(),
            str(u.get("emailaddress") or "").lower(),
            str(u.get("username") or "").lower(),
            str(u.get("LoginName") or "").lower(),
            str(u.get("networklogin") or "").lower(),
            str(u.get("adobject") or "").lower()
        }
        if email in candidates:
            log.info(f"✅ Match {email} → UserID={u.get('id')}")
            return u.get("id")
    log.warning(f"⚠️ Geen match {email}")
    return None

# ------------------------------------------------------------------------------
# Tickets
# ------------------------------------------------------------------------------
def create_halo_ticket(summary, name, email, omschrijving, sindswanneer,
                       watwerktniet, zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    h = get_halo_headers()
    requester_id = get_halo_user_id(email)

    body = {
        "Summary": summary,
        "Details": f"{omschrijving}\n\nSinds: {sindswanneer}\nWat werkt niet: {watwerktniet}\nZelf geprobeerd: {zelfgeprobeerd}\nImpact toelichting: {impacttoelichting}",
        "TypeID": HALO_TICKET_TYPE_ID,
        "ClientID": HALO_CLIENT_ID_NUM,
        "SiteID": HALO_SITE_ID,
        "TeamID": HALO_TEAM_ID,
        "ImpactID": int(impact_id),
        "UrgencyID": int(urgency_id)
    }
    if requester_id:
        body["UserID"] = int(requester_id)

    r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=body, timeout=15)
    log.info(f"➡️ Halo response {r.status_code}: {r.text}")
    return r.json() if r.status_code in (200,201) else None

def add_note_to_ticket(ticket_id, text, sender, email=None, room_id=None):
    h = get_halo_headers()
    body = {"Details": str(text), "ActionTypeID": HALO_ACTIONTYPE_PUBLIC, "IsPrivate": False}
    uid = get_halo_user_id(email) if email else None
    if uid: body["UserID"] = int(uid)
    r = requests.post(f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions", headers=h, json=body, timeout=10)
    log.info(f"➡️ AddNote response {r.status_code}")
    if r.status_code not in (200,201) and room_id:
        send_message(room_id, f"⚠️ Note toevoegen mislukt ({r.status_code})")

# ------------------------------------------------------------------------------
# Webex helpers
# ------------------------------------------------------------------------------
def send_message(room_id, text):
    requests.post("https://webexapis.com/v1/messages",
                 headers=WEBEX_HEADERS,
                 json={"roomId": room_id, "markdown": text}, timeout=10)

# ------------------------------------------------------------------------------
# Debug endpoints
# ------------------------------------------------------------------------------
@app.route("/debug/users", methods=["GET"])
def debug_users():
    users = preload_user_cache()
    sample = []
    for u in users[:10]:   # laat eerste 10 zien
        sample.append({
            "id": u.get("id"),
            "name": u.get("name"),
            "site": u.get("site_name"),
            "EmailAddress": u.get("EmailAddress") or u.get("emailaddress"),
            "PrimaryEmail": u.get("PrimaryEmail"),
            "Username": u.get("username"),
            "LoginName": u.get("LoginName"),
            "NetworkLogin": u.get("networklogin"),
            "AdObject": u.get("adobject")
        })
    return jsonify({
        "cached_count": len(users),
        "sample_users": sample
    })

@app.route("/debug/match")
def debug_match():
    email = request.args.get("email","").strip()
    uid = get_halo_user_id(email)
    return jsonify({"email": email, "found_userid": uid})

# ------------------------------------------------------------------------------
# Health
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}

# ------------------------------------------------------------------------------
# Startup preload
# ------------------------------------------------------------------------------
if __name__=="__main__":
    log.info("🚀 Startup → preload Main users cache")
    preload_user_cache()   # meteen ophalen + tonen voorbeelden in logs
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
