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
    handlers=[logging.StreamHandler(sys.stdout)],
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

HALO_TICKET_TYPE_ID = 66   # ✅ correct type-id
HALO_TEAM_ID        = int(os.getenv("HALO_TEAM_ID", 1))
HALO_CLIENT_ID_NUM  = int(os.getenv("HALO_CLIENT_ID_NUM", 12))
HALO_SITE_ID        = int(os.getenv("HALO_SITE_ID", 18))

WEBEX_TOKEN  = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}",
                 "Content-Type": "application/json"} if WEBEX_TOKEN else {}

USER_CACHE = {"users": [], "timestamp": 0, "source": "none"}
CACHE_DURATION = 24 * 60 * 60  # 24h
ticket_room_map = {}

# --------------------------------------------------------------------------
# HALO TOKEN
# --------------------------------------------------------------------------
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all",
    }
    r = requests.post(
        HALO_AUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(payload),
        timeout=10,
    )
    if r.status_code != 200:
        raise Exception(f"Fout bij ophalen token: {r.status_code} - {r.text}")
    try:
        token = r.json().get("access_token")
    except ValueError:
        raise Exception(f"Response geen JSON: {r.text}")
    if not token:
        raise Exception(f"Geen access_token in response: {r.text}")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# --------------------------------------------------------------------------
# USERS
# --------------------------------------------------------------------------
def fetch_users(client_id: int, site_id: int):
    h = get_halo_headers()
    all_users = []
    page = 1
    per_page = 100
    while True:
        log.info(f"➡️ Ophalen pagina {page} van /Users met client_id={client_id}, site_id={site_id}")
        params = {"client_id": client_id, "site_id": site_id, "page": page, "per_page": per_page}
        r = requests.get(f"{HALO_API_BASE}/Users", headers=h, params=params, timeout=15)
        if r.status_code != 200:
            log.warning(f"⚠️ /Users {r.status_code}: {r.text[:200]}")
            break
        users = r.json().get("users", []) or r.json().get("items", []) or r.json()
        if not users:
            break
        for u in users:
            u["id"] = int(u.get("id", 0))
            u["client_id"] = int(u.get("client_id", 0))
            u["site_id"] = int(u.get("site_id", 0))
            u["user_id"] = u["id"]
            if (
                u["client_id"] == client_id
                and u["site_id"] == site_id
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
        log.info(f"♻️ Cache gebruikt ({USER_CACHE['source']})")
        return USER_CACHE["users"]
    log.info(f"🔄 Ophalen gebruikers client_id={HALO_CLIENT_ID_NUM}, site_id={HALO_SITE_ID}")
    USER_CACHE["users"] = fetch_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    USER_CACHE["timestamp"] = now
    return USER_CACHE["users"]

def get_halo_user(email: str, room_id=None):
    if not email:
        return None
    email = email.lower().strip()
    for u in get_main_users():
        for f in [u.get("emailaddress"), u.get("EmailAddress"), u.get("email")]:
            if f and f.lower() == email:
                if room_id:
                    send_message(room_id, f"✅ Gebruiker {u.get('name')} gevonden · id={u.get('id')}")
                return u
    if room_id:
        send_message(room_id, f"⚠️ Geen gebruiker gevonden voor {email}")
    return None

# --------------------------------------------------------------------------
# HALO TICKET CREATION (gecorrigeerd)
# --------------------------------------------------------------------------
def create_halo_ticket(omschrijving, email, sindswanneer, watwerktniet,
                       zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    h = get_halo_headers()
    user = get_halo_user(email, room_id=room_id)
    if not user:
        if room_id:
            send_message(room_id, "❌ Geen gebruiker gevonden in Halo.")
        return None

    user_id   = int(user.get("id"))
    client_id = int(user.get("client_id", HALO_CLIENT_ID_NUM))
    site_id   = int(user.get("site_id", HALO_SITE_ID))

    body = {
        "summary": omschrijving[:100],
        "details": omschrijving,
        "teamid": HALO_TEAM_ID,
        "impact": int(impact_id),
        "urgency": int(urgency_id),
        "clientid": client_id,
        "siteid": site_id,
        "typeid": HALO_TICKET_TYPE_ID,      # ✅ lowercase veld
        "requestedbyid": user_id,           # ✅ lowercase veld
    }

    log.info(f"➡️ Ticket sturen naar Halo: {json.dumps(body, indent=2)}")
    try:
        r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=body, timeout=20)
    except Exception as e:
        log.error(f"❌ Fout bij HTTP-call: {e}")
        if room_id:
            send_message(room_id, f"❌ Fout bij aanmaken ticket: {e}")
        return None

    log.info(f"⬅️ Halo {r.status_code}: {r.text[:250]}")
    if r.status_code in (200, 201):
        try:
            resp = r.json()
        except ValueError:
            resp = None
        ticket_id = None
        if isinstance(resp, dict):
            ticket_id = resp.get("id") or resp.get("ID")
        elif isinstance(resp, list) and resp:
            ticket_id = resp[0].get("id") or resp[0].get("ID")

        msg = f"✅ Ticket aangemaakt · ID={ticket_id} · user={user.get('name')}"
        log.info(msg)
        if room_id:
            send_message(room_id, msg)
        return {"ID": ticket_id, "user_id": user_id}

    fout = f"❌ Ticket niet aangemaakt: {r.status_code} → {r.text}"
    log.error(fout)
    if room_id:
        send_message(room_id, fout)
    return None

# --------------------------------------------------------------------------
# WEBEX HELPERS  (ongewijzigd)
# --------------------------------------------------------------------------
def send_message(room_id, text):
    if WEBEX_HEADERS:
        try:
            requests.post("https://webexapis.com/v1/messages",
                          headers=WEBEX_HEADERS,
                          json={"roomId": room_id, "markdown": text},
                          timeout=10)
        except Exception as e:
            log.error(f"❌ Webex bericht versturen mislukt: {e}")

def send_adaptive_card(room_id):
    payload = {"roomId": room_id, "text": "✍ Vul dit formulier in:", "attachments": [{
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.0",
            "body": [
                {"type": "TextBlock", "text": "🆕 Nieuwe melding", "weight": "bolder"},
                {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres van gebruiker", "required": True},
                {"type": "Input.Text", "id": "omschrijving", "placeholder": "Korte omschrijving", "required": True},
                {"type": "Input.Text", "id": "impacttoelichting", "placeholder": "Impact toelichting"},
                {"type": "Input.ChoiceSet", "id": "impact",
                 "choices": [{"title": "Gehele bedrijf (1)", "value": "1"},
                             {"title": "Meerdere gebruikers (2)", "value": "2"},
                             {"title": "Één gebruiker (3)", "value": "3"}],
                 "value": "3"},
                {"type": "Input.ChoiceSet", "id": "urgency",
                 "choices": [{"title": "High (1)", "value": "1"},
                             {"title": "Medium (2)", "value": "2"},
                             {"title": "Low (3)", "value": "3"}],
                 "value": "3"}
            ],
            "actions": [{"type": "Action.Submit", "title": "✅ Ticket aanmaken"}],
        }}]}
    try:
        requests.post("https://webexapis.com/v1/messages",
                      headers=WEBEX_HEADERS, json=payload, timeout=10)
    except Exception as e:
        log.error(f"❌ Adaptive card versturen mislukt: {e}")

# --------------------------------------------------------------------------
# WEBEX EVENTS
# --------------------------------------------------------------------------
def process_webex_event(data):
    res = data.get("resource")
    if res == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}",
                           headers=WEBEX_HEADERS).json()
        text, room_id, sender = msg.get("text", ""), msg.get("roomId"), msg.get("personEmail")
        if sender and sender.endswith("@webex.bot"):
            return
        if "nieuwe melding" in text.lower():
            send_adaptive_card(room_id)
    elif res == "attachmentActions":
        act_id = data["data"]["id"]
        inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{act_id}",
                              headers=WEBEX_HEADERS).json().get("inputs", {})
        room_id = data["data"]["roomId"]
        if not inputs.get("email") or not inputs.get("omschrijving"):
            send_message(room_id, "⚠️ E‑mail en omschrijving zijn verplicht.")
            return
        impact_id = inputs.get("impact", "3")
        urgency_id = inputs.get("urgency", "3")
        ticket = create_halo_ticket(
            inputs["omschrijving"], inputs["email"], "",
            "", "", inputs.get("impacttoelichting", ""), impact_id, urgency_id, room_id
        )
        if ticket:
            send_message(room_id, f"✅ Ticket aangemaakt: **{ticket['ID']}**")
        else:
            send_message(room_id, "❌ Ticket kon niet worden aangemaakt. Controleer de logs.")

# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------
@app.route("/initialize", methods=["GET"])
def initialize():
    get_main_users()
    return {"status": "initialized",
            "cache_size": len(USER_CACHE["users"]),
            "source": USER_CACHE["source"]}

@app.route("/users-cache", methods=["GET"])
def users_cache():
    if not USER_CACHE["users"]:
        return {"error": "Geen gebruikers in cache, roep /initialize eerst aan."}, 404
    return {"total": len(USER_CACHE["users"]),
            "source": USER_CACHE["source"],
            "timestamp": USER_CACHE["timestamp"]}

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "cache": len(USER_CACHE["users"])}

@app.route("/webex", methods=["POST"])
def webhook():
    threading.Thread(target=process_webex_event, args=(request.json,)).start()
    return {"status": "ok"}

# --------------------------------------------------------------------------
# START
# --------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Start server op poort {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
