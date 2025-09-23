import os, urllib.parse, logging, sys, time, threading
from flask import Flask, request
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ------------------------------------------------------------------------------
# Logging config
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("ticketbot")

# ------------------------------------------------------------------------------
# Requests Session with Retry
# ------------------------------------------------------------------------------
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
TARGET_URL = os.getenv("WEBEX_TARGET_URL", "https://webexbpt-1.onrender.com/webex")
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

HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))
HALO_SITE_ID = int(os.getenv("HALO_SITE_ID", "18"))

ticket_room_map = {}

# ------------------------------------------------------------------------------
# Halo User Cache
# ------------------------------------------------------------------------------
USER_CACHE = {"users": [], "timestamp": 0}
CACHE_TTL = 3600  # 1 uur

def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    r = session.post(
        HALO_AUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(payload),
        timeout=10
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

def fetch_all_client_users(client_id: int):
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50
    while True:
        url = f"{HALO_API_BASE}/Users?$filter=ClientID eq {client_id}&pageSize={page_size}&pageNumber={page}"
        r = session.get(url, headers=h, timeout=10)
        if r.status_code != 200: break
        users = r.json().get("users", [])
        if not users: break
        all_users.extend(users)
        if len(users) < page_size: break
        page += 1
    return all_users

def get_main_users(force=False):
    now = time.time()
    if not force and USER_CACHE["users"] and now - USER_CACHE["timestamp"] < CACHE_TTL:
        return USER_CACHE["users"]
    all_users = fetch_all_client_users(HALO_CLIENT_ID_NUM)
    main_users = [u for u in all_users if str(u.get("site_id")) == str(HALO_SITE_ID) or str(u.get("site_name","")).lower() == "main"]
    USER_CACHE["users"] = main_users
    USER_CACHE["timestamp"] = now
    log.info(f"✅ Cache vernieuwd: {len(main_users)} main users")
    return main_users

def get_halo_user_id(email: str):
    if not email: return None
    users = get_main_users()
    email = email.strip().lower()
    for u in users:
        emails = {
            str(u.get("emailaddress") or "").lower(),
            str(u.get("networklogin") or "").lower(),
            str(u.get("adobject") or "").lower()
        }
        if email in emails:
            return u.get("id")
    return None

# ------------------------------------------------------------------------------
# Halo Ticket helpers
# ------------------------------------------------------------------------------
def create_halo_ticket(summary, name, email, omschrijving, sindswanneer,
                       watwerktniet, zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    log.info(f"🎟️ Ticket aanmaken voor {email} → samenvatting: {summary}")
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
        "UrgencyID": int(urgency_id),
    }
    if requester_id: body["UserID"] = requester_id
    r = session.post(f"{HALO_API_BASE}/Tickets", headers=h, json=body, timeout=10)
    log.info(f"➡️ Halo API response: {r.status_code} {r.text}")
    if r.status_code in (200, 201):
        ticket = r.json()
        return ticket
    else:
        if room_id: send_message(room_id, f"⚠️ Ticketkon niet aangemaakt worden (status {r.status_code})")
        return None

def add_note_to_ticket(ticket_id, text, sender, email=None, room_id=None):
    h = get_halo_headers()
    body = {"Details": text, "ActionTypeID": HALO_ACTIONTYPE_PUBLIC, "IsPrivate": False}
    user_id = get_halo_user_id(email) if email else None
    if user_id: body["UserID"] = user_id
    r = session.post(f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions", headers=h, json=body, timeout=10)
    log.info(f"➡️ Note toevoegen response: {r.status_code} {r.text}")
    if r.status_code not in (200,201) and room_id:
        send_message(room_id, f"⚠️ Kon bericht niet toevoegen aan ticket {ticket_id}.")

# ------------------------------------------------------------------------------
# Webex helpers
# ------------------------------------------------------------------------------
def send_message(room_id, text):
    try:
        session.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json={"roomId": room_id, "markdown": text}, timeout=10)
    except Exception as e:
        log.error(f"❌ Kon geen bericht sturen naar Webex: {e}")

def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul het formulier hieronder in:",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": [
                    {"type": "Input.Text", "id": "name", "placeholder": "Naam"},
                    {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres"},
                    {"type": "Input.Text", "id": "omschrijving", "isMultiline": True, "placeholder": "Probleemomschrijving"},
                    {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Sinds wanneer?"},
                    {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Wat werkt niet?"},
                    {"type": "Input.Text", "id": "zelfgeprobeerd", "isMultiline": True, "placeholder": "Zelf geprobeerd?"},
                    {"type": "Input.Text", "id": "impacttoelichting", "isMultiline": True,"placeholder": "Impact toelichting"},
                ],
                "actions": [{"type": "Action.Submit", "title": "Versturen"}]
            }
        }]}
    session.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=card, timeout=10)

# ------------------------------------------------------------------------------
# Webex Event Processing (background threaded)
# ------------------------------------------------------------------------------
def process_webex_event(data):
    resource = data.get("resource")
    log.info(f"📩 Event ontvangen van Webex: {resource} → {data}")
    if resource == "messages":
        # handle normal messages
        ...
    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        log.info(f"➡️ Ophalen van attachmentAction inputs voor {action_id}")
        resp = session.get(f"https://webexapis.com/v1/attachment/actions/{action_id}", headers=WEBEX_HEADERS, timeout=10)
        log.info(f"➡️ Response {resp.status_code}: {resp.text}")
        inputs = resp.json().get("inputs", {})
        log.info(f"➡️ Parsed inputs: {inputs}")

        # Extract form values
        naam = inputs.get("name", "Onbekend")
        email = inputs.get("email", "")
        omschrijving = inputs.get("omschrijving", "")
        sindswanneer = inputs.get("sindswanneer", "")
        watwerktniet = inputs.get("watwerktniet", "")
        zelfgeprobeerd = inputs.get("zelfgeprobeerd", "")
        impacttoelichting = inputs.get("impacttoelichting", "")
        impact_id = inputs.get("impact", str(HALO_DEFAULT_IMPACT))
        urgency_id = inputs.get("urgency", str(HALO_DEFAULT_URGENCY))
        room_id = data["data"]["roomId"]

        summary = omschrijving or "Melding via Webex"
        ticket = create_halo_ticket(summary, naam, email,
                                    omschrijving, sindswanneer,
                                    watwerktniet, zelfgeprobeerd,
                                    impacttoelichting, impact_id, urgency_id,
                                    room_id=room_id)
        if ticket:
            ticket_room_map[ticket["id"]] = room_id
            send_message(room_id, f"✅ Ticket aangemaakt: **{ticket['Ref']}**")
        else:
            send_message(room_id, "⚠️ Er ging iets mis bij het aanmaken van je ticket.")

@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    threading.Thread(target=process_webex_event, args=(data,)).start()
    return {"status": "ok"}
