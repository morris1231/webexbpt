import os, urllib.parse, logging, sys, time, threading, json, re
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

WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}",
                 "Content-Type": "application/json"} if WEBEX_TOKEN else {}

ACTION_ID_PUBLIC = int(os.getenv("ACTION_ID_PUBLIC", 145))
NOTE_FIELD_NAME  = os.getenv("NOTE_FIELD_NAME", "Note")

USER_CACHE = {"users": [], "timestamp": 0, "source": "none"}
USER_TICKET_MAP = {}   # {user_email: {room_id: [ticket_id,...]}}
TICKET_STATUS_TRACKER = {}  # {ticket_id: {status, last_note}}
CACHE_DURATION = 24 * 60 * 60

# --------------------------------------------------------------------------
# Controleer of WEBEX_TOKEN is ingesteld
# --------------------------------------------------------------------------
if not WEBEX_TOKEN:
    log.error("❌ WEBEX_BOT_TOKEN is niet ingesteld in .env bestand")
    sys.exit(1)
else:
    log.info("✅ Webex bot token is ingesteld")

# --------------------------------------------------------------------------
# HALO AUTH
# --------------------------------------------------------------------------
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    r = requests.post(HALO_AUTH_URL,
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data=urllib.parse.urlencode(payload),
                      timeout=10)
    r.raise_for_status()
    token_info = r.json()
    return {
        "Authorization": f"Bearer {token_info['access_token']}",
        "Content-Type": "application/json"
    }

# --------------------------------------------------------------------------
# USERS (correcte paginering tot 127)
# --------------------------------------------------------------------------
def fetch_users(client_id, site_id):
    h = get_halo_headers()
    all_users = []
    page_no = 1
    page_size = 100
    while True:
        params = {
            "client_id": client_id,
            "site_id": site_id,
            "pageinate": True,
            "page_size": page_size,
            "page_no": page_no
        }
        log.info(f"➡️ Haal users pagina {page_no}")
        r = requests.get(f"{HALO_API_BASE}/api/users", headers=h, params=params, timeout=15)
        if r.status_code != 200:
            log.warning(f"⚠️ {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        users = []
        if isinstance(data, list):
            users = data
        elif isinstance(data, dict):
            users = data.get("users") or data.get("items") or data.get("data") or []
        if not users:
            break
        for u in users:
            if "id" in u:
                u["id"] = int(u["id"])
            if u.get("use") == "user" and not u.get("inactive", True):
                mail = u.get("emailaddress") or u.get("EmailAddress")
                if mail and "@" in mail:
                    all_users.append(u)
        log.info(f"📦 Totaal {len(all_users)} users na pagina {page_no}")
        if len(users) < page_size:
            break
        page_no += 1
    USER_CACHE["users"] = all_users
    USER_CACHE["timestamp"] = time.time()
    USER_CACHE["source"] = f"client{client_id}_site{site_id}"
    log.info(f"✅ {len(all_users)} gebruikers opgehaald en gecached")
    return all_users

def get_users():
    now = time.time()
    if USER_CACHE["users"] and (now - USER_CACHE["timestamp"] < CACHE_DURATION):
        return USER_CACHE["users"]
    return fetch_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)

def get_user(email):
    if not email: return None
    email = email.lower().strip()
    for u in get_users():
        for veld in ["EmailAddress", "emailaddress", "PrimaryEmail", "login", "email", "email1"]:
            if u.get(veld) and u[veld].lower() == email:
                return u
    return None

# --------------------------------------------------------------------------
# WEBEX HELPERS
# --------------------------------------------------------------------------
def send_message(room_id, text):
    try:
        requests.post("https://webexapis.com/v1/messages",
                      headers=WEBEX_HEADERS,
                      json={"roomId": room_id, "markdown": text}, timeout=10)
    except Exception as e:
        log.error(f"Webex send mislukte: {e}")

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
                    {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres van gebruiker", "required": True},
                    {"type": "Input.Text", "id": "omschrijving", "placeholder": "Korte omschrijving", "required": True},
                    {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Sinds wanneer?"},
                    {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Wat werkt niet?"},
                    {"type": "Input.Text", "id": "zelfgeprobeerd", "placeholder": "Wat heb je al geprobeerd?"},
                    {"type": "Input.Text", "id": "impacttoelichting", "placeholder": "Impact toelichting (optioneel)"},
                    {"type": "Input.ChoiceSet", "id": "impact", "label": "Impact",
                     "choices": [
                         {"title": "Gehele bedrijf (1)", "value": "1"},
                         {"title": "Meerdere gebruikers (2)", "value": "2"},
                         {"title": "Één gebruiker (3)", "value": "3"}],
                     "value": "3", "required": True},
                    {"type": "Input.ChoiceSet", "id": "urgency", "label": "Urgency",
                     "choices": [
                         {"title": "High (1)", "value": "1"},
                         {"title": "Medium (2)", "value": "2"},
                         {"title": "Low (3)", "value": "3"}],
                     "value": "3", "required": True}
                ],
                "actions": [{"type": "Action.Submit", "title": "✅ Ticket aanmaken"}]
            }
        }]
    }
    try:
        requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=payload, timeout=10)
    except Exception as e:
        log.error(f"Adaptive card versturen mislukte: {e}")

# --------------------------------------------------------------------------
# HALO TICKETS
# --------------------------------------------------------------------------
def create_halo_ticket(form, room_id):
    h = get_halo_headers()
    user = get_user(form["email"])
    if not user:
        send_message(room_id, "❌ Geen gebruiker gevonden in Halo.")
        return
    body = {
        "summary": form["omschrijving"][:100],
        "details": f"Nieuwe melding: {json.dumps(form, indent=2)}",
        "tickettype_id": HALO_TICKET_TYPE_ID,
        "impact": int(form.get("impact", "3")),
        "urgency": int(form.get("urgency", "3")),
        "client_id": int(user.get("client_id", HALO_CLIENT_ID_NUM)),
        "site_id": int(user.get("site_id", HALO_SITE_ID)),
        "user_id": int(user["id"])
    }
    url = f"{HALO_API_BASE}/api/tickets"
    r = requests.post(url, headers=h, json=[body], timeout=20)
    if not r.ok:
        send_message(room_id, f"⚠️ Ticket aanmaken mislukt ({r.status_code})")
        return
    t = r.json()[0] if isinstance(r.json(), list) else r.json()
    tid = str(t.get("TicketNumber") or t.get("id") or t.get("TicketID"))
    if room_id not in USER_TICKET_MAP:
        USER_TICKET_MAP[room_id] = []
    USER_TICKET_MAP[room_id].append(tid)
    TICKET_STATUS_TRACKER[tid] = {"status": t.get("status", "Unknown"), "last_note": 0}
    send_message(room_id, f"✅ Ticket aangemaakt: **#{tid}**")

# --------------------------------------------------------------------------
# PUBLIC NOTE
# --------------------------------------------------------------------------
def add_public_note(ticket_id, text):
    h = get_halo_headers()
    url = f"{HALO_API_BASE}/api/Actions"
    payload = [{"Ticket_Id": int(ticket_id), "ActionId": ACTION_ID_PUBLIC, "outcome": text}]
    r = requests.post(url, headers=h, json=payload, timeout=15)
    return r.status_code in [200, 201]

# --------------------------------------------------------------------------
# STATUS + NOTES
# --------------------------------------------------------------------------
def check_ticket_status_and_notes():
    h = get_halo_headers()
    for tid, track in list(TICKET_STATUS_TRACKER.items()):
        try:
            t_resp = requests.get(f"{HALO_API_BASE}/api/Tickets/{tid}",
                                  headers=h, params={"includedetails": True}, timeout=10)
            if t_resp.ok:
                t = t_resp.json()
                cur_status = t.get("StatusName") or t.get("status", "Unknown")
                if cur_status != track["status"]:
                    track["status"] = cur_status
                    for rid, ids in USER_TICKET_MAP.items():
                        if tid in ids:
                            send_message(rid, f"⚠️ **Ticket #{tid} status gewijzigd → {cur_status}**")
            a_resp = requests.get(f"{HALO_API_BASE}/api/Actions",
                                  headers=h,
                                  params={"ticket_id": tid, "conversationonly": True,
                                          "excludesys": True, "excludeprivate": False, "count": 3},
                                  timeout=10)
            if a_resp.ok:
                actions = a_resp.json().get("actions") or a_resp.json().get("data") or []
                if actions:
                    latest = actions[-1]
                    note = latest.get("outcome") or latest.get("note") or ""
                    stamp = time.time()
                    if stamp > track.get("last_note", 0):
                        track["last_note"] = stamp
                        for rid, ids in USER_TICKET_MAP.items():
                            if tid in ids:
                                send_message(rid, f"🗒 **Nieuwe note vanuit Halo**\n{note}")
        except Exception as e:
            log.error(f"Check fout {tid}: {e}")

def status_check_loop():
    while True:
        try:
            check_ticket_status_and_notes()
        except Exception as e:
            log.error(f"💥 Loop fout: {e}")
        time.sleep(60)

# --------------------------------------------------------------------------
# WEBEX EVENTS  –  Vragenlijst & berichten
# --------------------------------------------------------------------------
def process_webex_event(payload):
    res = payload.get("resource")
    if res != "messages": return
    mid = payload["data"]["id"]
    msg = requests.get(f"https://webexapis.com/v1/messages/{mid}", headers=WEBEX_HEADERS).json()
    text = msg.get("text", "")
    room_id = msg.get("roomId")
    sender = msg.get("personEmail", "")
    if sender.endswith("@webex.bot"):  # eigen bericht
        return
    if "nieuwe melding" in text.lower():
        send_message(room_id, "👋 Hi! Klik hieronder om je melding te maken:")
        send_adaptive_card(room_id)
        return

    ticket_match = re.search(r'Ticket #(\d+)', text)
    if ticket_match:
        tid = ticket_match.group(1)
        if any(tid in tickets for tickets in USER_TICKET_MAP.values()):
            add_public_note(tid, text)
            send_message(room_id, f"📝 Bericht toegevoegd aan ticket #{tid}.")
        else:
            send_message(room_id, f"❌ Ticket #{tid} niet gevonden in deze room.")
        return

    # standaard: voeg note toe aan alle tickets in room
    if room_id in USER_TICKET_MAP:
        for tid in USER_TICKET_MAP[room_id]:
            add_public_note(tid, text)
        send_message(room_id, "📝 Bericht toegevoegd aan jouw tickets.")
    else:
        send_message(room_id, "ℹ️ Geen tickets gevonden. Typ 'nieuwe melding' om te starten.")

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
    threading.Thread(target=status_check_loop, daemon=True).start()
    return {"status": "initialized", "users": len(USER_CACHE['users'])}

# --------------------------------------------------------------------------
# START SERVER
# --------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Start server op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
