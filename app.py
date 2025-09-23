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

# Site Bossers & Cnossen → Main
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
    """Haal alle users van de site op en log ze keihard bij startup."""
    print("⚡ dump_site_users() wordt uitgevoerd...", flush=True)
    log.info("🚀 Startup check gestart: ophalen users van Halo...")
    try:
        h = get_halo_headers()
        site_url = f"{HALO_API_BASE}/Sites/{HALO_SITE_ID}/Users"
        r = requests.get(site_url, headers=h)
        r.raise_for_status()
        site_users = r.json() if isinstance(r.json(), list) else []
        print(f"✅ Halo gaf {len(site_users)} users terug bij startup", flush=True)
        log.info(f"=== Startup: Site {HALO_SITE_ID} heeft {len(site_users)} users ===")

        for u in site_users:
            line = (
                f"UserID={u.get('ID')} | "
                f"Email={u.get('Email')} | "
                f"NetworkLogin={u.get('NetworkLogin')} | "
                f"ADObject={u.get('ADObject')}"
            )
            print(line, flush=True)
            log.info(line)
    except Exception as e:
        print(f"❌ Kon site users niet ophalen bij startup: {e}", flush=True)
        log.error(f"❌ Kon site users niet ophalen bij startup: {e}")

def get_halo_user_id(email: str):
    """Zoekt UserID in de Site Users-lijst zelf."""
    if not email:
        return None
    h = get_halo_headers()
    email = email.strip().lower()

    try:
        site_url = f"{HALO_API_BASE}/Sites/{HALO_SITE_ID}/Users"
        r = requests.get(site_url, headers=h)
        r.raise_for_status()
        site_users = r.json() if isinstance(r.json(), list) else []
    except Exception as e:
        log.error(f"Kon site users niet ophalen: {e}")
        return None

    for user in site_users:
        user_id = user.get("ID")
        mails = {
            str(user.get("Email", "")).lower(),
            str(user.get("NetworkLogin", "")).lower(),
            str(user.get("ADObject", "")).lower(),
        }
        if email in mails:
            log.info(f"✅ User gevonden: {email} → UserID {user_id}")
            return user_id

    log.warning(f"❌ Geen match voor {email} in site {HALO_SITE_ID}")
    return None

# ------------------------------------------------------------------------------
# Safe POST wrapper
# ------------------------------------------------------------------------------
def safe_post_action(url, headers, payload, room_id=None):
    log.debug("➡️ Payload naar Halo:\n" + json.dumps(payload, indent=2))
    r = requests.post(url, headers=headers, json=payload)
    log.debug(f"⬅️ Halo response: {r.status_code} {r.text}")
    if r.status_code != 200 and room_id:
        send_message(room_id, f"⚠️ Halo error {r.status_code}:\n```\n{r.text}\n```")
    return r

# ------------------------------------------------------------------------------
# Ticket creation (onveranderd behalve logging)
# ------------------------------------------------------------------------------
def create_halo_ticket(summary, naam, email,
                       omschrijving="", sindswanneer="", watwerktniet="",
                       zelfgeprobeerd="", impacttoelichting="",
                       impact_id=3, urgency_id=3, room_id=None):
    user_id = get_halo_user_id(email)
    if not user_id:
        if room_id:
            send_message(room_id, f"❌ {email} hoort niet bij Bossers & Cnossen (Main). Ticket niet aangemaakt.")
        return None
    log.info(f"👤 Ticket aanmaker: {email} (UserID: {user_id})")

    h = get_halo_headers()
    ticket = {
        "Summary": summary,
        "Details": f"👤 Ticket aangemaakt door {naam} ({email})",
        "TypeID": HALO_TICKET_TYPE_ID,
        "TeamID": HALO_TEAM_ID,
        "Impact": int(impact_id),
        "Urgency": int(urgency_id),
        "SiteID": HALO_SITE_ID,
        "CFReportedUser": f"{naam} ({email})"
    }
    r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[ticket])
    r.raise_for_status()
    data = r.json()[0] if isinstance(r.json(), list) else r.json()
    ticket_id = data.get("id") or data.get("ID")
    return {"id": ticket_id, "ref": ticket_id}

# ------------------------------------------------------------------------------
# Webex helpers & routes (onveranderd)
# ------------------------------------------------------------------------------
def send_message(room_id, text):
    requests.post("https://webexapis.com/v1/messages",
                  headers=WEBEX_HEADERS,
                  json={"roomId": room_id, "markdown": text})

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}
