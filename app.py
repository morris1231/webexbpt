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

HALO_CLIENT_ID_NUM  = int(os.getenv("HALO_CLIENT_ID_NUM", 986))
HALO_SITE_ID        = int(os.getenv("HALO_SITE_ID", 992))
HALO_CUSTOMER_ID    = HALO_CLIENT_ID_NUM

# extra optionele velden (ticket type config)
HALO_CATEGORY_ID    = int(os.getenv("HALO_CATEGORY_ID", 0))
HALO_SERVICE_ID     = int(os.getenv("HALO_SERVICE_ID", 0))
HALO_SLA_ID         = int(os.getenv("HALO_SLA_ID", 0))

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
                return c
    return None

# --------------------------------------------------------------------------
# TICKET CREATION met full fallback matrix
# --------------------------------------------------------------------------
def create_halo_ticket(omschrijving, email, sindswanneer, watwerktniet,
                       zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    h = get_halo_headers()
    contact = get_halo_contact(email)
    if not contact:
        if room_id: send_message(room_id, f"⚠️ Geen contact gevonden in Halo voor {email}")
        return None

    contact_id = int(contact.get("id"))
    contact_name = contact.get("name", "Onbekend")

    base_body = {
        "summary": omschrijving[:100],
        "details": omschrijving,
        "typeId": HALO_TICKET_TYPE_ID,
        "teamId": HALO_TEAM_ID,
        "impactId": int(impact_id),
        "urgencyId": int(urgency_id),
        "emailAddress": email
    }

    requester_variants = ["requestContactId", "contactId", "requestUserId", "userId"]
    client_variants = [
        {"customerId": HALO_CUSTOMER_ID},
        {"clientId": HALO_CLIENT_ID_NUM, "siteId": HALO_SITE_ID}
    ]

    # extra velden varianten
    extra_variants = [ {} ]
    if HALO_CATEGORY_ID: extra_variants.append({"categoryId": HALO_CATEGORY_ID})
    if HALO_SERVICE_ID:  extra_variants.append({"serviceId": HALO_SERVICE_ID})
    if HALO_SLA_ID:      extra_variants.append({"slaId": HALO_SLA_ID})

    for client_block in client_variants:
        for req_field in requester_variants:
            for extra in extra_variants:
                body = base_body.copy()
                body.update(client_block)
                body[req_field] = contact_id
                body.update(extra)

                log.info(f"➡️ Try: {json.dumps(body)}")
                try:
                    r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[body], timeout=15)
                except Exception as e:
                    log.error(f"❌ Exception Halo call: {e}")
                    continue

                log.info(f"⬅️ Halo status {r.status_code} ({req_field}, {list(client_block.keys())}, extra={extra})")
                if r.status_code in (200, 201):
                    resp = r.json()
                    ticket = resp[0] if isinstance(resp, list) else resp
                    ticket_id = ticket.get("id") or ticket.get("ID") or "?"
                    log.info(f"✅ SUCCESS with {req_field} + {list(client_block.keys())} + {extra}, Ticket ID={ticket_id}")

                    note = (f"**Naam:** {contact_name}\n**E-mail:** {email}\n"
                            f"**Probleem:** {omschrijving}\n\n"
                            f"**Sinds:** {sindswanneer}\n"
                            f"**Wat werkt niet:** {watwerktniet}\n"
                            f"**Zelf geprobeerd:** {zelfgeprobeerd}\n"
                            f"**Impact:** {impacttoelichting}")
                    add_note_to_ticket(ticket_id, note, contact_name, email, room_id, contact_id)
                    return {"ID": ticket_id, "contact_id": contact_id}
                else:
                    log.warning(f"❌ Fail {req_field} + {list(client_block.keys())} + {extra} → {r.text[:250]}")

    if room_id:
        send_message(room_id, "⚠️ Ticket kon niet aangemaakt worden. Zie logs.")
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
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS,
                  json={"roomId": room_id, "markdown": text}, timeout=10)

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
            send_message(room_id, "📋 Vul formulier in (adaptive card kan hier)")
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
