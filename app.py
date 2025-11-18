import os, urllib.parse, logging, sys, time, threading, json, re
from flask import Flask, request
from dotenv import load_dotenv
import requests

# --------------------------------------------------------------------------
# LOGGING
# --------------------------------------------------------------------------
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("halo-api")
log.info("✅ Logging gestart")

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
load_dotenv()
required = ["HALO_AUTH_URL","HALO_API_BASE","HALO_CLIENT_ID","HALO_CLIENT_SECRET"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    log.critical(f"❌ Ontbrekende .env: {missing}")
    sys.exit(1)

app = Flask(__name__)
HALO_AUTH_URL  = os.getenv("HALO_AUTH_URL")
HALO_API_BASE  = os.getenv("HALO_API_BASE").rstrip('/')
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID")
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET")
HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", 66))
HALO_CLIENT_ID_NUM  = int(os.getenv("HALO_CLIENT_ID_NUM", 12))
HALO_SITE_ID        = int(os.getenv("HALO_SITE_ID", 18))
ACTION_ID_PUBLIC    = int(os.getenv("ACTION_ID_PUBLIC", 145))
WEBEX_TOKEN         = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"} if WEBEX_TOKEN else {}

if not WEBEX_TOKEN:
    log.critical("❌ WEBEX_BOT_TOKEN ontbreekt")
    sys.exit(1)

USER_CACHE = {"users": [], "timestamp": 0, "source": "none"}
USER_TICKET_MAP = {}
TICKET_STATUS_TRACKER = {}
CACHE_DURATION = 24 * 60 * 60

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
        data=urllib.parse.urlencode(payload), timeout=10)
    r.raise_for_status()
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# --------------------------------------------------------------------------
# USERS
# --------------------------------------------------------------------------
def fetch_users(client_id, site_id):
    h = get_halo_headers()
    all_users = []
    page_no = 1
    while True:
        params = {
            "client_id": client_id, "site_id": site_id,
            "pageinate": True, "page_size": 100, "page_no": page_no}
        r = requests.get(f"{HALO_API_BASE}/api/users", headers=h, params=params, timeout=15)
        if r.status_code != 200:
            log.error(f"❌ Users fetch failed: {r.status_code} - {r.text}")
            break
        js = r.json()
        users = []
        if isinstance(js, list):
            users = js
        elif isinstance(js, dict):
            users = js.get("users") or js.get("data") or js.get("items") or []
        if not users:
            break
        for u in users:
            if "id" in u:
                u["id"] = int(u["id"])
            mail = u.get("emailaddress") or u.get("EmailAddress")
            if u.get("use") == "user" and not u.get("inactive") and mail and "@" in mail:
                all_users.append(u)
        if len(users) < 100:
            break
        page_no += 1
    USER_CACHE.update({"users": all_users, "timestamp": time.time(), "source": f"client{client_id}_site{site_id}"})
    log.info(f"✅ {len(all_users)} gebruikers gecached")
    return all_users

def get_users():
    if USER_CACHE["users"] and time.time() - USER_CACHE["timestamp"] < CACHE_DURATION:
        return USER_CACHE["users"]
    return fetch_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)

def get_user(email):
    if not email:
        return None
    email = email.lower().strip()
    for u in get_users():
        for f in ["EmailAddress", "emailaddress", "PrimaryEmail", "login", "email", "email1"]:
            if u.get(f) and u[f].lower() == email:
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
        log.error(f"Webex send error: {e}")

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
                    {"type": "Input.ChoiceSet", "id": "impact", "label": "Impact",
                     "choices": [
                         {"title": "Gehele bedrijf (1)", "value": "1"},
                         {"title": "Meerdere gebruikers (2)", "value": "2"},
                         {"title": "Één gebruiker (3)", "value": "3"}
                     ],
                     "value": "3", "required": True},
                    {"type": "Input.ChoiceSet", "id": "urgency", "label": "Urgency",
                     "choices": [
                         {"title": "High (1)", "value": "1"},
                         {"title": "Medium (2)", "value": "2"},
                         {"title": "Low (3)", "value": "3"}
                     ],
                     "value": "3", "required": True}
                ],
                "actions": [{"type": "Action.Submit", "title": "✅ Ticket aanmaken"}]
            }
        }]
    }
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=payload, timeout=10)

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
        "details": f"Nieuwe melding uit Webex\n{json.dumps(form,indent=2)}",
        "tickettype_id": HALO_TICKET_TYPE_ID,
        "impact": int(form.get("impact", "3")),
        "urgency": int(form.get("urgency", "3")),
        "client_id": int(user.get("client_id", HALO_CLIENT_ID_NUM)),
        "site_id": int(user.get("site_id", HALO_SITE_ID)),
        "user_id": int(user["id"])
    }
    # FIX: Gebruik 'Tickets' in plaats van 'tickets' (case-sensitive endpoint)
    url = f"{HALO_API_BASE}/api/Tickets?bulkresponse=true"
    try:
        r = requests.post(url, headers=h, json=body, timeout=20)
    except Exception as e:
        log.error(f"Halo connection error: {e}")
        send_message(room_id, f"💥 Verbinding met Halo mislukt: {e}")
        return
    if not r.ok:
        log.error(f"Halo API error: {r.status_code} - {r.text}")
        send_message(room_id, f"⚠️ Ticket aanmaken mislukt ({r.status_code})\n{r.text[:200]}")
        return
    t = r.json()
    tid = str(t.get("TicketNumber") or t.get("id") or t.get("TicketID"))
    USER_TICKET_MAP.setdefault(room_id, []).append(tid)
    TICKET_STATUS_TRACKER[tid] = {
        "status": t.get("StatusName") or t.get("status", "Unknown"),
        "last_note": 0
    }
    send_message(room_id, f"✅ Ticket aangemaakt: **#{tid}**")

# --------------------------------------------------------------------------
# NOTES + STATUS
# --------------------------------------------------------------------------
def add_public_note(ticket_id, text):
    h = get_halo_headers()
    url = f"{HALO_API_BASE}/api/Actions"
    payload = [{"Ticket_Id": int(ticket_id), "ActionId": ACTION_ID_PUBLIC, "outcome": text}]
    r = requests.post(url, headers=h, json=payload, timeout=15)
    return r.status_code in [200, 201]

def check_ticket_status_and_notes():
    h = get_halo_headers()
    for tid, track in list(TICKET_STATUS_TRACKER.items()):
        try:
            t = requests.get(f"{HALO_API_BASE}/api/Tickets/{tid}",
                headers=h, params={"includedetails": True}, timeout=10)
            if t.ok:
                js = t.json()
                cur = js.get("StatusName") or js.get("status", "Unknown")
                if cur != track["status"]:
                    track["status"] = cur
                    for rid, ids in USER_TICKET_MAP.items():
                        if tid in ids:
                            send_message(rid, f"⚠️ Ticket #{tid} status → {cur}")
            a = requests.get(f"{HALO_API_BASE}/api/Actions",
                headers=h, params={"ticket_id": tid, "conversationonly": True,
                "excludesys": True, "excludeprivate": False, "count": 3}, timeout=10)
            if a.ok:
                acts = a.json().get("actions") or a.json().get("data") or []
                if acts:
                    latest = acts[-1]
                    note = latest.get("outcome") or latest.get("note") or ""
                    if note and note != track.get("last_note_text"):
                        track["last_note_text"] = note
                        for rid, ids in USER_TICKET_MAP.items():
                            if tid in ids:
                                send_message(rid, f"🗒 Nieuwe note in Halo #{tid}\n{note}")
        except Exception as e:
            log.error(f"Status check error for {tid}: {e}")

def status_check_loop():
    while True:
        check_ticket_status_and_notes()
        time.sleep(60)

# --------------------------------------------------------------------------
# WEBEX EVENTS
# --------------------------------------------------------------------------
def process_webex_event(payload):
    res = payload.get("resource")
    if res != "messages":
        return
    mid = payload["data"]["id"]
    msg = requests.get(f"https://webexapis.com/v1/messages/{mid}", headers=WEBEX_HEADERS).json()
    text = msg.get("text", "")
    room_id = msg.get("roomId")
    sender = msg.get("personEmail", "")
    if sender.endswith("@webex.bot"):
        return
    if "nieuwe melding" in text.lower():
        send_message(room_id, "👋 Hi! Klik hieronder om een ticket te maken:")
        send_adaptive_card(room_id)
        return
    ticket = re.search(r'Ticket #(\d+)', text)
    if ticket:
        tid = ticket.group(1)
        if any(tid in t for t in USER_TICKET_MAP.values()):
            add_public_note(tid, text)
            send_message(room_id, f"📝 Note toegevoegd aan #{tid}.")
        else:
            send_message(room_id, f"❌ Ticket #{tid} niet gevonden.")
        return
    if room_id in USER_TICKET_MAP:
        for tid in USER_TICKET_MAP[room_id]:
            add_public_note(tid, text)
        send_message(room_id, "📝 Bericht toegevoegd aan jouw tickets.")
    else:
        send_message(room_id, "ℹ️ Geen tickets in deze room. Typ 'nieuwe melding'.")

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
    log.info(f"🚀 Start server op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
