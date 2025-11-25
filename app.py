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
required = ["HALO_AUTH_URL", "HALO_API_BASE", "HALO_CLIENT_ID", "HALO_CLIENT_SECRET", "WEBEX_BOT_TOKEN", "AUTHORIZED_USERS"]
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
AUTHORIZED_USERS = [email.strip() for email in os.getenv("AUTHORIZED_USERS", "").split(",") if email.strip()]
log.info(f"✅ Geautoriseerde gebruikers voor KB verwijdering: {AUTHORIZED_USERS}")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}",
                 "Content-Type": "application/json"} if WEBEX_TOKEN else {}
# Algemene settings
DEDUPE_SECONDS = int(os.getenv("DEDUPE_SECONDS", 30))  # tijdsvenster voor het negeren van identieke webhook events
# Optionele filtering/controle van status notificaties:
# - STATUS_NOTIFY_WHITELIST: komma gescheiden namen waarvoor een melding gestuurd wordt (case-insensitive)
#   Voorbeeld: "Assigned,In Progress"
# - POLL_STATUS_ENABLED: "1" om de periodieke status polling aan te zetten, anders uit (default uit)
STATUS_NOTIFY_WHITELIST = [s.strip().lower() for s in os.getenv("STATUS_NOTIFY_WHITELIST", "").split(',') if s.strip()]
POLL_STATUS_ENABLED = os.getenv("POLL_STATUS_ENABLED", "0") in ["1", "true", "True"]
# Gebruikers cache (alleen voor client 18 & site 18)
USER_CACHE = {
    "users": [],
    "timestamp": 0,
    "source": "none",
    "max_users": 200
}
# Mapping van room naar tickets: {room_id: [ticket_id1, ticket_id2, ...]}
USER_TICKET_MAP = {}
# Status & assignee tracker: {ticket_id: {status: str, assignee: str|None, last_checked: ts}}
TICKET_STATUS_TRACKER = {}
# Cache voor duplicate webhook events: {(ticket_id, type, hash): timestamp}
LAST_WEBHOOK_EVENTS = {}
CACHE_DURATION = 24 * 60 * 60  # 24 uur
MAX_PAGES = 3  # Max 3 pagina's (100 + 100 + 100 = 300 users)
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
# HELPER FUNCTIE VOOR HALO REQUESTS MET RATE LIMIT HANDLING
# --------------------------------------------------------------------------
def halo_request(url, method='GET', headers=None, params=None, json=None, max_retries=3):
    for attempt in range(max_retries):
        try:
            if method == 'GET':
                r = requests.get(url, headers=headers, params=params, json=json, timeout=15)
            elif method == 'POST':
                r = requests.post(url, headers=headers, params=params, json=json, timeout=15)
            elif method == 'DELETE':
                r = requests.delete(url, headers=headers, params=params, json=json, timeout=15)
            else:
                raise ValueError(f"Onbekende methode: {method}")
        except Exception as e:
            log.error(f"Request mislukt: {e}")
            if attempt < max_retries - 1:
                wait_time = 1 * (attempt + 1)
                log.warning(f"Retrying in {wait_time} seconden (poging {attempt+1}/{max_retries})")
                time.sleep(wait_time)
                continue
            else:
                raise e
        # Rate limit handling
        if r.status_code == 429:
            retry_after = r.headers.get('Retry-After')
            wait_time = int(retry_after) if retry_after else 10
            log.warning(f"Rate limit bereikt, wachten {wait_time} seconden")
            time.sleep(wait_time)
            continue
        # Andere status codes
        return r
    return r  # Na max_retries, retourneer laatste response
# --------------------------------------------------------------------------
# STATUS NAAM CONVERSIE (ID → NAAM)
# --------------------------------------------------------------------------
def get_status_name(status_id):
    try:
        # Alleen converteren als status_id een nummer is
        if isinstance(status_id, str) and status_id.isdigit():
            status_id = int(status_id)
        if not isinstance(status_id, int):
            return str(status_id)
        h = get_halo_headers()
        url = f"{HALO_API_BASE}/api/Status/{status_id}"
        r = halo_request(url, headers=h)
        if r.status_code == 200:
            status_data = r.json()
            # Check meerdere mogelijke veldnamen voor statusnaam
            name = status_data.get("name") or status_data.get("StatusName") or status_data.get("status_name") or status_data.get("Status")
            if name:
                return name
        return str(status_id)
    except Exception as e:
        log.error(f"❌ Fout bij statusnaam conversie voor ID {status_id}: {e}")
        return str(status_id)
# --------------------------------------------------------------------------
# USERS
# --------------------------------------------------------------------------
def fetch_users(client_id, site_id):
    h = get_halo_headers()
    all_users = []
    page = 0
    page_size = 100
    while len(all_users) < USER_CACHE["max_users"]:
        params = {
            "client_id": client_id,
            "site_id": site_id,
            "pageinate": True,
            "page": page,
            "page_size": page_size
        }
        log.info(f"➡️ Fetching users page {page} (client={client_id}, site={site_id})")
        r = halo_request(f"{HALO_API_BASE}/api/Users",
                         params=params,
                         headers=h)
        if r.status_code != 200:
            log.warning(f"⚠️ /api/Users pagina {page} gaf {r.status_code}: {r.text[:200]}")
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
        if len(users) < page_size or len(all_users) >= USER_CACHE["max_users"]:
            break
        page += 1
    all_users = all_users[:USER_CACHE["max_users"]]
    log.info(f"✅ {len(all_users)} gebruikers opgehaald (client={client_id}, site={site_id})")
    return all_users
def get_users():
    now = time.time()
    source = f"client{HALO_CLIENT_ID_NUM}_site{HALO_SITE_ID}"
    if USER_CACHE["users"] and \
       (now - USER_CACHE["timestamp"] < CACHE_DURATION) and \
       USER_CACHE["source"] == source:
        log.info(f"✅ Gebruikers uit cache (bron: {source})")
        return USER_CACHE["users"]
    users = fetch_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    USER_CACHE["users"] = users
    USER_CACHE["timestamp"] = now
    USER_CACHE["source"] = source
    log.info(f"✅ Gebruikers opgehaald en gecached (bron: {source})")
    return users
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
        response = requests.post("https://webexapis.com/v1/messages",
                      headers=WEBEX_HEADERS,
                      json={"roomId": room_id, "markdown": text}, timeout=10)
        log.info(f"✅ Webex bericht verstuurd naar room {room_id} (status: {response.status_code})")
        return response
    except Exception as e:
        log.error(f"❌ Webex send: {e}")
        return None
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
    url = f"{HALO_API_BASE}/api/Tickets"
    log.info(f"➡️ Creëer Halo ticket met body: {json.dumps(body, indent=2)}")
    r = halo_request(url, method='POST', headers=h, json=[body])
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
    current_status = ticket.get("Status") or ticket.get("status") or ticket.get("StatusName") or "Unknown"
    # Converteer status ID naar naam als nodig
    if isinstance(current_status, int) or (isinstance(current_status, str) and current_status.isdigit()):
        current_status = get_status_name(current_status)
    if not tid:
        send_message(room_id, "❌ Ticket aangemaakt, maar geen ID gevonden")
        log.error("❌ Geen ticket ID gevonden in Halo response")
        return
    log.info(f"✅ Ticket aangemaakt: {tid}")
    if room_id not in USER_TICKET_MAP:
        USER_TICKET_MAP[room_id] = []
    USER_TICKET_MAP[room_id].append(tid)
    # Init tracker zonder assignee
    TICKET_STATUS_TRACKER[tid] = {"status": current_status, "assignee": None, "last_checked": time.time()}
    send_message(room_id, f"✅ Ticket aangemaakt: **{tid}**")
    log.info(f"✅ Ticket {tid} toegevoegd aan room {room_id}")
    return tid
# --------------------------------------------------------------------------
# PUBLIC NOTE FUNCTIE (CORRECTE IMPLEMENTATIE)
# --------------------------------------------------------------------------
def add_public_note(ticket_id, text):
    if not WEBEX_HEADERS:
        log.error("❌ WEBEX_HEADERS is niet ingesteld")
        return False
    h = get_halo_headers()
    url = f"{HALO_API_BASE}/api/Actions"
    payload = [
        {
            "Ticket_Id": int(ticket_id),
            "ActionId": ACTION_ID_PUBLIC,
            "outcome": text
        }
    ]
    log.info(f"➡️ Sturen public note naar Halo voor ticket {ticket_id}: {text}")
    r = halo_request(url, method='POST', headers=h, json=payload)
    if r.status_code in [200, 201]:
        log.info(f"✅ Public note succesvol toegevoegd aan ticket {ticket_id}")
        return True
    else:
        log.error(f"❌ Public note mislukt: {r.status_code} - {r.text}")
        return False
# --------------------------------------------------------------------------
# STATUS WIJZIGINGEN
# --------------------------------------------------------------------------
def check_ticket_status_changes():
    h = get_halo_headers()
    for ticket_id, status_info in list(TICKET_STATUS_TRACKER.items()):
        try:
            # Haal volledige ticket details met includedetails=true
            url = f"{HALO_API_BASE}/api/Tickets/{ticket_id}"
            log.info(f"➡️ Controleer status van ticket {ticket_id}")
            r = halo_request(url, headers=h, params={"includedetails": True})
            if r.status_code == 200:
                ticket_data = r.json()
                # Check alle mogelijke statusvelden (top-level en nested)
                current_status = ticket_data.get("Status") or \
                                 ticket_data.get("status") or \
                                 ticket_data.get("StatusName") or \
                                 ticket_data.get("status_name") or \
                                 ticket_data.get("StatusID") or \
                                 ticket_data.get("ticket_status", {}).get("name") or \
                                 ticket_data.get("status", {}).get("name") or \
                                 ticket_data.get("status", {}).get("status") or \
                                 ticket_data.get("status", {}).get("Status") or \
                                 ticket_data.get("status", {}).get("StatusName") or \
                                 "Unknown"
                # Converteer status ID naar naam als nodig
                if isinstance(current_status, int) or (isinstance(current_status, str) and current_status.isdigit()):
                    current_status = get_status_name(current_status)
                # Detecteer nieuwe toegewezen agent
                current_assignee = ticket_data.get("assigned_to") or \
                                   ticket_data.get("AssignedTo") or \
                                   ticket_data.get("assigned_user") or \
                                   ticket_data.get("agent") or \
                                   ticket_data.get("Agent") or \
                                   ticket_data.get("assignee") or \
                                   ticket_data.get("Assignee")
                assignee_changed = False
                if current_assignee and current_assignee != status_info.get("assignee"):
                    assignee_changed = True
                    TICKET_STATUS_TRACKER[ticket_id]["assignee"] = current_assignee
                    room_id = None
                    for rid, tickets in USER_TICKET_MAP.items():
                        if ticket_id in tickets:
                            room_id = rid
                            break
                    if room_id:
                        send_message(room_id, f"✅ **Ticket #{ticket_id} geassigned aan {current_assignee}**")
                        log.info(f"✅ Assignment update gestuurd naar room {room_id}")
                if current_status != status_info["status"]:
                    # Alleen melden als whitelist leeg is uitgeschakeld OF als de nieuwe status in de whitelist zit
                    if STATUS_NOTIFY_WHITELIST and current_status.lower() not in STATUS_NOTIFY_WHITELIST:
                        log.info(f"🔕 Status {status_info['status']} → {current_status} genegeerd (niet in whitelist)")
                    else:
                        TICKET_STATUS_TRACKER[ticket_id]["status"] = current_status
                        room_id = None
                        for rid, tickets in USER_TICKET_MAP.items():
                            if ticket_id in tickets:
                                room_id = rid
                                break
                        if room_id:
                            send_message(room_id, f"⚠️ **Statuswijziging voor ticket #{ticket_id}**\n- Oude status: {status_info['status']}\n- Nieuwe status: {current_status}")
                            log.info(f"✅ Statuswijziging gestuurd naar room {room_id}")
                        else:
                            log.warning(f"⚠️ Geen Webex-room gevonden voor ticket {ticket_id}")
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
        # NIEUWE CHECK VOOR KB VERWIJDERING
        if "/empty_kb" in text.lower() or "empty kb" in text.lower():
            if sender in AUTHORIZED_USERS:
                send_message(room_id, "⏳ Bezig met verwijderen van alle Knowledge Base artikelen...")
                count = empty_knowledge_base()
                send_message(room_id, f"✅ **{count} KB artikelen succesvol verwijderd**")
            else:
                send_message(room_id, "❌ ❌ **Geen toestemming!** Jij bent niet geautoriseerd om Knowledge Base te wissen. Neem contact op met de beheerder.")
            return
        if "nieuwe melding" in text.lower():
            log.info("ℹ️ Bericht bevat 'nieuwe melding', stuur adaptive card")
            send_message(room_id, "👋 Hi! Je hebt 'nieuwe melding' gestuurd. Klik op de knop hieronder om een ticket aan te maken:\n\n"
                                 "Je kunt ook een bericht sturen met 'Ticket #<nummer>' om een reactie te geven aan een specifiek ticket.")
            send_adaptive_card(room_id)
            return
        ticket_match = re.search(r'Ticket #(\d+)', text)
        if ticket_match:
            requested_tid = ticket_match.group(1)
            log.info(f"ℹ️ Bericht bevat ticket #{requested_tid}")
            if room_id in USER_TICKET_MAP and requested_tid in USER_TICKET_MAP[room_id]:
                log.info(f"✅ Ticket #{requested_tid} gevonden in room {room_id}")
                success = add_public_note(requested_tid, text)
                if success:
                    send_message(room_id, f"📝 Bericht toegevoegd aan Halo ticket #{requested_tid}.")
                else:
                    send_message(room_id, f"❌ Kan geen notitie toevoegen aan ticket #{requested_tid}. Probeer het opnieuw.")
            else:
                log.info(f"❌ Ticket #{requested_tid} bestaat niet in deze room")
                send_message(room_id, f"❌ Ticket #{requested_tid} bestaat niet in deze room of is niet gekoppeld aan deze room.")
        else:
            log.info("ℹ️ Geen specifiek ticketnummer in bericht, voeg toe aan alle tickets in de room")
            if room_id in USER_TICKET_MAP:
                for tid in USER_TICKET_MAP[room_id]:
                    success = add_public_note(tid, text)
                    if not success:
                        log.error(f"❌ Notitie toevoegen aan ticket {tid} mislukt")
                send_message(room_id, f"📝 Bericht toegevoegd aan alle jouw tickets in deze room.")
            else:
                send_message(room_id, "ℹ️ Geen tickets gevonden in deze room. Stuur 'nieuwe melding' om een ticket aan te maken.")
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
# HALO ACTION BUTTON WEBHOOK - GEREDUCEERDE LOGGING
# --------------------------------------------------------------------------
@app.route("/halo-action", methods=["POST"])
def halo_action():
    # --- CRUCIALE AUTHENTICATIE CHECK ---
    auth = request.authorization
    if not auth or auth.username != "Webexbot" or auth.password != "Webexbot2025":
        log.error("❌ Ongeldige credentials voor Halo webhook")
        return {"status": "unauthorized"}, 401
    # --- GEREDUCEERDE LOGGING VAN WEBHOOK DATA ---
    data = request.json if request.is_json else request.form.to_dict()
    # Log alleen relevante velden in plaats van volledige JSON
    relevant_data = {
        "ticket_id": data.get("ticket_id") or data.get("TicketId") or data.get("TicketNumber"),
        "status": data.get("status") or data.get("Status"),
        "action_id": data.get("actionid") or data.get("ActionId"),
        "note": data.get("outcome") or data.get("note") or data.get("text"),
        "assigned_agent": data.get("assigned_to") or data.get("assignedTo"),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    log.info(f"📥 HALO WEBHOOK DATA: {json.dumps(relevant_data, indent=2)}")
    # Controleer alle mogelijke veldnamen voor ticket ID
    ticket_id = None
    for f in ["ticket_id", "TicketId", "TicketID", "TicketNumber", "id", "Ticket_Id", "ticketnumber", "Ticket_ID", "ticketid", "TicketID", "TicketID", "ticket_id", "TicketID"]:
        if f in data:
            ticket_id = data[f]
            break
    # Controleer alle mogelijke veldnamen voor notitietekst
    note_text = None
    for f in ["outcome", "note", "text", "comment", "description", "public_note", "note_text", "comment_text", "action_description", "notecontent", "NoteContent", "note_body", "NoteBody", "note_text", "NoteText", "action_note", "ActionNote"]:
        if f in data:
            note_text = data[f]
            break
    # Controleer alle mogelijke veldnamen voor status
    status_change = None
    for f in ["status", "Status", "status_name", "statusName", "status_id", "StatusID", "ticketstatus", "TicketStatus", "current_status", "NewStatus", "NewStatusName", "status_value", "StatusValue", "status_name", "StatusName", "status_text", "StatusText", "newstatus", "NewStatus", "status_id", "StatusID"]:
        if f in data:
            status_change = data[f]
            break
    # Controleer alle mogelijke veldnamen voor toegewezen agent
    assigned_agent = None
    for f in ["assigned_to", "assignedTo", "assignedagent", "agent", "AssignedAgent", "assigned_by", "assignedBy", "assignedby", "AssignedBy", "assigned_to_name", "assignedToName", "agent_name", "AgentName", "assigned_to_id", "AssignedToID", "assigned_by_id", "AssignedByID"]:
        if f in data:
            assigned_agent = data[f]
            break
    # Controleer alle mogelijke veldnamen voor actie ID
    action_id = None
    for f in ["actionid", "ActionId", "action_id", "action", "Action", "action_id", "action_id", "ActionID", "action_id", "ActionType", "action_type", "action_type_id", "ActionTypeID"]:
        if f in data:
            action_id = data[f]
            break
    # Als we geen ticket_id hebben, log dit en stopt
    if not ticket_id:
        log.warning("❌ Geen ticket_id gevonden in webhook data")
        return {"status": "ignore"}
    # Zorg dat ticket_id een string is voor consistentie
    ticket_id = str(ticket_id)
    # Zoek de room waar dit ticket in zit
    room_id = None
    for rid, tickets in USER_TICKET_MAP.items():
        if ticket_id in tickets:
            room_id = rid
            break
    if not room_id:
        log.warning(f"❌ Geen Webex-room gevonden voor ticket {ticket_id}")
        return {"status": "ignore"}
    # Achterhaal auteur / agent naam (voor notities en assignments)
    note_author = None
    for f in ["note_author", "author", "created_by", "CreatedBy", "user", "User", "username", "Username", "agent", "Agent", "action_user", "ActionUser", "entered_by", "EnteredBy"]:
        if f in data and data[f]:
            note_author = data[f]
            break
    # Losse voor/achternaam velden samenvoegen indien aanwezig
    first_name = data.get("first_name") or data.get("FirstName") or data.get("firstname")
    last_name = data.get("last_name") or data.get("LastName") or data.get("lastname")
    if (first_name or last_name) and not note_author:
        note_author = f"{first_name or ''} {last_name or ''}".strip()
    # Tracker initialiseren indien onbekend
    if ticket_id not in TICKET_STATUS_TRACKER:
        TICKET_STATUS_TRACKER[ticket_id] = {"status": None, "assignee": None, "last_checked": time.time()}
    # Dedupe helper (best effort binnen single process)
    def is_duplicate(kind: str, content: str):
        key_hash = hash(f"{kind}:{ticket_id}:{content.strip()}")
        now = time.time()
        ts = LAST_WEBHOOK_EVENTS.get(key_hash)
        if ts and now - ts < DEDUPE_SECONDS:
            return True
        LAST_WEBHOOK_EVENTS[key_hash] = now
        for k, v in list(LAST_WEBHOOK_EVENTS.items()):
            if now - v > DEDUPE_SECONDS * 2:
                del LAST_WEBHOOK_EVENTS[k]
        return False
    # Public / agent note detection: stuur bij elke note_text tenzij leeg.
    # We beperken duplicates; actie_id hoeft niet exact te matchen.
    if note_text and str(note_text).strip():
        if is_duplicate("note", note_text):
            log.info(f"🔁 Duplicate note genegeerd voor ticket {ticket_id}")
            return {"status": "duplicate"}
        log.info(f"✅ Note ontvangen voor ticket {ticket_id}")
        author_segment = f" door {note_author}" if note_author else ""
        send_message(room_id, f"📥 **Public note{author_segment}**\n{note_text}")
        return {"status": "ok"}
    # Verwerk statuswijzigingen (converteer ID naar naam)
    if status_change:
        # Converteer status ID naar naam als nodig
        if isinstance(status_change, int) or (isinstance(status_change, str) and status_change.isdigit()):
            status_name = get_status_name(status_change)
            log.info(f"✅ Status ID {status_change} geconverteerd naar naam: {status_name}")
            status_change = status_name
        else:
            status_name = status_change
        # Filter via whitelist (indien ingesteld). Alleen versturen als whitelist leeg OF status in whitelist.
        prev_status = TICKET_STATUS_TRACKER[ticket_id]["status"]
        if prev_status == status_name:
            log.info(f"🔁 Status '{status_name}' al bekend voor ticket {ticket_id}; geen bericht")
        elif STATUS_NOTIFY_WHITELIST and status_name.lower() not in STATUS_NOTIFY_WHITELIST:
            log.info(f"🔕 Webhook status '{status_name}' genegeerd (niet in whitelist)")
            TICKET_STATUS_TRACKER[ticket_id]["status"] = status_name  # Update zonder notificatie
        else:
            if is_duplicate("status", status_name):
                log.info(f"🔁 Duplicate status event genegeerd voor ticket {ticket_id}: {status_name}")
                return {"status": "duplicate"}
            log.info(f"✅ Statuswijziging ontvangen voor ticket {ticket_id}: {status_name}")
            send_message(room_id, f"⚠️ Ticket #{ticket_id} status gewijzigd naar: **{status_name}**")
            TICKET_STATUS_TRACKER[ticket_id]["status"] = status_name
        return {"status": "ok"}
    # Verwerk toewijzingen
    if assigned_agent:
        assignee_display = assigned_agent
        if (first_name or last_name) and not assigned_agent:
            assignee_display = f"{first_name or ''} {last_name or ''}".strip()
        prev_assignee = TICKET_STATUS_TRACKER[ticket_id].get("assignee")
        if prev_assignee == assignee_display:
            log.info(f"🔁 Assignee '{assignee_display}' al bekend voor ticket {ticket_id}; geen bericht")
        else:
            if is_duplicate("assignment", assignee_display):
                log.info(f"🔁 Duplicate assignment genegeerd voor ticket {ticket_id}")
                return {"status": "duplicate"}
            log.info(f"✅ Toewijzing ontvangen voor ticket {ticket_id}: {assignee_display}")
            send_message(room_id, f"✅ Ticket #{ticket_id} geassigned naar **{assignee_display}**")
            TICKET_STATUS_TRACKER[ticket_id]["assignee"] = assignee_display
        return {"status": "ok"}
    # Als geen van de bovenstaande gevalen, log en stopt
    log.warning("❌ Geen herkenbare actie in webhook data")
    return {"status": "ignore"}
# --------------------------------------------------------------------------
# KB LEEMMAK FUNCTIE
# --------------------------------------------------------------------------
def empty_knowledge_base():
    h = get_halo_headers()
    all_ids = []
    page = 0
    page_size = 100
    total_articles = 0
    total_pages = 0
    
    while True:
        # Gebruik "page" in plaats van "page_no" voor HALO API
        params = {
            "pageinate": True,
            "page_size": page_size,
            "page": page,  # Correctie: page in plaats van page_no
            "count": 1000  # Extra parameter om alle artikelen op te halen in één keer
        }
        url = f"{HALO_API_BASE}/api/KBArticle"
        log.info(f"➡️ Ophalen KB artikelen (pagina {page}, page_size={page_size})")
        r = halo_request(url, headers=h, params=params)
        
        if r.status_code != 200:
            log.error(f"❌ Fout bij ophalen KB artikelen: {r.status_code} - {r.text[:500]}")
            break
            
        data = r.json()
        log.info(f"📩 API Response (pagina {page}): {json.dumps(data, indent=2)[:500]}...")
        
        # Handle verschillende mogelijke response formaten
        articles = []
        if isinstance(data, dict):
            if "root" in data:
                articles = data["root"]
            elif "data" in data:
                articles = data["data"]
            elif "items" in data:
                articles = data["items"]
            elif "articles" in data:
                articles = data["articles"]
            elif "KBArticles" in data:
                articles = data["KBArticles"]
            else:
                # Probeer de data direct als lijst
                if isinstance(data, list):
                    articles = data
                else:
                    log.warning(f"⚠️ Onbekende response structuur: {json.dumps(data, indent=2)[:200]}")
        elif isinstance(data, list):
            articles = data
        else:
            log.warning(f"⚠️ Onbekende response type: {type(data)}")
        
        if not articles:
            log.info(f"✅ Geen artikelen meer gevonden (pagina {page})")
            break
            
        # Log details van de eerste paar artikelen
        for i, article in enumerate(articles[:3]):
            article_id = article.get("id") or article.get("KBArticleID") or article.get("ArticleID")
            log.info(f"🔍 Artikel {i+1}: ID={article_id}, Title={article.get('Title') or article.get('title')}")
        
        for article in articles:
            article_id = article.get("id") or article.get("KBArticleID") or article.get("ArticleID") or article.get("ArticleId")
            if article_id is not None:
                all_ids.append(str(article_id))
            else:
                log.warning(f"⚠️ Artikel heeft geen ID: {json.dumps(article, indent=2)[:200]}")
                
        total_articles += len(articles)
        total_pages = page + 1
        
        if len(articles) < page_size:
            log.info(f"✅ Eind van pagina's bereikt (totaal {total_articles} artikelen in {total_pages} pagina's)")
            break
            
        page += 1
        
    log.info(f"🔍 Totaal {len(all_ids)} KB artikelen gevonden om te verwijderen")
    deleted_count = 0
    for i, article_id in enumerate(all_ids):
        url = f"{HALO_API_BASE}/api/KBArticle/{article_id}"
        log.info(f"➡️ Verwijderen KB artikel {i+1}/{len(all_ids)}: {article_id}")
        r = halo_request(url, method='DELETE', headers=h)
        if r.status_code in [200, 204]:
            deleted_count += 1
            log.info(f"✅ KB artikel {article_id} verwijderd")
        else:
            log.error(f"❌ Fout bij verwijderen KB artikel {article_id}: {r.status_code} - {r.text[:500]}")
            
    log.info(f"✅ Totaal {deleted_count} KB artikelen verwijderd van {len(all_ids)} gevonden")
    return deleted_count
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
    # Start poller alleen als expliciet aangezet
    if POLL_STATUS_ENABLED:
        threading.Thread(target=status_check_loop, daemon=True).start()
    return {
        "status": "initialized",
        "source": f"client{HALO_CLIENT_ID_NUM}_site{HALO_SITE_ID}",
        "cached_users": len(USER_CACHE["users"])
    }
@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "tickets_tracked": len(TICKET_STATUS_TRACKER),
        "rooms": len(USER_TICKET_MAP)
    }
@app.route("/tickets/<room_id>", methods=["GET"])
def list_room_tickets(room_id):
    tickets = USER_TICKET_MAP.get(room_id, [])
    result = []
    for tid in tickets:
        info = TICKET_STATUS_TRACKER.get(tid, {})
        result.append({
            "ticket_id": tid,
            "status": info.get("status"),
            "assignee": info.get("assignee")
        })
    return {"tickets": result}
@app.route("/ticket/<ticket_id>", methods=["GET"])
def ticket_details(ticket_id):
    h = get_halo_headers()
    url = f"{HALO_API_BASE}/api/Tickets/{ticket_id}"
    r = halo_request(url, headers=h, params={"includedetails": True})
    if r.status_code != 200:
        return {"error": "not_found", "status_code": r.status_code}, r.status_code
    data = r.json()
    # Versimpelde extractie
    status_val = data.get("Status") or data.get("status") or data.get("StatusName")
    if isinstance(status_val, int) or (isinstance(status_val, str) and status_val.isdigit()):
        status_val = get_status_name(status_val)
    assignee_val = data.get("assigned_to") or data.get("AssignedTo") or data.get("assignee")
    return {
        "ticket_id": ticket_id,
        "status": status_val,
        "assignee": assignee_val,
        "summary": data.get("Summary") or data.get("summary"),
        "details": data.get("Details") or data.get("details")
    }
def status_check_loop():
    while True:
        try:
            check_ticket_status_changes()
            time.sleep(60)
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

