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

# Controleer essentiële variabelen
required = ["HALO_AUTH_URL", "HALO_API_BASE", "HALO_CLIENT_ID", "HALO_CLIENT_SECRET"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    log.critical(f"❌ Ontbrekende .env-variabelen: {missing}")
    sys.exit(1)

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
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"} if WEBEX_TOKEN else {}
CONTACT_CACHE = {"contacts": [], "timestamp": 0, "source": "none"}
CACHE_DURATION = 24 * 60 * 60  # ✅ GEFIXT: was 24 _60_ 60 → SYNTAXERROR
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
# CONTACTS ophalen - eerst ClientContactLinks proberen, dan Users?type=contact
# --------------------------------------------------------------------------
def fetch_contacts(client_id: int, site_id: int):
    h = get_halo_headers()
    all_contacts = []
    client_id = int(client_id)
    site_id = int(site_id)

    # 1. Probeer ClientContactLinks
    try:
        log.info(f"➡️ Probeer /ClientContactLinks met client_id={client_id}, site_id={site_id} ...")
        r = requests.get(f"{HALO_API_BASE}/ClientContactLinks", headers=h, params={"client_id": client_id, "site_id": site_id}, timeout=15)
        if r.status_code == 200:
            contacts = r.json().get('contacts') or r.json().get('items') or r.json()
            if contacts:
                for c in contacts:
                    c["link_id"] = c.get("id")
                    all_contacts.append(c)
                CONTACT_CACHE["source"] = "/ClientContactLinks"
                log.info(f"✅ {len(all_contacts)} contacten uit /ClientContactLinks")
                return all_contacts
        else:
            log.warning(f"⚠️ ClientContactLinks gaf {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"❌ ClientContactLinks faalde: {e}")

    # 2. Fallback Users?type=contact
    try:
        log.info(f"➡️ Probeer /Users?type=contact met client_id={client_id}, site_id={site_id} ...")
        params = {"type": "contact", "client_id": client_id, "site_id": site_id}
        r = requests.get(f"{HALO_API_BASE}/Users", headers=h, params=params, timeout=15)
        if r.status_code == 200:
            contacts = r.json().get('users', []) or r.json().get('items', []) or r.json()
            if contacts:
                for c in contacts:
                    c["link_id"] = c.get("id")
                    all_contacts.append(c)
                CONTACT_CACHE["source"] = "/Users?type=contact"
                log.info(f"✅ {len(all_contacts)} contacten uit /Users?type=contact")
                return all_contacts
        else:
            log.warning(f"⚠️ Users?type=contact gaf {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"❌ Users?type=contact faalde: {e}")

    return []

def get_main_contacts():
    now = time.time()
    if CONTACT_CACHE["contacts"] and (now - CONTACT_CACHE["timestamp"] < CACHE_DURATION):
        log.info(f"♻️ Cache gebruikt (source: {CONTACT_CACHE['source']}) - {len(CONTACT_CACHE['contacts'])} contacten")
        return CONTACT_CACHE["contacts"]

    log.info(f"🔄 Ophalen contacten voor client_id={HALO_CLIENT_ID_NUM}, site_id={HALO_SITE_ID}")
    CONTACT_CACHE["contacts"] = fetch_contacts(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    CONTACT_CACHE["timestamp"] = now
    log.info(f"✅ Cache bijgewerkt: {len(CONTACT_CACHE['contacts'])} contacten uit {CONTACT_CACHE['source']}")
    return CONTACT_CACHE["contacts"]

def get_halo_contact(email: str, room_id=None):
    if not email: return None
    email = email.lower().strip()
    for c in get_main_contacts():
        # ✅ Alleen contacten van client 986 en site 992 accepteren
        if int(c.get("client_id", 0)) != HALO_CLIENT_ID_NUM or int(c.get("site_id", 0)) != HALO_SITE_ID:
            continue
        flds = [c.get("EmailAddress"), c.get("emailaddress"), c.get("PrimaryEmail"), c.get("login"), c.get("email"), c.get("email1")]
        for f in flds:
            if f and f.lower() == email:
                log.info("👉 Hele contactrecord:")
                log.info(json.dumps(c, indent=2))
                if room_id:
                    send_message(room_id, f"✅ Eindgebruiker {c.get('name')} gevonden · id={c.get('id')} link_id={c.get('link_id')} · via {CONTACT_CACHE['source']}")
                return c
    if room_id:
        send_message(room_id, f"⚠️ Geen eindgebruiker gevonden voor {email}")
    return None

# --------------------------------------------------------------------------
# TICKET CREATION - HALOPSA COMPATIBEL: GEEN requestContactId, GEEN endUserId — ALLEEN contactId
# --------------------------------------------------------------------------
def create_halo_ticket(omschrijving, email, sindswanneer, watwerktniet,
                       zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    h = get_halo_headers()
    contact = get_halo_contact(email, room_id=room_id)
    if not contact:
        if room_id:
            send_message(room_id, "❌ Geen contact gevonden in Halo. Controleer e-mail en client/site-id.")
        return None

    contact_id  = int(contact.get("id"))
    client_id   = int(contact.get("client_id") or HALO_CLIENT_ID_NUM)
    site_id     = int(contact.get("site_id") or HALO_SITE_ID)

    base_body = {
        "summary": omschrijving[:100],
        "details": omschrijving,
        "typeId": HALO_TICKET_TYPE_ID,
        "teamId": HALO_TEAM_ID,
        "impactId": int(impact_id),
        "urgencyId": int(urgency_id),
        "clientId": client_id,
        "siteId": site_id,
        "emailAddress": email
    }

    # ✅ HALOPSA: ÉÉN ENDELIJKE GELDIGE VARIANT — ALLEEN contactId werkt!
    variants = [
        ("contactId", {**base_body, "contactId": contact_id}),
    ]

    for name, body in variants:
        log.info(f"➡️ Try variant {name}: {json.dumps(body, indent=2)[:300]}...")
        try:
            r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[body], timeout=20)
            log.info(f"⬅️ Halo {r.status_code} ({name}) → {r.text[:250]}")
            if r.status_code in (200, 201):
                resp = r.json()
                ticket = resp[0] if isinstance(resp, list) else resp
                ticket_id = ticket.get("id") or ticket.get("ID")
                msg = f"✅ Ticket gelukt via {name} → TicketID={ticket_id}"
                log.info(msg)
                if room_id: send_message(room_id, msg)
                return {"ID": ticket_id, "contact_id": contact_id}
        except Exception as e:
            log.error(f"❌ Request faalde bij {name}: {e}")

    if room_id:
        send_message(room_id, "❌ Geen enkele variant werkte, zie logs.")
    return None

# --------------------------------------------------------------------------
# WEBEX HELPERS
# --------------------------------------------------------------------------
def send_message(room_id, text):
    if WEBEX_HEADERS:
        try:
            requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS,
                          json={"roomId": room_id, "markdown": text}, timeout=10)
        except Exception as e:
            log.error(f"❌ Webex bericht versturen mislukt: {e}")

def send_adaptive_card(room_id):
    payload = {
        "roomId": room_id,
        "text": "✍ Vul dit formulier in:",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.0",
                "body": [
                    {"type": "TextBlock", "text": "Nieuwe melding", "weight": "bolder"},
                    {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres"},
                    {"type": "Input.Text", "id": "omschrijving", "placeholder": "Probleemomschrijving", "style": "text"},
                    {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Sinds wanneer?"},
                    {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Wat werkt niet?"},
                    {"type": "Input.Text", "id": "zelfgeprobeerd", "placeholder": "Zelf geprobeerd?", "style": "text"},
                    {"type": "Input.Text", "id": "impacttoelichting", "placeholder": "Impact toelichting", "style": "text"}
                ],
                "actions": [{"type": "Action.Submit", "title": "Versturen"}]
            }
        }]
    }
    try:
        requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=payload, timeout=10)
    except Exception as e:
        log.error(f"❌ Adaptive card versturen mislukt: {e}")

# --------------------------------------------------------------------------
# WEBEX EVENTS
# --------------------------------------------------------------------------
def process_webex_event(data):
    res = data.get("resource")
    if res == "messages":
        msg_id = data["data"]["id"]
        try:
            msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS).json()
            text, room_id, sender = msg.get("text", ""), msg.get("roomId"), msg.get("personEmail")
            if sender and sender.endswith("@webex.bot"): return
            if "nieuwe melding" in text.lower():
                send_adaptive_card(room_id)
        except Exception as e:
            log.error(f"❌ Ophalen Webex bericht mislukt: {e}")
    elif res == "attachmentActions":
        act_id = data["data"]["id"]
        try:
            inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{act_id}", headers=WEBEX_HEADERS).json().get("inputs", {})
            if not inputs.get("email") or not inputs.get("omschrijving"):
                send_message(data["data"]["roomId"], "⚠️ E-mail en omschrijving zijn verplicht.")
                return
            ticket = create_halo_ticket(
                inputs["omschrijving"], inputs["email"],
                inputs.get("sindswanneer", "Niet opgegeven"),
                inputs.get("watwerktniet", "Niet opgegeven"),
                inputs.get("zelfgeprobeerd", "Niet opgegeven"),
                inputs.get("impacttoelichting", "Niet opgegeven"),
                inputs.get("impact", HALO_DEFAULT_IMPACT),
                inputs.get("urgency", HALO_DEFAULT_URGENCY),
                room_id=data["data"]["roomId"]
            )
            if ticket:
                send_message(data["data"]["roomId"], f"✅ Ticket aangemaakt: **{ticket['ID']}**")
            else:
                send_message(data["data"]["roomId"], "❌ Ticket kon niet worden aangemaakt. Controleer de logs.")
        except Exception as e:
            log.error(f"❌ Verwerken Adaptive Card mislukt: {e}")

# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------
@app.route("/debug-halo", methods=["GET"])
def debug_halo():
    h = get_halo_headers()
    out = {}
    for name, url in {
        "/ClientContactLinks": f"{HALO_API_BASE}/ClientContactLinks?client_id={HALO_CLIENT_ID_NUM}&site_id={HALO_SITE_ID}",
        "/Users?type=contact": f"{HALO_API_BASE}/Users?type=contact&client_id={HALO_CLIENT_ID_NUM}&site_id={HALO_SITE_ID}"
    }.items():
        try:
            r = requests.get(url, headers=h, timeout=10)
            out[name] = {"status": r.status_code, "body": r.text[:500]}
        except Exception as e:
            out[name] = {"error": str(e)}
    return out

@app.route("/initialize", methods=["GET"])
def initialize():
    get_main_contacts()
    return {"status":"initialized","cache_size":len(CONTACT_CACHE['contacts']),"source":CONTACT_CACHE["source"]}

@app.route("/", methods=["GET"])
def health():
    return {"status":"ok","contacts_cached":len(CONTACT_CACHE["contacts"]), "source":CONTACT_CACHE["source"]}

@app.route("/webex", methods=["POST"])
def webhook():
    threading.Thread(target=process_webex_event, args=(request.json,)).start()
    return {"status":"ok"}

# --------------------------------------------------------------------------
# START
# --------------------------------------------------------------------------
if __name__ == "__main__":  # ✅ GEFIXT: was **name** → __name__
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Start server op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
