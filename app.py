import os, urllib.parse, logging, sys, time, threading, json
from flask import Flask, request
from dotenv import load_dotenv
import requests

# --------------------------------------------------------------------------
# LOGGING
# --------------------------------------------------------------------------
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-api")
log.info("✅ Logging gestart")

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
load_dotenv()
required = ["HALO_AUTH_URL", "HALO_API_BASE", "HALO_CLIENT_ID", "HALO_CLIENT_SECRET"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    log.critical(f"❌ Ontbrekende .env-variabelen: {missing}")
    sys.exit(1)

app = Flask(__name__)

HALO_AUTH_URL  = os.getenv("HALO_AUTH_URL")
HALO_API_BASE  = os.getenv("HALO_API_BASE").rstrip('/')
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID")
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET")
HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", 66))
HALO_CLIENT_ID_NUM  = int(os.getenv("HALO_CLIENT_ID_NUM", 12))
HALO_SITE_ID        = int(os.getenv("HALO_SITE_ID", 18))
WEBEX_TOKEN         = os.getenv("WEBEX_BOT_TOKEN")

WEBEX_HEADERS = (
    {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"}
    if WEBEX_TOKEN else {}
)

USER_CACHE = {"users": [], "timestamp": 0, "source": "none"}
TICKET_ROOM_MAP = {}   # roomId <-> ticketId
CACHE_DURATION = 24 * 60 * 60  # 24 uur
MAX_PAGES = 10

# --------------------------------------------------------------------------
# HALO AUTH
# --------------------------------------------------------------------------
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all",
    }
    r = requests.post(
        HALO_AUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(payload),
        timeout=10,
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

# --------------------------------------------------------------------------
# USERS (met volledige paginering)
# --------------------------------------------------------------------------
def fetch_users(client_id: int, site_id: int):
    h = get_halo_headers()
    all_users = []
    page = 1
    page_size = 50
    page_count = 0
    while page_count < MAX_PAGES:
        params = {
            "client_id": client_id,
            "site_id": site_id,
            "page": page,
            "page_size": page_size,
        }
        log.info(f"➡️ Fetching users page {page}")
        r = requests.get(f"{HALO_API_BASE}/api/Users", headers=h, params=params, timeout=15)
        if r.status_code != 200:
            log.warning(f"⚠️ /api/Users page {page} gaf {r.status_code}: {r.text[:200]}")
            break

        response_json = r.json()
        users = []
        if isinstance(response_json, list):
            users = response_json
        elif isinstance(response_json, dict):
            users = response_json.get("users", []) or response_json.get("items", []) or response_json.get("data", [])

        if not users:
            break

        for u in users:
            if "id" in u:
                u["id"] = int(u["id"])
            if "client_id" in u:
                u["client_id"] = int(u["client_id"])
            if "site_id" in u:
                u["site_id"] = int(u["site_id"])
            if (
                u.get("use") == "user"
                and not u.get("inactive", True)
                and u.get("emailaddress")
                and "@" in u["emailaddress"]
            ):
                all_users.append(u)

        if len(users) < page_size:
            break
        page += 1
        page_count += 1

    USER_CACHE["source"] = "/api/Users (paginated)"
    USER_CACHE["users"] = all_users
    USER_CACHE["timestamp"] = time.time()
    log.info(f"✅ {len(all_users)} gebruikers opgehaald")
    return all_users

def get_users():
    now = time.time()
    if USER_CACHE["users"] and (now - USER_CACHE["timestamp"] < CACHE_DURATION):
        return USER_CACHE["users"]
    return fetch_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)

def get_user(email: str):
    if not email:
        return None
    email = email.lower().strip()
    for u in get_users():
        for f in ["EmailAddress","emailaddress","PrimaryEmail","login","email","email1"]:
            if u.get(f) and u[f].lower() == email:
                return u
    return None

# --------------------------------------------------------------------------
# WEBEX HELPERS
# --------------------------------------------------------------------------
def send_message(room_id: str, text: str):
    if not WEBEX_HEADERS: return
    try:
        requests.post(
            "https://webexapis.com/v1/messages",
            headers=WEBEX_HEADERS,
            json={"roomId": room_id, "markdown": text},
            timeout=10,
        )
    except Exception as e:
        log.error(f"❌ Webex send: {e}")

def send_adaptive_card(room_id):
    payload = {
        "roomId": room_id,
        "text": "✍ Vul dit formulier in:",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.0",
                "body": [
                    {"type": "TextBlock", "text": "🆕 Nieuwe melding", "weight": "bolder"},
                    {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres", "required": True},
                    {"type": "Input.Text", "id": "omschrijving", "placeholder": "Korte omschrijving", "required": True},
                    {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Sinds wanneer?"},
                    {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Wat werkt niet?"},
                    {"type": "Input.Text", "id": "zelfgeprobeerd", "placeholder": "Wat heb je geprobeerd?"},
                    {"type": "Input.ChoiceSet", "id": "impact", "label": "Impact",
                     "choices":[
                         {"title":"Gehele bedrijf (1)","value":"1"},
                         {"title":"Meerdere gebruikers (2)","value":"2"},
                         {"title":"Één gebruiker (3)","value":"3"}],
                     "value":"3","required":True},
                    {"type": "Input.ChoiceSet", "id": "urgency", "label": "Urgentie",
                     "choices":[
                         {"title":"High (1)","value":"1"},
                         {"title":"Medium (2)","value":"2"},
                         {"title":"Low (3)","value":"3"}],
                     "value":"3","required":True}
                ],
                "actions":[{"type":"Action.Submit","title":"✅ Ticket aanmaken"}]
            }
        }]
    }
    try:
        requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=payload, timeout=10)
    except Exception as e:
        log.error(f"❌ Adaptive card versturen mislukt: {e}")

# --------------------------------------------------------------------------
# HALO TICKETS + NOTES
# --------------------------------------------------------------------------
def create_halo_ticket(form, room_id):
    h = get_halo_headers()
    user = get_user(form["email"])
    if not user:
        send_message(room_id, "❌ Geen gebruiker gevonden in Halo.")
        return

    details = (
        f"### 📝 Nieuwe melding details\n\n"
        f"- **Omschrijving:** {form['omschrijving']}\n"
        f"- **Sinds wanneer:** {form.get('sindswanneer','-')}\n"
        f"- **Wat werkt niet:** {form.get('watwerktniet','-')}\n"
        f"- **Zelf geprobeerd:** {form.get('zelfgeprobeerd','-')}\n"
    )

    body = {
        "summary": form["omschrijving"][:100],
        "details": details,
        "tickettype_id": HALO_TICKET_TYPE_ID,
        "impact": int(form.get("impact", "3")),
        "urgency": int(form.get("urgency", "3")),
        "client_id": int(user.get("client_id", HALO_CLIENT_ID_NUM)),
        "site_id": int(user.get("site_id", HALO_SITE_ID)),
        "user_id": int(user["id"]),
    }

    url = f"{HALO_API_BASE}/api/Tickets"
    log.info(f"➡️ Creating ticket to {url}")

    r = requests.post(url, headers=h, json=[body], timeout=20)
    if not r.ok:
        log.error(f"❌ Ticket aanmaken mislukt ({r.status_code}) - {r.text}")
        send_message(room_id, f"⚠️ Ticket aanmaken mislukt: {r.status_code}")
        return None

    resp = r.json()
    ticket = resp[0] if isinstance(resp, list) else resp.get("data") or resp
    tid = str(ticket.get("id") or ticket.get("TicketID") or "")
    if not tid:
        send_message(room_id, "❌ Ticket aangemaakt, maar geen ID gevonden.")
        return None

    TICKET_ROOM_MAP[room_id] = tid
    send_message(room_id, f"✅ Ticket aangemaakt: **{tid}**")
    log.info(f"✅ Ticket {tid} opgeslagen voor room {room_id}")
    return tid


def add_public_note(ticket_id, text):
    """Voeg publieke notitie toe aan bestaand ticket (case-sensitive pad!)."""
    h = get_halo_headers()
    url = f"{HALO_API_BASE}/api/Tickets/{ticket_id}/Notes"
    note_data = {"text": text, "is_public": True}
    log.info(f"➡️ POST {url}")
    r = requests.post(url, headers=h, json=note_data, timeout=15)
    if not r.ok:
        log.error(f"❌ Notitie toevoegen mislukt: {r.status_code} - {r.text}")
        return False
    log.info(f"✅ Notitie toegevoegd aan ticket {ticket_id}")
    return True

# --------------------------------------------------------------------------
# WEBEX EVENTS
# --------------------------------------------------------------------------
def process_webex_event(payload):
    res = payload.get("resource")
    if res == "messages":
        mid = payload["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{mid}", headers=WEBEX_HEADERS).json()
        text = msg.get("text", "")
        room_id = msg.get("roomId")
        sender = msg.get("personEmail", "")
        if sender and sender.endswith("@webex.bot"):
            return
        if "nieuwe melding" in text.lower():
            send_adaptive_card(room_id)
        elif room_id in TICKET_ROOM_MAP:
            if add_public_note(TICKET_ROOM_MAP[room_id], f"💬 **Van gebruiker:** {text}"):
                send_message(room_id, "📝 Bericht toegevoegd aan Halo als public note.")
    elif res == "attachmentActions":
        a_id = payload["data"]["id"]
        inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{a_id}", headers=WEBEX_HEADERS).json().get("inputs", {})
        create_halo_ticket(inputs, payload["data"]["roomId"])

# --------------------------------------------------------------------------
# HALO ACTION BUTTON WEBHOOK
# --------------------------------------------------------------------------
@app.route("/halo-action", methods=["POST"])
def halo_action():
    data = request.json if request.is_json else request.form.to_dict()
    log.info(f"📥 Halo action webhook: {json.dumps(data, indent=2)}")
    tid = str(data.get("ticket_id") or data.get("TicketID") or data.get("id") or "")
    note_text = data.get("note") or data.get("text") or ""
    if not tid or not note_text:
        log.warning("❌ Onvoldoende velden in action webhook.")
        return {"status": "ignore"}

    for room_id, stored_tid in TICKET_ROOM_MAP.items():
        if str(stored_tid) == tid:
            send_message(room_id, f"📥 **Nieuwe public note vanuit Halo:**\n{note_text}")
            return {"status": "ok"}
    log.warning(f"❌ Geen Webex-room gevonden voor ticket {tid}")
    return {"status": "ok"}

# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------
@app.route("/webex", methods=["POST"])
def webex_hook():
    threading.Thread(target=process_webex_event, args=(request.json,)).start()
    return {"status": "ok"}

@app.route("/initialize", methods=["GET"])
def initialize():
    get_users()
    return {"status":"initialized","cache_size":len(USER_CACHE['users']),"source":USER_CACHE["source"]}

# --------------------------------------------------------------------------
# START SERVER
# --------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Start server op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
