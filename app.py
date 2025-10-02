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

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"} if WEBEX_TOKEN else {}

CONTACT_CACHE = {"contacts": [], "timestamp": 0, "source": "none"}
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
# CONTACTS ophalen (We weten: bij jou alleen via /Users?type=contact)
# --------------------------------------------------------------------------
def fetch_all_contacts_with_fallback(client_id: int, site_id: int):
    h = get_halo_headers()
    all_contacts, processed_ids = [], set()

    log.info("➡️ Gebruik /Users?type=contact, andere endpoints bestaan niet in jouw omgeving...")
    params = {"type": "contact", "client_id": client_id, "site_id": site_id}
    r = requests.get(f"{HALO_API_BASE}/Users", headers=h, params=params, timeout=15)
    if r.status_code == 200:
        contacts = r.json().get('users', []) or r.json().get('items', []) or r.json()
        if contacts:
            for c in contacts:
                cid = str(c.get("id", ""))
                if cid and cid not in processed_ids:
                    processed_ids.add(cid)
                    c["client_id"] = int(c.get("client_id") or client_id)
                    c["site_id"]   = int(float(c.get("site_id") or site_id))
                    all_contacts.append(c)
            log.info(f"✅ {len(all_contacts)} eindgebruikers via /Users?type=contact")
            CONTACT_CACHE["source"] = "/Users?type=contact"
            return all_contacts
    else:
        log.error(f"❌ /Users?type=contact gaf {r.status_code} {r.text}")

    return []

def get_main_contacts():
    now = time.time()
    if CONTACT_CACHE["contacts"] and (now - CONTACT_CACHE["timestamp"] < CACHE_DURATION):
        return CONTACT_CACHE["contacts"]
    CONTACT_CACHE["contacts"] = fetch_all_contacts_with_fallback(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    CONTACT_CACHE["timestamp"] = now
    return CONTACT_CACHE["contacts"]

def get_halo_contact(email: str, room_id=None):
    if not email: 
        return None
    email = email.lower().strip()
    for c in get_main_contacts():
        for f in [c.get("EmailAddress"), c.get("emailaddress"), c.get("PrimaryEmail"), c.get("login")]:
            if f and f.lower() == email:
                log.info("👉 Hele contactrecord gevonden:")
                log.info(json.dumps(c, indent=2))
                if room_id:
                    send_message(room_id, f"✅ Eindgebruiker {c.get('name')} gevonden · ID={c.get('id')} key={c.get('key')} · via {CONTACT_CACHE['source']}")
                return c
    log.warning(f"⚠️ Geen eindgebruiker gevonden voor {email}")
    if room_id: send_message(room_id, f"⚠️ Geen eindgebruiker gevonden voor {email}")
    return None

# --------------------------------------------------------------------------
# TICKET CREATION - test alle varianten (id & key)
# --------------------------------------------------------------------------
def create_halo_ticket(omschrijving, email, sindswanneer, watwerktniet,
                       zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    h = get_halo_headers()
    contact = get_halo_contact(email, room_id=room_id)
    if not contact:
        return None

    contact_id = int(contact.get("id"))
    contact_key = int(contact.get("key") or contact_id)
    client_id  = int(contact.get("client_id") or HALO_CLIENT_ID_NUM)
    site_id    = int(contact.get("site_id") or HALO_SITE_ID)

    base_body = {
        "summary": omschrijving[:100],
        "details": omschrijving,
        "typeId": HALO_TICKET_TYPE_ID,
        "teamId": HALO_TEAM_ID,
        "impactId": int(impact_id),
        "urgencyId": int(urgency_id),
        "emailAddress": email,
        "clientId": client_id,
        "siteId": site_id
    }

    variants = [
        ("requestContactId-id", {**base_body, "requestContactId": contact_id}),
        ("requestContactId-key", {**base_body, "requestContactId": contact_key}),
        ("requestUserId-id",    {**base_body, "requestUserId": contact_id}),
        ("requestUserId-key",   {**base_body, "requestUserId": contact_key}),
        ("userId-id",           {**base_body, "userId": contact_id}),
        ("userId-key",          {**base_body, "userId": contact_key}),
        ("users-array-id",      {**base_body, "users": [{"id": contact_id}]}),
        ("users-array-key",     {**base_body, "users": [{"id": contact_key}]}),
        ("endUserId-id",        {**base_body, "endUserId": contact_id}),
        ("endUserId-key",       {**base_body, "endUserId": contact_key}),
        ("customerId+reqContact-id", {**base_body, "customerId": client_id, "requestContactId": contact_id}),
        ("customerId+reqContact-key", {**base_body, "customerId": client_id, "requestContactId": contact_key}),
    ]

    for name, body in variants:
        log.info(f"➡️ Probeer variant {name}: {json.dumps(body)}")
        r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[body], timeout=20)
        log.info(f"⬅️ Halo {r.status_code} ({name}) → {r.text[:250]}")
        if r.status_code in (200, 201):
            resp = r.json()
            ticket = resp[0] if isinstance(resp, list) else resp
            ticket_id = ticket.get("id") or ticket.get("ID")
            msg = f"✅ Ticket aangemaakt via {name} → TicketID={ticket_id}"
            log.info(msg)
            if room_id: send_message(room_id, msg)
            return {"ID": ticket_id, "contact_id": contact_id}

    if room_id:
        send_message(room_id, "❌ Geen enkele variant werkte. Zie logs en debug-halo.")
    return None

# --------------------------------------------------------------------------
# WEBEX HELPERS (kort gehouden)
# --------------------------------------------------------------------------
def send_message(room_id, text):
    if WEBEX_HEADERS:
        requests.post("https://webexapis.com/v1/messages",
                      headers=WEBEX_HEADERS,
                      json={"roomId": room_id, "markdown": text}, timeout=10)

# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------
@app.route("/debug-halo", methods=["GET"])
def debug_halo():
    h = get_halo_headers()
    out = {}
    endpoints = {
        "/Users?type=contact": (f"{HALO_API_BASE}/Users", {"type": "contact", "client_id": HALO_CLIENT_ID_NUM, "site_id": HALO_SITE_ID})
    }
    for name, (url, params) in endpoints.items():
        try:
            r = requests.get(url, headers=h, params=params, timeout=10)
            out[name] = {"status": r.status_code, "body": r.text[:500]}
        except Exception as e:
            out[name] = {"error": str(e)}
    return out

@app.route("/initialize", methods=["GET"])
def initialize():
    get_main_contacts()
    return {"status": "initialized", "cache_size": len(CONTACT_CACHE['contacts']), "source": CONTACT_CACHE["source"]}

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "contacts_cached": len(CONTACT_CACHE['contacts']), "source": CONTACT_CACHE['source']}

# --------------------------------------------------------------------------
# START
# --------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Start server op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
