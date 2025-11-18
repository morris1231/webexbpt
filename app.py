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
USER_CACHE = {"users": [], "timestamp": 0, "source": "none"}
# Nu: {user_email: {room_id: [ticket_id1, ticket_id2, ...]}}
USER_TICKET_MAP = {}
# Om statuswijzigingen te detecteren: {ticket_id: {status: "Oud status", last_checked: timestamp}}
TICKET_STATUS_TRACKER = {}
CACHE_DURATION = 24 * 60 * 60
MAX_PAGES = 10

# Nieuwe variabelen voor HALO actie-ID en notitieveld
ACTION_ID_PUBLIC = int(os.getenv("ACTION_ID_PUBLIC", 145))
NOTE_FIELD_NAME = os.getenv("NOTE_FIELD_NAME", "Note")

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
    log.info("➡️ Verbinding maken met HALO auth endpoint")
    r = requests.post(HALO_AUTH_URL,
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data=urllib.parse.urlencode(payload),
                      timeout=10)
    r.raise_for_status()
    token_info = r.json()
    log.info(f"✅ HALO auth succesvol: token expires in {token_info.get('expires_in', 'onbekend')} seconden")
    return {"Authorization": f"Bearer {token_info['access_token']}",
            "Content-Type": "application/json"}

# --------------------------------------------------------------------------
# USERS
# --------------------------------------------------------------------------
def fetch_users(client_id, site_id):
    h = get_halo_headers()
    all_users = []
    page = 1
    page_size = 50
    page_count = 0
    while page_count < MAX_PAGES:
        params = {"client_id": client_id, "site_id": site_id, "page": page, "page_size": page_size}
        log.info(f"➡️ Fetching users page {page}")
        r = requests.get(f"{HALO_API_BASE}/api/users", headers=h, params=params, timeout=15)
        if r.status_code != 200:
            log.warning(f"⚠️ /api/users pagina {page} gaf {r.status_code}: {r.text[:200]}")
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
            if "id" in u: u["id"] = int(u["id"])
            if "client_id" in u: u["client_id"] = int(u["client_id"])
            if "site_id" in u: u["site_id"] = int(u["site_id"])
            if (
                u.get("use") == "user" and
                not u.get("inactive", True) and
                u.get("emailaddress") and
                "@" in u["emailaddress"]
            ):
                all_users.append(u)
        if len(users) < page_size:
            break
        page += 1
        page_count += 1
    USER_CACHE["source"] = "/api/users (paginated)"
    USER_CACHE["timestamp"] = time.time()
    USER_CACHE["users"] = all_users
    log.info(f"✅ {len(all_users)} gebruikers opgehaald")
    return all_users

def get_users():
    now = time.time()
    if USER_CACHE["users"] and (now - USER_CACHE["timestamp"] < CACHE_DURATION):
        return USER_CACHE["users"]
    return fetch_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)

def get_user(email):
    if not email:
        return None
    email = email.lower().strip()
    for u in get_users():
        for field in ["EmailAddress", "emailaddress", "PrimaryEmail", "login", "email", "email1"]:
            if u.get(field) and u[field].lower() == email:
                return u
    return None

# --------------------------------------------------------------------------
# WEBEX HELPERS
# --------------------------------------------------------------------------
def send_message(room_id, text):
    if not WEBEX_HEADERS:
        log.error("❌ WEBEX_HEADERS is niet ingesteld")
        return
    try:
        log.info(f"➡️ Sturen Webex bericht naar room {room_id}: '{text[:50]}...'")
        requests.post("https://webexapis.com/v1/messages",
                      headers=WEBEX_HEADERS,
                      json={"roomId": room_id, "markdown": text}, timeout=10)
        log.info(f"✅ Webex bericht verstuurd naar room {room_id}")
    except Exception as e:
        log.error(f"❌ Webex send: {e}")

def send_adaptive_card(room_id):
    if not WEBEX_HEADERS:
        log.error("❌ WEBEX_HEADERS is niet ingesteld")
        return
    log.info(f"➡️ Sturen adaptive card naar room {room_id}")
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
        requests.post("https://webexapis.com/v1/messages",
                      headers=WEBEX_HEADERS, json=payload, timeout=10)
        log.info(f"✅ Adaptive card verstuurd naar room {room_id}")
    except Exception as e:
        log.error(f"❌ Adaptive card versturen mislukt: {e}")

# --------------------------------------------------------------------------
# HALO TICKETS
# --------------------------------------------------------------------------
def create_halo_ticket(form, room_id):
    if not WEBEX_HEADERS:
        log.error("❌ WEBEX_HEADERS is niet ingesteld")
        return
    h = get_halo_headers()
    user = get_user(form["email"])
    if not user:
        send_message(room_id, "❌ Geen gebruiker gevonden in Halo.")
        return
    log.info(f"✅ Gebruiker gevonden: {user.get('emailaddress')}")
    details = (
        "### 📝 Nieuwe melding details\n\n"
        f"- **Omschrijving:** {form['omschrijving']}\n"
        f"- **Sinds wanneer:** {form.get('sindswanneer', '-')}\n"
        f"- **Wat werkt niet:** {form.get('watwerktniet', '-')}\n"
        f"- **Zelf geprobeerd:** {form.get('zelfgeprobeerd', '-')}\n"
    )
    if form.get('impacttoelichting', '').strip():
        details += f"- **Impact toelichting:** {form['impacttoelichting']}\n"
    body = {
        "summary": form["omschrijving"][:100],
        "details": details,
        "tickettype_id": HALO_TICKET_TYPE_ID,
        "impact": int(form.get("impact", "3")),
        "urgency": int(form.get("urgency", "3")),
        "client_id": int(user.get("client_id", HALO_CLIENT_ID_NUM)),
        "site_id": int(user.get("site_id", HALO_SITE_ID)),
        "user_id": int(user["id"])
    }
    url = f"{HALO_API_BASE}/api/tickets"
    log.info(f"➡️ Creëer Halo ticket met body: {json.dumps(body, indent=2)}")
    r = requests.post(url, headers=h, json=[body], timeout=20)
    if not r.ok:
        send_message(room_id, f"⚠️ Ticket aanmaken mislukt: {r.status_code}")
        log.error(f"❌ Halo ticket aanmaken mislukt: {r.status_code} - {r.text}")
        return
    response = r.json()
    if isinstance(response, list) and response:
        ticket = response[0]
    elif isinstance(response, dict):
        ticket = response.get("data") or response.get("tickets", [None])[0] or response
    else:
        ticket = response
    tid = str(ticket.get("TicketNumber") or ticket.get("id") or ticket.get("TicketID") or "")
    if not tid:
        send_message(room_id, "❌ Ticket aangemaakt, maar geen ID gevonden")
        log.error("❌ Geen ticket ID gevonden in Halo response")
        return
    log.info(f"✅ Ticket aangemaakt: {tid}")
    # Maak een nieuwe room voor deze gebruiker als deze nog niet bestaat
    user_email = user.get("emailaddress", form["email"]).lower()
    log.info(f"ℹ️ Gebruiker email: {user_email}")
    # Als de gebruiker nog geen tickets heeft, maak dan een nieuwe room aan
    if user_email not in USER_TICKET_MAP:
        USER_TICKET_MAP[user_email] = {}
    # Zorg dat de room_id in USER_TICKET_MAP staat
    if room_id not in USER_TICKET_MAP[user_email]:
        USER_TICKET_MAP[user_email][room_id] = []
    # Voeg het ticket toe aan de room
    USER_TICKET_MAP[user_email][room_id].append(tid)
    send_message(room_id, f"✅ Ticket aangemaakt: **{tid}**")
    log.info(f"✅ Ticket {tid} toegevoegd aan room {room_id} voor gebruiker {user_email}")
    return tid

# --------------------------------------------------------------------------
# PUBLIC NOTE FUNCTIE (CORRECTE IMPLEMENTATIE)
# --------------------------------------------------------------------------
def add_public_note(ticket_id, text):
    """Public note toevoegen via HALO Actions API (met Ticket_Id met underscore)"""
    if not WEBEX_HEADERS:
        log.error("❌ WEBEX_HEADERS is niet ingesteld")
        return
    h = get_halo_headers()
    url = f"{HALO_API_BASE}/api/Actions"
    payload = [
        {
            "Ticket_Id": int(ticket_id),  # MET UNDERSCORE - zoals jij nodig hebt
            "ActionId": ACTION_ID_PUBLIC,
            "outcome": text  # Note tekst in 'outcome' veld
        }
    ]
    log.info(f"➡️ Sturen public note naar Halo voor ticket {ticket_id}: {text}")
    try:
        r = requests.post(url, headers=h, json=payload, timeout=15)
        if r.status_code in [200, 201]:
            log.info(f"✅ Public note succesvol toegevoegd aan ticket {ticket_id}")
            return True
        else:
            log.error(f"❌ Public note mislukt: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        log.error(f"💥 Fout bij public note: {e}")
        return False

# --------------------------------------------------------------------------
# STATUS WIJZIGINGEN
# --------------------------------------------------------------------------
def check_ticket_status_changes():
    """Controleer statuswijzigingen voor alle tickets in de tracker"""
    h = get_halo_headers()
    for ticket_id, status_info in list(TICKET_STATUS_TRACKER.items()):
        try:
            # Haal de huidige status van het ticket op
            url = f"{HALO_API_BASE}/api/Tickets/{ticket_id}"
            log.info(f"➡️ Controleer status van ticket {ticket_id}")
            r = requests.get(url, headers=h, timeout=10)
            if r.status_code == 200:
                ticket_data = r.json()
                current_status = ticket_data.get("status", "Unknown")
                # Controleer of de status is gewijzigd
                if current_status != status_info["status"]:
                    # Update de status in de tracker
                    TICKET_STATUS_TRACKER[ticket_id]["status"] = current_status
                    # Zoek de gebruiker die dit ticket heeft
                    user_email = None
                    for email, rooms in USER_TICKET_MAP.items():
                        for room_id, tickets in rooms.items():
                            if ticket_id in tickets:
                                user_email = email
                                break
                        if user_email:
                            break
                    # Stuur notificatie naar de juiste Webex room
                    if user_email:
                        for room_id in USER_TICKET_MAP[user_email]:
                            send_message(room_id, f"⚠️ **Statuswijziging voor ticket #{ticket_id}**\n- Oude status: {status_info['status']}\n- Nieuwe status: {current_status}")
                    log.info(f"✅ Statuswijziging gedetecteerd voor ticket {ticket_id}: {status_info['status']} → {current_status}")
            else:
                log.warning(f"⚠️ Ticket status check mislukt voor {ticket_id}: {r.status_code}")
        except Exception as e:
            log.error(f"💥 Fout bij statuscheck voor ticket {ticket_id}: {e}")

# --------------------------------------------------------------------------
# WEBEX EVENTS
# --------------------------------------------------------------------------
def process_webex_event(payload):
    if not WEBEX_HEADERS:
        log.error("❌ WEBEX_HEADERS is niet ingesteld")
        return
    res = payload.get("resource")
    log.info(f"📩 Verwerken Webex event: resource={res}")
    if res == "messages":
        mid = payload["data"]["id"]
        log.info(f"📩 Verwerken bericht: id={mid}")
        msg = requests.get(f"https://webexapis.com/v1/messages/{mid}", headers=WEBEX_HEADERS).json()
        text = msg.get("text", "")
        room_id = msg.get("roomId")
        sender = msg.get("personEmail", "")
        log.info(f"📩 Bericht ontvangen van {sender} in room {room_id}: '{text}'")
        if sender and sender.endswith("@webex.bot"):
            log.info("❌ Bericht is van de bot zelf, negeren")
            return
        # Controleer of de gebruiker een ticket heeft in deze room
        user_email = None
        for email, rooms in USER_TICKET_MAP.items():
            if room_id in rooms:
                user_email = email
                break
        # Als er geen gebruiker is gevonden, maar de gebruiker "nieuwe melding" stuurt, maak dan een nieuwe room aan
        if not user_email and "nieuwe melding" in text.lower():
            # Maak een nieuwe room aan voor deze gebruiker
            user_email = sender  # We gebruiken de sender als email voor de gebruiker
            # Zorg dat de gebruiker een entry heeft in USER_TICKET_MAP
            if user_email not in USER_TICKET_MAP:
                USER_TICKET_MAP[user_email] = {}
            # Gebruik de huidige room als de nieuwe room
            if room_id not in USER_TICKET_MAP[user_email]:
                USER_TICKET_MAP[user_email][room_id] = []
            log.info(f"✅ Gebruiker {user_email} toegevoegd aan room {room_id}")
        # Als er nog steeds geen user_email is, dan is er iets mis
        if not user_email:
            log.info("ℹ️ Geen ticket in deze room, geen actie")
            # Stuur een bericht dat deze room niet voor tickets is
            send_message(room_id, "ℹ️ Deze room is niet geconfigureerd voor ticketdiscussie. Stuur 'nieuwe melding' om een nieuwe ticket room te maken.")
            return
        # Nu kunnen we de "nieuwe melding" verwerken
        if "nieuwe melding" in text.lower():
            log.info("ℹ️ Bericht bevat 'nieuwe melding', stuur adaptive card")
            # Stuur een duidelijke instructie voor het aanmaken van een ticket
            send_message(room_id, "👋 Hi! Je hebt 'nieuwe melding' gestuurd. Klik op de knop hieronder om een ticket aan te maken:\n\n"
                                 "Je kunt ook een bericht sturen met 'Ticket #<nummer>' om een reactie te geven aan een specifiek ticket.")
            send_adaptive_card(room_id)
        else:
            # Check of er een ticketnummer in het bericht staat
            ticket_match = re.search(r'Ticket #(\d+)', text)
            if ticket_match:
                requested_tid = ticket_match.group(1)
                log.info(f"ℹ️ Bericht bevat ticket #{requested_tid}")
                # Controleer of dit ticket bij de gebruiker hoort
                ticket_found = False
                for room_id_check, tickets in USER_TICKET_MAP[user_email].items():
                    if requested_tid in tickets:
                        ticket_found = True
                        break
                if ticket_found:
                    log.info(f"✅ Ticket #{requested_tid} gevonden voor gebruiker {user_email}")
                    success = add_public_note(requested_tid, text)
                    if success:
                        send_message(room_id, f"📝 Bericht toegevoegd aan Halo ticket #{requested_tid}.")
                    else:
                        send_message(room_id, f"❌ Kan geen notitie toevoegen aan ticket #{requested_tid}. Probeer het opnieuw.")
                else:
                    log.info(f"❌ Ticket #{requested_tid} hoort niet bij {user_email}")
                    send_message(room_id, f"❌ Ticket #{requested_tid} hoort niet bij jouw tickets.")
            else:
                log.info("ℹ️ Geen specifiek ticketnummer in bericht, voeg toe aan alle tickets in de room")
                # Geen specifiek ticketnummer, voeg toe aan alle tickets in de room
                for room_id_check, tickets in USER_TICKET_MAP[user_email].items():
                    if room_id == room_id_check:
                        for tid in tickets:
                            success = add_public_note(tid, text)
                            if not success:
                                log.error(f"❌ Notitie toevoegen aan ticket {tid} mislukt")
                        send_message(room_id, f"📝 Bericht toegevoegd aan alle jouw tickets.")
                        break
    elif res == "attachmentActions":
        a_id = payload["data"]["id"]
        log.info(f"📩 Verwerken attachmentActions: id={a_id}")
        inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{a_id}",
                              headers=WEBEX_HEADERS).json().get("inputs", {})
        room_id = payload["data"]["roomId"]
        log.info(f"📩 attachmentActions in room {room_id} met inputs: {json.dumps(inputs, indent=2)}")
        create_halo_ticket(inputs, room_id)
    else:
        log.info(f"ℹ️ Onbekende resource type: {res}")

# --------------------------------------------------------------------------
# HALO ACTION BUTTON WEBHOOK
# --------------------------------------------------------------------------
@app.route("/halo-action", methods=["POST"])
def halo_action():
    if not WEBEX_HEADERS:
        log.error("❌ WEBEX_HEADERS is niet ingesteld")
        return {"status": "ignore"}
    data = request.json if request.is_json else request.form.to_dict()
    log.info(f"📥 Ontvangen Halo action data: {json.dumps(data, indent=2)}")
    ticket_id = None
    note_text = None
    action_type = None
    # Detecteer action type (note, status change, etc.)
    if "actionid" in data:
        action_type = "action"
    elif "status" in data:
        action_type = "status_change"
    elif "assigned_to" in data:
        action_type = "assignment"
    # Haal ticket_id en notitie tekst op
    for f in ["ticket_id", "TicketId", "TicketID", "TicketNumber", "id", "Ticket_Id"]:
        if f in data:
            ticket_id = data[f]
            break
    for f in ["note", "text", "Note", "note_text", "public_note", "comment", "outcome"]:
        if f in data:
            note_text = data[f]
            break
    if not ticket_id or not note_text:
        log.warning("❌ Onvoldoende data in webhook")
        return {"status": "ignore"}
    # Zorg dat ticket_id een string is voor consistentie
    ticket_id = str(ticket_id)
    # Zoek de gebruiker die dit ticket heeft
    user_email = None
    for email, rooms in USER_TICKET_MAP.items():
        for room_id, tickets in rooms.items():
            if ticket_id in tickets:
                user_email = email
                break
        if user_email:
            break
    if not user_email:
        log.warning(f"❌ Geen Webex-room voor ticket {ticket_id}")
        return {"status": "ignore"}
    # Verwerk het type actie
    if action_type == "action":
        # Stuur notificatie naar de juiste Webex room
        for room_id in USER_TICKET_MAP[user_email]:
            send_message(room_id, f"📥 **Nieuwe public note vanuit Halo:**\n{note_text}")
            log.info(f"✅ Note gestuurd naar room {room_id}")
    elif action_type == "status_change":
        # Stuur statuswijziging notificatie
        for room_id in USER_TICKET_MAP[user_email]:
            send_message(room_id, f"⚠️ **Statuswijziging voor ticket #{ticket_id}**\n- Nieuwe status: {note_text}")
            log.info(f"✅ Statuswijziging gestuurd naar room {room_id}")
    elif action_type == "assignment":
        # Stuur toewijzingsnotificatie
        assigned_to = data.get("assigned_to", "onbekende gebruiker")
        for room_id in USER_TICKET_MAP[user_email]:
            send_message(room_id, f"✅ **Ticket #{ticket_id} is toegewezen aan {assigned_to}**")
            log.info(f"✅ Toewijzing gestuurd naar room {room_id}")
    return {"status": "ok"}

# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------
@app.route("/webex", methods=["POST"])
def webex_hook():
    if not WEBEX_HEADERS:
        log.error("❌ WEBEX_HEADERS is niet ingesteld")
        return {"status": "ignore"}
    threading.Thread(target=process_webex_event, args=(request.json,)).start()
    return {"status": "ok"}

@app.route("/initialize", methods=["GET"])
def initialize():
    if not WEBEX_HEADERS:
        log.error("❌ WEBEX_HEADERS is niet ingesteld")
        return {"status": "error", "message": "WEBEX_BOT_TOKEN is niet ingesteld"}
    get_users()
    # Start statuswijziging check in een aparte thread
    threading.Thread(target=status_check_loop, daemon=True).start()
    return {"status": "initialized", "cache_size": len(USER_CACHE['users']), "source": USER_CACHE["source"]}

def status_check_loop():
    """Loopen om statuswijzigingen te controleren"""
    while True:
        try:
            check_ticket_status_changes()
            time.sleep(60)  # Check elke minuut
        except Exception as e:
            log.error(f"💥 Fout bij status check loop: {e}")
            time.sleep(60)

# --------------------------------------------------------------------------
# START
# --------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Start server op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
