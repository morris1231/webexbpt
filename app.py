import os, urllib.parse, logging, sys, time, threading, json
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
HALO_AUTH_URL       = os.getenv("HALO_AUTH_URL")
HALO_API_BASE       = os.getenv("HALO_API_BASE")
HALO_CLIENT_ID      = os.getenv("HALO_CLIENT_ID")
HALO_CLIENT_SECRET  = os.getenv("HALO_CLIENT_SECRET")
HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", 66))
HALO_CLIENT_ID_NUM  = int(os.getenv("HALO_CLIENT_ID_NUM", 12))
HALO_SITE_ID        = int(os.getenv("HALO_SITE_ID", 18))
WEBEX_TOKEN         = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"} if WEBEX_TOKEN else {}
USER_CACHE = {"users": [], "timestamp": 0, "source": "none"}
CACHE_DURATION = 24 * 60 * 60  # 24 uur
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
    r = requests.post(
        HALO_AUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(payload),
        timeout=10
    )
    r.raise_for_status()
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "Content-Type": "application/json"
    }
# --------------------------------------------------------------------------
# USERS OPHALEN
# --------------------------------------------------------------------------
def fetch_users(client_id: int, site_id: int):
    h = get_halo_headers()
    all_users = []
    page = 1
    per_page = 100
    while True:
        params = {"client_id": client_id, "site_id": site_id, "page": page, "per_page": per_page}
        r = requests.get(f"{HALO_API_BASE}/Users", headers=h, params=params, timeout=15)
        if r.status_code != 200:
            log.warning(f"⚠️ /Users pagina {page} gaf {r.status_code}: {r.text[:200]}")
            break
        users = r.json().get("users", []) or r.json().get("items", []) or r.json()
        if not users:
            break
        for u in users:
            u["id"] = int(u.get("id", 0))
            u["client_id"] = int(u.get("client_id", 0))
            u["site_id"] = int(u.get("site_id", 0))
            if (
                u["client_id"] == client_id
                and u["site_id"] == site_id
                and u.get("use") == "user"
                and not u.get("inactive", True)
                and u.get("emailaddress")
                and "@" in u["emailaddress"]
            ):
                all_users.append(u)
        if len(users) < per_page:
            break
        page += 1
    USER_CACHE["source"] = "/Users (paginated)"
    log.info(f"✅ {len(all_users)} users opgehaald")
    return all_users
def get_main_users():
    now = time.time()
    if USER_CACHE["users"] and (now - USER_CACHE["timestamp"] < CACHE_DURATION):
        return USER_CACHE["users"]
    USER_CACHE["users"] = fetch_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    USER_CACHE["timestamp"] = now
    return USER_CACHE["users"]
def get_halo_user(email: str, room_id=None):
    if not email:
        return None
    email = email.lower().strip()
    for u in get_main_users():
        for f in [
            u.get("EmailAddress"),
            u.get("emailaddress"),
            u.get("PrimaryEmail"),
            u.get("login"),
            u.get("email"),
            u.get("email1"),
        ]:
            if f and f.lower() == email:
                if room_id:
                    send_message(room_id, f"✅ Gebruiker {u.get('name')} gevonden · id={u.get('id')}")
                return u
    if room_id:
        send_message(room_id, f"⚠️ Geen gebruiker gevonden voor {email}")
    return None
# --------------------------------------------------------------------------
# TICKET AANMAKEN — gebruik user_id
# --------------------------------------------------------------------------
def create_halo_ticket(omschrijving, email, sindswanneer, watwerktniet,
                       zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    h = get_halo_headers()
    user = get_halo_user(email, room_id)
    if not user:
        if room_id:
            send_message(room_id, "❌ Geen gebruiker gevonden in Halo.")
        return None
    user_id  = int(user.get("id"))
    client_id = int(user.get("client_id", 0))
    site_id   = int(user.get("site_id", 0))
    ticket_data = {
        "summary": omschrijving[:100],
        "details": omschrijving,
        "tickettype_id": HALO_TICKET_TYPE_ID,
        "impact": int(impact_id),
        "urgency": int(urgency_id),
        "client_id": client_id,
        "site_id": site_id,
        "user_id": user_id   # FIX: uid vervangen door user_id (zoals door Halo support aangegeven)
    }
    log.info(f"➡️ Ticket data: {json.dumps(ticket_data, indent=2)}")
    try:
        # ✅ POST as array (Halo expects Faults[])
        r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[ticket_data], timeout=20)
        log.info(f"⬅️ Halo {r.status_code}: {r.text[:250]}")
        if r.status_code in (200, 201):
            resp = r.json()
            ticket = resp[0] if isinstance(resp, list) else resp
            ticket_id = ticket.get("id") or ticket.get("ID")
            msg = f"✅ Ticket aangemaakt: {ticket_id} | user_id={user_id}"
            log.info(msg)
            if room_id:
                send_message(room_id, msg)
            return {"ID": ticket_id, "user_id": user_id}
        else:
            log.warning(f"⚠️ Halo gaf status {r.status_code}")
            if room_id:
                send_message(room_id, f"⚠️ Halo gaf status {r.status_code}")
    except Exception as e:
        log.error(f"❌ Ticket aanmaken mislukt: {e}")
        if room_id:
            send_message(room_id, "❌ Ticket aanmaken mislukt, zie logs.")
    return None
# --------------------------------------------------------------------------
# WEBEX HELPERS
# --------------------------------------------------------------------------
def send_message(room_id, text):
    if not WEBEX_HEADERS:
        return
    try:
        requests.post(
            "https://webexapis.com/v1/messages",
            headers=WEBEX_HEADERS,
            json={"roomId": room_id, "markdown": text},
            timeout=10
        )
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
                "type": "AdaptiveCard",
                "version": "1.0",
                "body": [
                    {"type": "TextBlock", "text": "🆕 Nieuwe melding", "weight": "bolder"},
                    {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres van gebruiker", "required": True},
                    {"type": "Input.Text", "id": "omschrijving", "placeholder": "Korte omschrijving van het probleem", "required": True},
                    {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Sinds wanneer is het probleem aanwezig?"},
                    {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Wat werkt precies niet?"},
                    {"type": "Input.Text", "id": "zelfgeprobeerd", "placeholder": "Wat heb je zelf al geprobeerd?"},
                    {"type": "Input.Text", "id": "impacttoelichting", "placeholder": "Toelichting op impact (optioneel)"},
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
        log.error(f"❌ Adaptive card versturen mislukt: {e}")
# --------------------------------------------------------------------------
# WEBEX EVENTS
# --------------------------------------------------------------------------
def process_webex_event(data):
    res = data.get("resource")
    if res == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS).json()
        text, room_id, sender = msg.get("text", ""), msg.get("roomId"), msg.get("personEmail")
        if sender and sender.endswith("@webex.bot"):
            return
        if "nieuwe melding" in text.lower():
            send_adaptive_card(room_id)
    elif res == "attachmentActions":
        act_id = data["data"]["id"]
        inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{act_id}",
                              headers=WEBEX_HEADERS).json().get("inputs", {})
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
            impact_id, urgency_id,
            room_id=data["data"]["roomId"]
        )
        if ticket:
            send_message(data["data"]["roomId"], f"✅ Ticket aangemaakt: **{ticket['ID']}**")
        else:
            send_message(data["data"]["roomId"], "❌ Ticket kon niet worden aangemaakt.")
# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------
@app.route("/initialize", methods=["GET"])
def initialize():
    get_main_users()
    return {"status": "initialized",
            "cache_size": len(USER_CACHE['users']),
            "source": USER_CACHE["source"]}
@app.route("/webex", methods=["POST"])
def webhook():
    threading.Thread(target=process_webex_event, args=(request.json,)).start()
    return {"status": "ok"}
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok",
            "users_cached": len(USER_CACHE['users']),
            "source": USER_CACHE["source"]}
# --------------------------------------------------------------------------
# START
# --------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Start server op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
