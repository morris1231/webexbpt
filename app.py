import os, requests, urllib.parse, json, logging, sys, time
from flask import Flask, request
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Logging config
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("ticketbot")

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
TARGET_URL = os.getenv("WEBEX_TARGET_URL", "https://webexbpt-1.onrender.com/webex")

WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}

HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE = os.getenv("HALO_API_BASE", "").strip()

HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", "55"))
HALO_TEAM_ID = int(os.getenv("HALO_TEAM_ID", "1"))
HALO_DEFAULT_IMPACT = int(os.getenv("HALO_IMPACT", "3"))
HALO_DEFAULT_URGENCY = int(os.getenv("HALO_URGENCY", "3"))
HALO_ACTIONTYPE_PUBLIC = int(os.getenv("HALO_ACTIONTYPE_PUBLIC", "78"))

# Specifieke klant en site
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))
HALO_SITE_ID = int(os.getenv("HALO_SITE_ID", "18"))

ticket_room_map = {}

# ------------------------------------------------------------------------------
# Webex Webhook auto-management
# ------------------------------------------------------------------------------
def get_webhooks():
    r = requests.get("https://webexapis.com/v1/webhooks", headers=WEBEX_HEADERS)
    r.raise_for_status()
    return r.json().get("items", [])

def delete_webhook(webhook_id):
    r = requests.delete(f"https://webexapis.com/v1/webhooks/{webhook_id}", headers=WEBEX_HEADERS)
    if r.status_code == 204:
        log.info(f"🗑️ Webhook {webhook_id} verwijderd")
    else:
        log.warning(f"⚠️ Kon webhook {webhook_id} niet verwijderen: {r.status_code} {r.text}")

def create_webhook(name, resource, event):
    body = {"name": name, "targetUrl": TARGET_URL, "resource": resource, "event": event}
    r = requests.post("https://webexapis.com/v1/webhooks", headers=WEBEX_HEADERS, json=body)
    if r.status_code == 200:
        log.info(f"✅ Webhook '{name}' ({resource}/{event}) aangemaakt")
    else:
        log.error(f"❌ Kon webhook '{name}' niet maken: {r.status_code} {r.text}")

def ensure_webhook(name, resource, event):
    existing_hooks = get_webhooks()
    matching = [
        h for h in existing_hooks
        if h["resource"] == resource and h["event"] == event and h["targetUrl"] == TARGET_URL
    ]
    if len(matching) == 0:
        create_webhook(name, resource, event)
    elif len(matching) == 1:
        log.info(f"👍 Webhook '{name}' ({resource}/{event}) bestaat al")
    else:
        log.warning(f"⚠️ Dubbele webhooks gevonden voor {resource}/{event}, opschonen...")
        for h in matching[1:]:
            delete_webhook(h["id"])

def ensure_all_webhooks():
    log.info("🔎 Controleren/maken van benodigde Webex webhooks...")
    ensure_webhook("TicketbotMessages", "messages", "created")
    ensure_webhook("TicketbotAttachments", "attachmentActions", "created")
    log.info("✅ Webhooks staan correct ingesteld")

# ------------------------------------------------------------------------------
# Halo user cache helpers
# ------------------------------------------------------------------------------
USER_CACHE = {"users": [], "timestamp": 0}
CACHE_TTL = 300  # 5 min

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
        timeout=15
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

def fetch_all_client_users(client_id: int):
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50
    while True:
        url = f"{HALO_API_BASE}/Users?$filter=ClientID eq {client_id}&pageSize={page_size}&pageNumber={page}"
        r = requests.get(url, headers=h, timeout=30)
        if r.status_code != 200: break
        users = r.json().get("users", [])
        if not users: break
        all_users.extend(users)
        if len(users) < page_size: break
        page += 1
    return all_users

def get_main_users(force=False):
    now = time.time()
    if not force and USER_CACHE["users"] and now - USER_CACHE["timestamp"] < CACHE_TTL:
        return USER_CACHE["users"]

    all_users = fetch_all_client_users(HALO_CLIENT_ID_NUM)
    main_users = [u for u in all_users if str(u.get("site_id")) == str(HALO_SITE_ID)
                                        or str(u.get("site_name","")).lower() == "main"]
    USER_CACHE["users"] = main_users
    USER_CACHE["timestamp"] = now
    log.info(f"✅ Cache vernieuwd: {len(main_users)} Bossers & Cnossen/Main users")
    return main_users

def get_halo_user_id(email: str):
    if not email: return None
    users = get_main_users()
    email = email.strip().lower()
    for u in users:
        emails = {
            str(u.get("emailaddress") or "").lower(),
            str(u.get("networklogin") or "").lower(),
            str(u.get("adobject") or "").lower()
        }
        if email in emails:
            return u.get("id")
    return None

def preload_user_cache():
    log.info("🔄 Preloading Halo user cache…")
    users = get_main_users(force=True)
    log.info(f"✅ {len(users)} Main-users cached at startup.")

# ------------------------------------------------------------------------------
# Webex helpers
# ------------------------------------------------------------------------------
def send_message(room_id, text):
    requests.post("https://webexapis.com/v1/messages",
                  headers=WEBEX_HEADERS,
                  json={"roomId": room_id, "markdown": text})

def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul het formulier hieronder in:",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": [
                    {"type": "Input.Text", "id": "name", "placeholder": "Naam"},
                    {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres"},
                    {"type": "Input.Text", "id": "omschrijving", "isMultiline": True, "placeholder": "Probleemomschrijving"},
                    {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Sinds wanneer?"},
                    {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Wat werkt niet?"},
                    {"type": "Input.Text", "id": "zelfgeprobeerd", "isMultiline": True, "placeholder": "Zelf geprobeerd?"},
                    {"type": "Input.Text", "id": "impacttoelichting", "isMultiline": True,"placeholder": "Impact toelichting"},
                ],
                "actions": [{"type": "Action.Submit", "title": "Versturen"}]
            }
        }]}
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=card)

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    resource = data.get("resource")

    if resource == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS).json()
        text = msg.get("text", "").strip()
        room_id = msg.get("roomId")
        sender = msg.get("personEmail")
        if sender and sender.endswith("@webex.bot"): return {"status": "ignored"}
        if "nieuwe melding" in text.lower():
            send_adaptive_card(room_id)
            send_message(room_id, "📋 Vul het formulier hierboven in om een ticket te starten.")
        else:
            for t_id, rid in ticket_room_map.items():
                if rid == room_id:
                    add_note_to_ticket(t_id, text, sender, email=sender, room_id=room_id)

    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{action_id}", headers=WEBEX_HEADERS).json().get("inputs", {})
        naam = inputs.get("name", "Onbekend")
        email = inputs.get("email", "")
        omschrijving = inputs.get("omschrijving", "")
        sindswanneer = inputs.get("sindswanneer", "")
        watwerktniet = inputs.get("watwerktniet", "")
        zelfgeprobeerd = inputs.get("zelfgeprobeerd", "")
        impacttoelichting = inputs.get("impacttoelichting", "")
        impact_id = inputs.get("impact", str(HALO_DEFAULT_IMPACT))
        urgency_id = inputs.get("urgency", str(HALO_DEFAULT_URGENCY))
        room_id = data["data"]["roomId"]
        summary = omschrijving or "Melding via Webex"

        ticket = create_halo_ticket(summary, naam, email,
                                    omschrijving, sindswanneer,
                                    watwerktniet, zelfgeprobeerd,
                                    impacttoelichting, impact_id, urgency_id,
                                    room_id=room_id)
        if ticket:
            ticket_room_map[ticket["id"]] = room_id
            send_message(room_id, f"✅ Ticket aangemaakt: **{ticket['ref']}**")
    return {"status": "ok"}

@app.route("/halo", methods=["POST"])
def halo_webhook():
    data = request.json
    t_id = data.get("TicketID") or data.get("Request", {}).get("ID")
    if not t_id or int(t_id) not in ticket_room_map: return {"status": "ignored"}
    h = get_halo_headers()

    # Status updates
    t_detail = requests.get(f"{HALO_API_BASE}/Tickets/{t_id}", headers=h, timeout=30)
    if t_detail.status_code == 200:
        status = t_detail.json().get("StatusName") or t_detail.json().get("Status")
        if status:
            send_message(ticket_room_map[int(t_id)], f"🔄 Status update: {status}")

    # Notes
    r = requests.get(f"{HALO_API_BASE}/Tickets/{t_id}/Actions", headers=h, timeout=30)
    if r.status_code == 200 and r.json():
        actions = r.json()
        last = sorted(actions, key=lambda x: x.get("ID", 0), reverse=True)[0]
        note = last.get("Details")
        created_by = last.get("User", {}).get("Name", "Onbekend")
        if note and not last.get("IsPrivate", False):
            send_message(ticket_room_map[int(t_id)], f"💬 Halo update door {created_by}:\n\n{note}")
    return {"status": "ok"}

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}

# ------------------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    ensure_all_webhooks()   # ✅ Webex webhooks zetten
    preload_user_cache()    # ✅ Halo users cache preload
    log.info("🚀 Ticketbot gestart – Webhooks & Cache actief, klaar voor gebruik 🎉")
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
