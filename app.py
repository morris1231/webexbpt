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
HALO_AUTH_URL  = os.getenv("HALO_AUTH_URL")
HALO_API_BASE  = os.getenv("HALO_API_BASE")
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID")
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET")
HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", 66))
HALO_CLIENT_ID_NUM  = int(os.getenv("HALO_CLIENT_ID_NUM", 12))
HALO_SITE_ID        = int(os.getenv("HALO_SITE_ID", 18))
WEBEX_TOKEN         = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}",
                 "Content-Type": "application/json"} if WEBEX_TOKEN else {}
USER_CACHE = {"users": [], "timestamp": 0, "source": "none"}
TICKET_ROOM_MAP = {}   # roomId <-> ticketId
CACHE_DURATION = 24 * 60 * 60  # CORRECTED: 24 uur in seconden

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
    r = requests.post(HALO_AUTH_URL,
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data=urllib.parse.urlencode(payload),
                      timeout=10)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}

# --------------------------------------------------------------------------
# USERS (met volledige paginering)
# --------------------------------------------------------------------------
def fetch_users(client_id: int, site_id: int):
    h = get_halo_headers()
    all_users = []
    page = 1
    per_page = 100  # Max 100 per pagina (Halo standaard)
    
    while True:
        params = {
            "client_id": client_id,
            "site_id": site_id,
            "page": page,
            "per_page": per_page
        }
        r = requests.get(f"{HALO_API_BASE}/Users", headers=h, params=params, timeout=15)
        
        if r.status_code != 200:
            log.warning(f"⚠️ /Users pagina {page} gaf {r.status_code}: {r.text[:200]}")
            break
            
        users = r.json().get("users", []) or r.json().get("items", []) or r.json()
        if not users:
            break
            
        for u in users:
            # Filter actieve gebruikers met geldig emailadres
            if (
                u.get("use") == "user" and
                not u.get("inactive", True) and
                u.get("emailaddress") and
                "@" in u["emailaddress"]
            ):
                # Zet alle ID's om naar integers
                u["id"] = int(u.get("id", 0))
                u["client_id"] = int(u.get("client_id", 0))
                u["site_id"] = int(u.get("site_id", 0))
                all_users.append(u)
                
        # Stop als minder dan per_page gebruikers in de pagina zitten
        if len(users) < per_page:
            break
            
        page += 1
        
    USER_CACHE["source"] = "/Users (paginated)"
    log.info(f"✅ {len(all_users)} gebruikers opgehaald (client={client_id}, site={site_id})")
    return all_users

def get_users():
    now = time.time()
    if USER_CACHE["users"] and (now - USER_CACHE["timestamp"] < CACHE_DURATION):
        return USER_CACHE["users"]
    USER_CACHE["users"] = fetch_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    USER_CACHE["timestamp"] = now
    return USER_CACHE["users"]

def get_user(email: str):
    if not email:
        return None
    email = email.lower().strip()
    for u in get_users():
        for field in ["EmailAddress", "emailaddress", "PrimaryEmail", "login", "email", "email1"]:
            if u.get(field) and u[field].lower() == email:
                return u
    return None

# --------------------------------------------------------------------------
# WEBEX HELPERS
# --------------------------------------------------------------------------
def send_message(room_id: str, text: str):
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
        log.error(f"❌ Webex send: {e}")

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
# HALO TICKETS + NOTES
# --------------------------------------------------------------------------
def create_halo_ticket(form, room_id):
    h = get_halo_headers()
    user = get_user(form["email"])
    if not user:
        send_message(room_id, "❌ Geen gebruiker gevonden in Halo.")
        return
    user_id = int(user["id"])
    body = {
        "summary": form["omschrijving"][:100],
        "details": form["omschrijving"],
        "tickettype_id": HALO_TICKET_TYPE_ID,
        "impact": int(form.get("impact", "3")),
        "urgency": int(form.get("urgency", "3")),
        "client_id": int(user.get("client_id", HALO_CLIENT_ID_NUM)),
        "site_id": int(user.get("site_id", HALO_SITE_ID)),
        "user_id": user_id
    }
    r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[body], timeout=20)
    if not r.ok:
        send_message(room_id, f"⚠️ Ticket aanmaken mislukt: {r.status_code}")
        return
    tid = r.json()[0]["id"]
    TICKET_ROOM_MAP[room_id] = tid
    # Voeg formuliergegevens als eerste public note toe
    note = "\n".join([
        "**Nieuwe melding gegevens:**",
        f"**Email:** {form['email']}",
        f"**Omschrijving:** {form['omschrijving']}",
        f"**Sinds wanneer:** {form.get('sindswanneer', '-')}",
        f"**Wat werkt niet:** {form.get('watwerktniet', '-')}",
        f"**Zelf geprobeerd:** {form.get('zelfgeprobeerd', '-')}",
        f"**Impact toelichting:** {form.get('impacttoelichting', '-')}",
        f"**Impact:** {form.get('impact', '-')} | **Urgency:** {form.get('urgency', '-')}"
    ])
    add_public_note(tid, note)
    send_message(room_id, f"✅ Ticket aangemaakt: **{tid}**")
    return tid

def add_public_note(ticket_id, text):
    h = get_halo_headers()
    requests.post(
        f"{HALO_API_BASE}/Tickets/{ticket_id}/Notes",
        headers=h,
        json={"text": text, "is_public": True},
        timeout=15
    )

def check_new_halo_notes():
    """Polling voor Halo webhook: haalt nieuwe public notes op en stuurt ze naar Webex"""
    while True:
        try:
            h = get_halo_headers()
            for room_id, ticket_id in list(TICKET_ROOM_MAP.items()):
                r = requests.get(
                    f"{HALO_API_BASE}/Tickets/{ticket_id}/Notes",
                    headers=h,
                    timeout=15
                )
                if not r.ok:
                    continue
                notes = r.json()
                # Filter alleen public notes en vind de nieuwste ID
                public_notes = [n for n in notes if n.get("is_public")]
                if not public_notes:
                    continue
                latest_note_id = max(n["id"] for n in public_notes)
                
                # Determine last note ID from TICKET_ROOM_MAP
                last_data = TICKET_ROOM_MAP.get(room_id)
                last_note_id = last_data.get("last_note", 0) if isinstance(last_data, dict) else 0
                
                # Check if we have new notes
                if last_note_id < latest_note_id:
                    # Get all new public notes
                    new_notes = []
                    for n in public_notes:
                        if n["id"] > last_note_id:
                            new_notes.append(n)
                    
                    # Send new notes to Webex
                    for n in new_notes:
                        send_message(room_id, f"📢 **Public note in Halo:**\n{n['text']}")
                    
                    # Update last note ID for this room
                    TICKET_ROOM_MAP[room_id] = {
                        "ticket_id": ticket_id,
                        "last_note": latest_note_id
                    }
        except Exception as e:
            log.error(f"❌ Poll notes error: {e}")
        time.sleep(60)  # Check elke minuut

# --------------------------------------------------------------------------
# WEBEX EVENTS
# --------------------------------------------------------------------------
def process_webex_event(payload):
    res = payload.get("resource")
    if res == "messages":
        mid = payload["data"]["id"]
        msg = requests.get(
            f"https://webexapis.com/v1/messages/{mid}",
            headers=WEBEX_HEADERS
        ).json()
        text = msg.get("text", "")
        room_id = msg.get("roomId")
        sender = msg.get("personEmail", "")
        if sender and sender.endswith("@webex.bot"):
            return
        if "nieuwe melding" in text.lower():
            send_adaptive_card(room_id)
        elif room_id in TICKET_ROOM_MAP:
            # Stuur Webex-bericht als public note naar Halo
            add_public_note(TICKET_ROOM_MAP[room_id], f"💬 **Van gebruiker:** {text}")
            send_message(room_id, "📝 Bericht toegevoegd aan Halo als public note.")
    elif res == "attachmentActions":
        a_id = payload["data"]["id"]
        inputs = requests.get(
            f"https://webexapis.com/v1/attachment/actions/{a_id}",
            headers=WEBEX_HEADERS
        ).json().get("inputs", {})
        create_halo_ticket(inputs, payload["data"]["roomId"])

# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------
@app.route("/webex", methods=["POST"])
def webex_hook():
    threading.Thread(target=process_webex_event, args=(request.json,)).start()
    return {"status": "ok"}

@app.route("/halo", methods=["POST"])
def halo_hook():
    """Webhook vanuit Halo op nieuwe public note"""
    data = request.json or {}
    note = data.get("note") or data.get("text") or ""
    ticket_id = data.get("ticket_id") or data.get("TicketID")
    if not note or not ticket_id:
        return {"status": "ignore"}
    for room_id, t_id in TICKET_ROOM_MAP.items():
        if isinstance(t_id, dict):
            t_id = t_id.get("ticket_id")
        if t_id == ticket_id:
            send_message(room_id, f"📥 **Nieuwe public note vanuit Halo:**\n{note}")
    return {"status": "ok"}

@app.route("/", methods=["GET"])
def health():
    return {
        "status": "running",
        "tracked_rooms": len(TICKET_ROOM_MAP),
        "cached_users": len(USER_CACHE["users"]) if USER_CACHE["users"] else 0
    }

# --------------------------------------------------------------------------
# START
# --------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Start server op poort {port}")
    threading.Thread(target=check_new_halo_notes, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False)
