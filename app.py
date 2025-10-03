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
HALO_CLIENT_ID_NUM  = int(os.getenv("HALO_CLIENT_ID_NUM", 986))
HALO_SITE_ID        = int(os.getenv("HALO_SITE_ID", 992))
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"} if WEBEX_TOKEN else {}
CONTACT_CACHE = {"users": [], "timestamp": 0, "source": "none"}  # ✅ Nu "users", niet "contacts"
CACHE_DURATION = 24 * 60 * 60  # ✅ FIX: was 24 _60_ 60 → syntaxfout!
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
# USERS ophalen — NU VOOR INTERNE USERS
# --------------------------------------------------------------------------
def fetch_users(client_id: int, site_id: int):
    h = get_halo_headers()
    all_users = []
    client_id = int(client_id)
    site_id = int(site_id)
    try:
        log.info(f"➡️ Probeer /Users met client_id={client_id}, site_id={site_id} ...")
        params = {"client_id": client_id, "site_id": site_id}
        r = requests.get(f"{HALO_API_BASE}/Users", headers=h, params=params, timeout=15)
        if r.status_code == 200:
            users = r.json().get('users', []) or r.json().get('items', []) or r.json()
            if users:
                for u in users:
                    u["user_id"] = u.get("id")  # ✅ Uniforme key
                    all_users.append(u)
                CONTACT_CACHE["source"] = "/Users"
                log.info(f"✅ {len(all_users)} users uit /Users")
                return all_users
        else:
            log.warning(f"⚠️ /Users gaf {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"❌ /Users faalde: {e}")
    return []

def get_main_users():
    now = time.time()
    if CONTACT_CACHE["users"] and (now - CONTACT_CACHE["timestamp"] < CACHE_DURATION):
        log.info(f"♻️ Cache gebruikt (source: {CONTACT_CACHE['source']}) - {len(CONTACT_CACHE['users'])} users")
        return CONTACT_CACHE["users"]
    log.info(f"🔄 Ophalen users voor client_id={HALO_CLIENT_ID_NUM}, site_id={HALO_SITE_ID}")
    CONTACT_CACHE["users"] = fetch_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    CONTACT_CACHE["timestamp"] = now
    log.info(f"✅ Cache bijgewerkt: {len(CONTACT_CACHE['users'])} users uit {CONTACT_CACHE['source']}")
    return CONTACT_CACHE["users"]

def get_halo_user(email: str, room_id=None):
    if not email: return None
    email = email.lower().strip()
    for u in get_main_users():
        if int(u.get("client_id", 0)) != HALO_CLIENT_ID_NUM or int(u.get("site_id", 0)) != HALO_SITE_ID:
            continue
        flds = [u.get("EmailAddress"), u.get("emailaddress"), u.get("PrimaryEmail"), u.get("login"), u.get("email"), u.get("email1")]
        for f in flds:
            if f and f.lower() == email:
                log.info("👉 Hele userrecord:")
                log.info(json.dumps(u, indent=2))
                if room_id:
                    send_message(room_id, f"✅ Gebruiker {u.get('name')} gevonden · id={u.get('id')} · via {CONTACT_CACHE['source']}")
                return u
    if room_id:
        send_message(room_id, f"⚠️ Geen gebruiker gevonden voor {email}")
    return None

# --------------------------------------------------------------------------
# TICKET CREATION — ALLEEN VOOR USERS (GEEN CONTACTS!)
# --------------------------------------------------------------------------
def create_halo_ticket(omschrijving, email, sindswanneer, watwerktniet,
                       zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    h = get_halo_headers()
    user = get_halo_user(email, room_id=room_id)
    if not user:
        if room_id:
            send_message(room_id, "❌ Geen gebruiker gevonden in Halo. Controleer e-mail en client/site-id.")
        return None

    user_id     = int(user.get("id"))
    client_id   = int(user.get("client_id", 0))
    site_id     = int(user.get("site_id", 0))

    # ✅ CRUCIAAL: Gebruik ONLY requestUserId — GEEN contactId voor users!
    base_body = {
        "summary": omschrijving[:100],
        "details": omschrijving,
        "typeId": HALO_TICKET_TYPE_ID,
        "teamId": HALO_TEAM_ID,
        "impact": int(impact_id),
        "urgency": int(urgency_id),
        "requestUserId": user_id,      # ✅ ENIGE NODIGE ID VOOR INTERNE USERS
        "client_id": client_id,        # ✅ Context
        "site_id": site_id,            # ✅ Context
        # "contactId": user_id,        # ❌ VERWIJDERD! Dit is voor contacts, niet voor users!
    }

    variants = [
        ("requestUserId-only", {**base_body}),
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
                return {"ID": ticket_id, "user_id": user_id}
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
                    {"type": "TextBlock", "text": "🆕 Nieuwe melding", "weight": "bolder"},
                    {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres van gebruiker", "required": True},
                    {"type": "Input.Text", "id": "omschrijving", "placeholder": "Korte omschrijving van het probleem", "required": True},
                    {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Sinds wanneer is het probleem aanwezig?"},
                    {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Wat werkt precies niet?"},
                    {"type": "Input.Text", "id": "zelfgeprobeerd", "placeholder": "Wat heb je zelf al geprobeerd?"},
                    {"type": "Input.Text", "id": "impacttoelichting", "placeholder": "Toelichting op impact (optioneel)"},
                    {
                        "type": "Input.ChoiceSet",
                        "id": "impact",
                        "label": "Impact",
                        "choices": [
                            {"title": "Gehele bedrijf (1)", "value": "1"},
                            {"title": "Meerdere gebruikers (2)", "value": "2"},
                            {"title": "Één gebruiker (3)", "value": "3"}
                        ],
                        "value": "3",
                        "required": True
                    },
                    {
                        "type": "Input.ChoiceSet",
                        "id": "urgency",
                        "label": "Urgency",
                        "choices": [
                            {"title": "High (1)", "value": "1"},
                            {"title": "Medium (2)", "value": "2"},
                            {"title": "Low (3)", "value": "3"}
                        ],
                        "value": "3",
                        "required": True
                    }
                ],
                "actions": [{"type": "Action.Submit", "title": "✅ Ticket aanmaken"}]
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
            impact_id = inputs.get("impact", "3")
            urgency_id = inputs.get("urgency", "3")
            ticket = create_halo_ticket(
                inputs["omschrijving"], inputs["email"],
                inputs.get("sindswanneer", "Niet opgegeven"),
                inputs.get("watwerktniet", "Niet opgegeven"),
                inputs.get("zelfgeprobeerd", "Niet opgegeven"),
                inputs.get("impacttoelichting", "Niet opgegeven"),
                impact_id,
                urgency_id,
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
        "/Users": f"{HALO_API_BASE}/Users?client_id={HALO_CLIENT_ID_NUM}&site_id={HALO_SITE_ID}"
    }.items():
        try:
            r = requests.get(url, headers=h, timeout=10)
            out[name] = {"status": r.status_code, "body": r.text[:500]}
        except Exception as e:
            out[name] = {"error": str(e)}
    return out

@app.route("/initialize", methods=["GET"])
def initialize():
    get_main_users()  # ✅ Nu get_main_users()
    return {"status":"initialized","cache_size":len(CONTACT_CACHE['users']),"source":CONTACT_CACHE["source"]}

@app.route("/", methods=["GET"])
def health():
    return {"status":"ok","users_cached":len(CONTACT_CACHE["users"]), "source":CONTACT_CACHE["source"]}

@app.route("/webex", methods=["POST"])
def webhook():
    threading.Thread(target=process_webex_event, args=(request.json,)).start()
    return {"status":"ok"}

# --------------------------------------------------------------------------
# START
# --------------------------------------------------------------------------
if __name__ == "__main__":  # ✅ FIX: was "**name**" → fout!
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Start server op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
