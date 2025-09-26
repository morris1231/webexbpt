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
log = logging.getLogger("ticketbot")
log.info("✅ Logging gestart")

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

HALO_AUTH_URL = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE = "https://bncuat.halopsa.com/api"

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"} if WEBEX_TOKEN else {}

HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

HALO_TICKET_TYPE_ID = 65
HALO_TEAM_ID = 1
HALO_DEFAULT_IMPACT = 3
HALO_DEFAULT_URGENCY = 3
HALO_ACTIONTYPE_PUBLIC = 78

# 🚩 Altijd deze gebruiken
HALO_CLIENT_ID_NUM = 986    # Bossers & Cnossen
HALO_SITE_ID = 992          # Main site

CONTACT_CACHE = {"contacts": [], "timestamp": 0}
CACHE_DURATION = 24 * 60 * 60  # 24 uur
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
# CONTACTS
# --------------------------------------------------------------------------
def fetch_all_site_contacts(client_id: int, site_id: int, max_pages=20):
    h = get_halo_headers()
    all_contacts, processed_ids = [], set()
    page, endpoint = 1, "/Users"
    while page <= max_pages:
        params = {
            "include": "site,client",
            "client_id": client_id,
            "site_id": site_id,
            "type": "contact",
            "page": page,
            "page_size": 50
        }
        r = requests.get(f"{HALO_API_BASE}{endpoint}", headers=h, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            contacts = data.get('users', []) or data.get('items', []) or data
            if not contacts: break
            for contact in contacts:
                cid = str(contact.get('id', ''))
                if cid and cid not in processed_ids:
                    processed_ids.add(cid)
                    all_contacts.append(contact)
            if len(contacts) < 50: break
            page += 1
        else:
            log.error(f"❌ Halo fout {r.status_code}: {r.text}")
            break
    return all_contacts

def get_main_contacts():
    now = time.time()
    if CONTACT_CACHE["contacts"] and (now - CONTACT_CACHE["timestamp"] < CACHE_DURATION):
        return CONTACT_CACHE["contacts"]
    log.info(f"🔄 Ophalen contacten client={HALO_CLIENT_ID_NUM} site={HALO_SITE_ID}")
    CONTACT_CACHE["contacts"] = fetch_all_site_contacts(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    CONTACT_CACHE["timestamp"] = time.time()
    log.info(f"✅ {len(CONTACT_CACHE['contacts'])} contacten gecached")
    return CONTACT_CACHE["contacts"]

def get_halo_contact_id(email: str):
    if not email: return None
    email = email.strip().lower()
    for c in get_main_contacts():
        fields = [
            c.get("EmailAddress", ""), c.get("emailaddress", ""),
            c.get("PrimaryEmail", ""), c.get("username", ""),
            c.get("login", ""), c.get("email2", ""), c.get("email3", "")
        ]
        for f in fields:
            if f and email == f.lower():
                log.info(f"✅ Email match {email} → ID {c.get('id')}")
                return c.get("id")
    log.warning(f"⚠️ Geen match voor {email}")
    return None

def get_contact_name(contact_id):
    for c in get_main_contacts():
        if str(c.get("id")) == str(contact_id):
            return c.get("name", "Onbekend")
    return "Onbekend"

# --------------------------------------------------------------------------
# TICKET AANMAKEN met fallback (contactId → endUserId)
# --------------------------------------------------------------------------
def create_halo_ticket(omschrijving, email, sindswanneer, watwerktniet,
                       zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    h = get_halo_headers()
    contact_id = get_halo_contact_id(email)
    if not contact_id:
        if room_id: send_message(room_id, "⚠️ Geen matchend contact in Halo.")
        return None

    contact_name = get_contact_name(contact_id)

    base_body = {
        "summary": str(omschrijving)[:100],
        "details": str(omschrijving),
        "typeId": HALO_TICKET_TYPE_ID,
        "clientId": HALO_CLIENT_ID_NUM,
        "siteId": HALO_SITE_ID,
        "teamId": HALO_TEAM_ID,
        "impactId": int(impact_id),
        "urgencyId": int(urgency_id),
        "emailAddress": email
    }

    # ---- Eerste poging: contactId
    body = base_body | {"contactId": int(contact_id)}
    log.info(f"➡️ Ticket body (contactId):\n{json.dumps(body, indent=2)}")
    r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[body], timeout=15)

    # ---- Tweede poging: endUserId als eerste fout is 400
    if r.status_code == 400:
        log.warning("⚠️ Halo 400 bij contactId → probeer opnieuw met endUserId")
        body = base_body | {"endUserId": int(contact_id)}
        log.info(f"➡️ Ticket body (endUserId):\n{json.dumps(body, indent=2)}")
        r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[body], timeout=15)

    log.info(f"⬅️ Halo status {r.status_code}")

    if r.status_code in (200, 201):
        resp = r.json()
        ticket = resp[0] if isinstance(resp, list) else resp
        ticket_id = ticket.get("id") or ticket.get("ID")
        log.info(f"✅ Ticket aangemaakt ID={ticket_id}")

        note = (f"**Naam:** {contact_name}\n**E-mail:** {email}\n"
                f"**Probleem:** {omschrijving}\n\n"
                f"**Sinds:** {sindswanneer}\n"
                f"**Wat werkt niet:** {watwerktniet}\n"
                f"**Zelf geprobeerd:** {zelfgeprobeerd}\n"
                f"**Impact:** {impacttoelichting}")

        add_note_to_ticket(ticket_id, note, contact_name, email, room_id, contact_id)
        return {"ID": ticket_id, "Ref": f"BC-{ticket_id}", "contact_id": contact_id}
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
    r = requests.post(f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions",
                      headers=h, json=body, timeout=10)
    return r.status_code in (200, 201)

# --------------------------------------------------------------------------
# WEBEX HELPERS
# --------------------------------------------------------------------------
def send_message(room_id, text):
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS,
                  json={"roomId": room_id, "markdown": text}, timeout=10)

def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul formulier in:",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.0",
                "body": [
                    {"type": "TextBlock", "text": "E-mailadres", "weight": "Bolder"},
                    {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres", "isRequired": True},
                    {"type": "TextBlock", "text": "Probleemomschrijving", "weight": "Bolder"},
                    {"type": "Input.Text", "id": "omschrijving", "placeholder": "Probleemomschrijving", "isRequired": True, "isMultiline": True},
                    {"type": "TextBlock", "text": "Sinds wanneer?", "weight": "Bolder"},
                    {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Sinds wanneer?"},
                    {"type": "TextBlock", "text": "Wat werkt niet?", "weight": "Bolder"},
                    {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Wat werkt niet?"},
                    {"type": "TextBlock", "text": "Zelf geprobeerd?", "weight": "Bolder"},
                    {"type": "Input.Text", "id": "zelfgeprobeerd", "placeholder": "Zelf geprobeerd?", "isMultiline": True},
                    {"type": "TextBlock", "text": "Impact toelichting", "weight": "Bolder"},
                    {"type": "Input.Text", "id": "impacttoelichting", "placeholder": "Impact toelichting", "isMultiline": True}
                ],
                "actions": [{"type": "Action.Submit", "title": "Versturen"}]
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
            send_message(room_id, "📋 Vul formulier in.")
        else:
            for t_id, ri in ticket_room_map.items():
                if ri.get("room_id") == room_id:
                    add_note_to_ticket(t_id, text, sender, email=sender,
                                       room_id=room_id, contact_id=ri.get("contact_id"))

    elif res == "attachmentActions":
        act_id = data["data"]["id"]
        inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{act_id}", headers=WEBEX_HEADERS).json().get("inputs", {})
        if not inputs.get("email") or not inputs.get("omschrijving"):
            send_message(data["data"]["roomId"], "⚠️ Email en omschrijving verplicht.")
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
            ticket_room_map[ticket_id] = {"room_id": data["data"]["roomId"],
                                          "contact_id": ticket.get("contact_id")}
            ref = ticket.get("Ref", f"BC-{ticket_id}")
            send_message(data["data"]["roomId"], f"✅ Ticket aangemaakt: **{ref}**\n🔢 ID: {ticket_id}")

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
def initialize_cache():
    get_main_contacts()
    return {"status": "initialized", "cache_size": len(CONTACT_CACHE["contacts"])}

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
