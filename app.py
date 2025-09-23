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

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")  # Jouw Bot token
WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}
TARGET_URL = os.getenv("WEBEX_TARGET_URL", "https://webexbpt-1.onrender.com/webex")

HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE = os.getenv("HALO_API_BASE", "").strip()

HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", "55"))
HALO_TEAM_ID = int(os.getenv("HALO_TEAM_ID", "1"))
HALO_DEFAULT_IMPACT = int(os.getenv("HALO_IMPACT", "3"))
HALO_DEFAULT_URGENCY = int(os.getenv("HALO_URGENCY", "3"))
HALO_ACTIONTYPE_PUBLIC = int(os.getenv("HALO_ACTIONTYPE_PUBLIC", "78"))

HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))  # Bossers & Cnossen
HALO_SITE_ID = int(os.getenv("HALO_SITE_ID", "18"))              # Main site

ticket_room_map = {}

# ------------------------------------------------------------------------------
# Webex Webhook Auto-Management
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
    body = {
        "name": name,
        "targetUrl": TARGET_URL,
        "resource": resource,
        "event": event
    }
    r = requests.post("https://webexapis.com/v1/webhooks", headers=WEBEX_HEADERS, json=body)
    if r.status_code == 200:
        log.info(f"✅ Webhook '{name}' ({resource}/{event}) aangemaakt")
    else:
        log.error(f"❌ Kon webhook '{name}' niet maken: {r.status_code} {r.text}")

def ensure_webhook(name, resource, event):
    existing_hooks = get_webhooks()
    matching = [
        h for h in existing_hooks
        if h["resource"] == resource
        and h["event"] == event
        and h["targetUrl"] == TARGET_URL
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
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "Content-Type": "application/json"
    }

def fetch_all_client_users(client_id: int):
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50
    while True:
        url = f"{HALO_API_BASE}/Users?$filter=ClientID eq {client_id}&pageSize={page_size}&pageNumber={page}"
        r = requests.get(url, headers=h, timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
        users = data.get("users", [])
        if not users:
            break
        all_users.extend(users)
        if len(users) < page_size:
            break
        page += 1
    return all_users

def get_main_users(force=False):
    now = time.time()
    if not force and USER_CACHE["users"] and now - USER_CACHE["timestamp"] < CACHE_TTL:
        return USER_CACHE["users"]

    all_users = fetch_all_client_users(HALO_CLIENT_ID_NUM)
    main_users = [u for u in all_users if str(u.get("site_id")) == str(HALO_SITE_ID)
                                        or str(u.get("site_name", "")).lower() == "main"]
    USER_CACHE["users"] = main_users
    USER_CACHE["timestamp"] = now
    log.info(f"✅ Cache vernieuwd: {len(main_users)} Bossers & Cnossen/Main users")
    return main_users

def get_halo_user_id(email: str):
    if not email:
        return None
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
    log.info("🔄 Preloading Halo user cache...")
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
        "markdown": "✍ Vul het formulier in:",
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
# Routes (tickets etc. zoals jij al had gemaakt) 
# ------------------------------------------------------------------------------
# ... <laat je bestaande create_halo_ticket, add_note_to_ticket, webex_webhook, halo_webhook etc. hier staan> ...

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}

# ------------------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Zorg dat alles automatisch goed komt :)
    ensure_all_webhooks()   # ✅ check/maken Webex-webhooks
    preload_user_cache()    # ✅ preload Halo users
    log.info("🚀 Ticketbot volledig gestart – Webhooks + Cache actief!")
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
