import os, urllib.parse, logging, sys, time, threading
from flask import Flask, request
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ------------------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("ticketbot")

# ------------------------------------------------------------------------------
# Requests Session w/ Retry
# ------------------------------------------------------------------------------
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"}

HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL      = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE      = os.getenv("HALO_API_BASE", "").strip()

HALO_TICKET_TYPE_ID   = int(os.getenv("HALO_TICKET_TYPE_ID", "55"))
HALO_TEAM_ID          = int(os.getenv("HALO_TEAM_ID", "1"))
HALO_DEFAULT_IMPACT   = int(os.getenv("HALO_IMPACT", "3"))
HALO_DEFAULT_URGENCY  = int(os.getenv("HALO_URGENCY", "3"))
HALO_ACTIONTYPE_PUBLIC= int(os.getenv("HALO_ACTIONTYPE_PUBLIC", "78"))

HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12")) # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))      # Main site

ticket_room_map = {}

# ------------------------------------------------------------------------------
# User Cache (fetch all site users w/ paging)
# ------------------------------------------------------------------------------
USER_CACHE = {"users": [], "timestamp": 0}

def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    r = session.post(HALO_AUTH_URL,
                     headers={"Content-Type": "application/x-www-form-urlencoded"},
                     data=urllib.parse.urlencode(payload), timeout=10)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

def fetch_all_site_users(client_id: int, site_id: int, max_pages=20):
    """Fetch all users for Client+Site with paging until all Main users (~341)."""
    h = get_halo_headers()
    all_users, page, page_size = [], 1, 50
    while page <= max_pages:
        url = (f"{HALO_API_BASE}/Users?"
               f"$filter=ClientID eq {client_id} and SiteID eq {site_id}"
               f"&pageSize={page_size}&pageNumber={page}")
        r = session.get(url, headers=h, timeout=15)
        if r.status_code != 200:
            log.error(f"❌ Error fetching page {page}: {r.status_code}")
            break
        users = r.json().get("users", [])
        if not users: break
        all_users.extend(users)
        log.info(f"📄 Page {page}: {len(users)} users, totaal {len(all_users)}")
        if len(users) < page_size:
            break
        page += 1
    log.info(f"👥 In totaal {len(all_users)} users opgehaald (Client={client_id}, Site={site_id})")
    return all_users

def get_main_users():
    if not USER_CACHE["users"]:
        log.info("🔄 Cache leeg, ophalen Bossers & Cnossen Main users…")
        users = fetch_all_site_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
        USER_CACHE["users"] = users
        USER_CACHE["timestamp"] = time.time()
        log.info(f"✅ {len(users)} Main users gecached")
    return USER_CACHE["users"]

def get_halo_user_id(email: str):
    if not email: return None
    email = email.strip().lower()
    for u in get_main_users():
        check_vals = {
            str(u.get("EmailAddress") or "").lower(),
            str(u.get("emailaddress") or "").lower(),
            str(u.get("PrimaryEmail") or "").lower(),
            str(u.get("username") or "").lower(),
            str(u.get("LoginName") or "").lower(),
            str(u.get("networklogin") or "").lower(),
            str(u.get("adobject") or "").lower()
        }
        if email in check_vals:
            log.info(f"✅ Match {email} → UserID={u.get('id')}")
            return u.get("id")
    log.warning(f"⚠️ Geen match voor {email}")
    return None

# ------------------------------------------------------------------------------
# Halo Tickets
# ------------------------------------------------------------------------------
def create_halo_ticket(summary, name, email, omschrijving, sindswanneer,
                       watwerktniet, zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):

    h = get_halo_headers()
    requester_id = get_halo_user_id(email)

    body = {
        "Summary": str(summary),
        "Details": f"{omschrijving}\n\nSinds: {sindswanneer}\nWat werkt niet: {watwerktniet}\nZelf geprobeerd: {zelfgeprobeerd}\nImpact toelichting: {impacttoelichting}",
        "TypeID": HALO_TICKET_TYPE_ID,
        "ClientID": HALO_CLIENT_ID_NUM,
        "SiteID": HALO_SITE_ID,
        "TeamID": HALO_TEAM_ID,
        "ImpactID": int(impact_id),
        "UrgencyID": int(urgency_id)
    }
    if requester_id:
        body["UserID"] = int(requester_id)
    else:
        log.warning("⚠️ Ticket zonder UserID")

    r = session.post(f"{HALO_API_BASE}/Tickets", headers=h, json=body, timeout=15)
    log.info(f"➡️ Halo response {r.status_code}: {r.text}")
    if r.status_code in (200, 201): return r.json()
    if room_id: send_message(room_id, f"⚠️ Ticket aanmaken mislukt ({r.status_code})")
    return None

# ------------------------------------------------------------------------------
# Notes
# ------------------------------------------------------------------------------
def add_note_to_ticket(ticket_id, text, sender, email=None, room_id=None):
    h = get_halo_headers()
    body = {"Details": str(text), "ActionTypeID": HALO_ACTIONTYPE_PUBLIC, "IsPrivate": False}
    uid = get_halo_user_id(email) if email else None
    if uid: body["UserID"] = int(uid)
    r = session.post(f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions", headers=h, json=body, timeout=10)
    log.info(f"➡️ AddNote response {r.status_code}")
    if r.status_code not in (200,201) and room_id:
        send_message(room_id, f"⚠️ Note toevoegen mislukt ({r.status_code})")

# ------------------------------------------------------------------------------
# Webex helpers
# ------------------------------------------------------------------------------
def send_message(room_id, text):
    session.post("https://webexapis.com/v1/messages",
                 headers=WEBEX_HEADERS,
                 json={"roomId": room_id, "markdown": text}, timeout=10)

def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul het formulier hieronder in:",
        "attachments":[{
            "contentType":"application/vnd.microsoft.card.adaptive",
            "content":{
                "$schema":"http://adaptivecards.io/schemas/adaptive-card.json",
                "type":"AdaptiveCard","version":"1.2","body":[
                    {"type":"Input.Text","id":"name","placeholder":"Naam"},
                    {"type":"Input.Text","id":"email","placeholder":"E-mailadres"},
                    {"type":"Input.Text","id":"omschrijving","isMultiline":True,"placeholder":"Probleemomschrijving"},
                    {"type":"Input.Text","id":"sindswanneer","placeholder":"Sinds wanneer?"},
                    {"type":"Input.Text","id":"watwerktniet","placeholder":"Wat werkt niet?"},
                    {"type":"Input.Text","id":"zelfgeprobeerd","isMultiline":True,"placeholder":"Zelf geprobeerd?"},
                    {"type":"Input.Text","id":"impacttoelichting","isMultiline":True,"placeholder":"Impact toelichting"}
                ],
                "actions":[{"type":"Action.Submit","title":"Versturen"}]
            }
        }]
    }
    session.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=card, timeout=10)

# ------------------------------------------------------------------------------
# Webex Event Handler
# ------------------------------------------------------------------------------
def process_webex_event(data):
    res = data.get("resource")
    log.info(f"📩 Webex event: {res}")
    if res=="messages":
        msg_id = data["data"]["id"]
        msg = session.get(f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS, timeout=10).json()
        text, room_id, sender = msg.get("text","").strip(), msg.get("roomId"), msg.get("personEmail")
        if sender and sender.endswith("@webex.bot"): return
        if "nieuwe melding" in text.lower():
            send_adaptive_card(room_id)
            send_message(room_id,"📋 Vul formulier in om ticket te starten.")
        else:
            for t_id,rid in ticket_room_map.items():
                if rid==room_id:
                    add_note_to_ticket(t_id,text,sender,email=sender,room_id=room_id)

    elif res=="attachmentActions":
        act_id = data["data"]["id"]
        inputs = session.get(f"https://webexapis.com/v1/attachment/actions/{act_id}", headers=WEBEX_HEADERS, timeout=10).json().get("inputs",{})
        log.info(f"➡️ Inputs: {inputs}")
        naam,email = inputs.get("name","Onbekend"), inputs.get("email","")
        ticket = create_halo_ticket(
            inputs.get("omschrijving","Melding via Webex"),
            naam,email,inputs.get("omschrijving",""),inputs.get("sindswanneer",""),
            inputs.get("watwerktniet",""),inputs.get("zelfgeprobeerd",""),
            inputs.get("impacttoelichting",""),
            inputs.get("impact",HALO_DEFAULT_IMPACT), inputs.get("urgency",HALO_DEFAULT_URGENCY),
            room_id=data["data"]["roomId"]
        )
        if ticket:
            ticket_room_map[ticket.get("ID") or ticket.get("id")] = data["data"]["roomId"]
            send_message(data["data"]["roomId"], f"✅ Ticket aangemaakt: **{ticket.get('Ref')}**")
        else:
            send_message(data["data"]["roomId"], "⚠️ Ticket kon niet aangemaakt worden.")

@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    threading.Thread(target=process_webex_event,args=(data,)).start()
    return {"status":"ok"}

@app.route("/", methods=["GET"])
def health():
    return {"status":"ok","message":"Bot draait!"}

if __name__=="__main__":
    port=int(os.getenv("PORT",5000))
    app.run(host="0.0.0.0",port=port,debug=False)
