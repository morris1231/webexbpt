import os, urllib.parse, logging, sys, time, threading, json
from flask import Flask, request, jsonify
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
app = Flask(__name__)

HALO_AUTH_URL       = os.getenv("HALO_AUTH_URL")
HALO_API_BASE       = os.getenv("HALO_API_BASE")
HALO_CLIENT_ID      = os.getenv("HALO_CLIENT_ID")
HALO_CLIENT_SECRET  = os.getenv("HALO_CLIENT_SECRET")

HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", 65))
HALO_TEAM_ID        = int(os.getenv("HALO_TEAM_ID", 1))
HALO_DEFAULT_IMPACT = int(os.getenv("HALO_IMPACT", 3))
HALO_DEFAULT_URGENCY= int(os.getenv("HALO_URGENCY", 3))
HALO_ACTIONTYPE_PUBLIC = int(os.getenv("HALO_ACTIONTYPE_PUBLIC", 78))

# 🚩 Altijd deze klant en site
HALO_CLIENT_ID_NUM  = int(os.getenv("HALO_CLIENT_ID_NUM", 986))
HALO_SITE_ID        = int(os.getenv("HALO_SITE_ID", 992))

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"} if WEBEX_TOKEN else {}

CONTACT_CACHE = {"contacts": [], "timestamp": 0}
CACHE_DURATION = 24 * 60 * 60
ticket_room_map = {}

# --------------------------------------------------------------------------
# HALO TOKEN
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
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

# --------------------------------------------------------------------------
# CONTACTS ophalen via clientId+siteId
# --------------------------------------------------------------------------
def fetch_all_site_contacts(client_id: int, site_id: int, max_pages=20):
    h = get_halo_headers()
    all_contacts, processed_ids = [], set()
    page = 1
    while page <= max_pages:
        params = {
            "include": "site,client",
            "client_id": client_id,
            "site_id": site_id,
            "type": "contact",
            "page": page,
            "page_size": 50
        }
        r = requests.get(f"{HALO_API_BASE}/Users", headers=h, params=params, timeout=15)
        if r.status_code != 200:
            log.error(f"❌ Fout bij ophalen contacten {r.status_code} {r.text}")
            break
        data = r.json()
        contacts = data.get('users', []) or data.get('items', []) or data
        if not contacts: break
        for c in contacts:
            cid = str(c.get("id", ""))
            if cid and cid not in processed_ids:
                processed_ids.add(cid)
                all_contacts.append(c)
        if len(contacts) < 50:
            break
        page += 1
    return all_contacts

def get_main_contacts():
    now = time.time()
    if CONTACT_CACHE["contacts"] and (now - CONTACT_CACHE["timestamp"] < CACHE_DURATION):
        return CONTACT_CACHE["contacts"]
    CONTACT_CACHE["contacts"] = fetch_all_site_contacts(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    CONTACT_CACHE["timestamp"] = now
    log.info(f"✅ {len(CONTACT_CACHE['contacts'])} contacten in cache")
    return CONTACT_CACHE["contacts"]

def get_halo_contact(email: str):
    if not email: return None
    email = email.lower().strip()
    for c in get_main_contacts():
        for f in [c.get("EmailAddress"), c.get("emailaddress"), c.get("PrimaryEmail"), c.get("login")]:
            if f and f.lower() == email:
                log.info(f"✅ Email match: {email} → ID {c.get('id')}, client={c.get('client_id')}, site={c.get('site_id')}")
                return c
    log.warning(f"⚠️ Geen match gevonden voor {email}")
    return None

# --------------------------------------------------------------------------
# TICKET CREATION
# --------------------------------------------------------------------------
def create_halo_ticket(omschrijving, email, sindswanneer, watwerktniet,
                       zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    h = get_halo_headers()
    contact = get_halo_contact(email)
    if not contact:
        if room_id: send_message(room_id, f"⚠️ Geen contact gevonden voor {email}")
        return None

    contact_id = int(contact.get("id"))
    contact_name = contact.get("name", "Onbekend")

    body = {
        "summary": omschrijving[:100],
        "details": omschrijving,
        "typeId": HALO_TICKET_TYPE_ID,
        "clientId": HALO_CLIENT_ID_NUM,
        "siteId": HALO_SITE_ID,
        "teamId": HALO_TEAM_ID,
        "impactId": int(impact_id),
        "urgencyId": int(urgency_id),
        "requestContactId": contact_id,
        "emailAddress": email
    }

    log.info(f"➡️ Halo ticket body: {json.dumps(body)}")
    r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[body], timeout=15)
    log.info(f"⬅️ Halo antwoord: {r.status_code}")

    if r.status_code in (200, 201):
        resp = r.json()
        ticket = resp[0] if isinstance(resp, list) else resp
        ticket_id = ticket.get("id") or ticket.get("ID") or "?"
        log.info(f"✅ Ticket aangemaakt ID={ticket_id}")

        note = (f"**Naam:** {contact_name}\n**E-mail:** {email}\n"
                f"**Probleem:** {omschrijving}\n\n"
                f"**Sinds:** {sindswanneer}\n"
                f"**Wat werkt niet:** {watwerktniet}\n"
                f"**Zelf geprobeerd:** {zelfgeprobeerd}\n"
                f"**Impact:** {impacttoelichting}")
        add_note_to_ticket(ticket_id, note, contact_name, email, room_id, contact_id)
        return {"ID": ticket_id, "contact_id": contact_id}
    else:
        log.error(f"❌ Halo error {r.text}")
        if room_id: send_message(room_id, f"⚠️ Ticket fout: {r.text[:200]}")
        return None

# --------------------------------------------------------------------------
# NOTES
# --------------------------------------------------------------------------
def add_note_to_ticket(ticket_id, public_output, sender, email=None, room_id=None, contact_id=None):
    h = get_halo_headers()
    body = {
        "details": public_output,
        "actionTypeId": HALO_ACTIONTYPE_PUBLIC,
        "isPrivate": False,
        "timeSpent": "00:00:00",
        "userId": contact_id
    }
    requests.post(f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions",
                  headers=h, json=body, timeout=10)

# --------------------------------------------------------------------------
# WEBEX HELPERS
# --------------------------------------------------------------------------
def send_message(room_id, text):
    if WEBEX_HEADERS:
        requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS,
                      json={"roomId": room_id, "markdown": text}, timeout=10)

def send_adaptive_card(room_id):
    # 📋 Stuur begeleidende tekst
    send_message(room_id, "✍ Vul het formulier in:")

    # Daarna de Adaptive Card zonder markdown
    card = {
        "roomId": room_id,
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": "E-mailadres", "weight": "Bolder"},
                    {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres", "isRequired": True},
                    {"type": "TextBlock", "text": "Probleemomschrijving", "weight": "Bolder"},
                    {"type": "Input.Text", "id": "omschrijving", "placeholder": "Probleemomschrijving", "isRequired": True, "isMultiline": True},
                    {"type": "TextBlock", "text": "Sinds wanneer?"},
                    {"type": "Input.Text", "id": "sindswanneer"},
                    {"type": "TextBlock", "text": "Wat werkt niet?"},
                    {"type": "Input.Text", "id": "watwerktniet"},
                    {"type": "TextBlock", "text": "Zelf geprobeerd?"},
                    {"type": "Input.Text", "id": "zelfgeprobeerd", "isMultiline": True},
                    {"type": "TextBlock", "text": "Impact toelichting"},
                    {"type": "Input.Text", "id": "impacttoelichting", "isMultiline": True}
                ],
                "actions": [
                    {"type": "Action.Submit", "title": "Versturen"}
                ]
            }
        }]
    }
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS,
                  json=card, timeout=10)

# --------------------------------------------------------------------------
# WEBEX EVENTS
# --------------------------------------------------------------------------
def process_webex_event(data):
    res = data.get("resource")
    if res == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS).json()
        text, room_id, sender = msg.get("text", ""), msg.get("roomId"), msg.get("personEmail")
        if sender.endswith("@webex.bot"): return
        if "nieuwe melding" in text.lower():
            send_adaptive_card(room_id)
        else:
            for t_id, ri in ticket_room_map.items():
                if ri.get("room_id") == room_id:
                    add_note_to_ticket(t_id, text, sender, email=sender,
                                       room_id=room_id, contact_id=ri.get("contact_id"))

    elif res == "attachmentActions":
        act_id = data["data"]["id"]
        inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{act_id}", headers=WEBEX_HEADERS).json().get("inputs", {})
        if not inputs.get("email") or not inputs.get("omschrijving"):
            send_message(data["data"]["roomId"], "⚠️ E-mail en omschrijving verplicht.")
            return
        ticket = create_halo_ticket(inputs["omschrijving"], inputs["email"],
                                    inputs.get("sindswanneer", "Niet opgegeven"),
                                    inputs.get("watwerktniet", "Niet opgegeven"),
                                    inputs.get("zelfgeprobeerd", "Niet opgegeven"),
                                    inputs.get("impacttoelichting", "Niet opgegeven"),
                                    inputs.get("impact", HALO_DEFAULT_IMPACT),
                                    inputs.get("urgency", HALO_DEFAULT_URGENCY),
                                    room_id=data["data"]["roomId"])
        if ticket:
            ticket_id = ticket.get("ID")
            ticket_room_map[ticket_id] = {"room_id": data["data"]["roomId"], "contact_id": ticket.get("contact_id")}
            send_message(data["data"]["roomId"], f"✅ Ticket aangemaakt ID: {ticket_id}")

# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------
@app.route("/webex", methods=["POST"])
def webhook():
    threading.Thread(target=process_webex_event, args=(request.json,)).start()
    return {"status": "ok"}

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "contacts_cached": len(CONTACT_CACHE["contacts"])}

@app.route("/initialize", methods=["GET"])
def initialize():
    get_main_contacts()
    return {"status": "initialized", "cache_size": len(CONTACT_CACHE['contacts'])}

@app.route("/cache", methods=["GET"])
def inspect_cache():
    return jsonify(CONTACT_CACHE)

# --------------------------------------------------------------------------
# START
# --------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Start server op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
