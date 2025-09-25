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

# Webex token validatie
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"}

# Halo credentials
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE = "https://bncuat.halopsa.com/api"

# Halo ticket instellingen
HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", "55"))
HALO_TEAM_ID = int(os.getenv("HALO_TEAM_ID", "1"))
HALO_DEFAULT_IMPACT = int(os.getenv("HALO_IMPACT", "3"))
HALO_DEFAULT_URGENCY = int(os.getenv("HALO_URGENCY", "3"))
HALO_ACTIONTYPE_PUBLIC = int(os.getenv("HALO_ACTIONTYPE_PUBLIC", "78"))

# Klant en locatie ID's
HALO_CLIENT_ID_NUM = 986  # Bossers & Cnossen
HALO_SITE_ID = 992        # Main site

# Globale cache variabele
USER_CACHE = {"users": [], "timestamp": 0}
CACHE_DURATION = 24 * 60 * 60  # 24 uur

# ------------------------------------------------------------------------------
# ID Normalisatie Helper
# ------------------------------------------------------------------------------
def normalize_id(value):
    """Converteer willekeurige ID-waarden naar integers (UAT-proof)"""
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError, AttributeError):
        return None

# ------------------------------------------------------------------------------
# User Cache (24-uurs cache met UAT-paginering)
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Haal Halo API headers met token"""
    try:
        payload = {
            "grant_type": "client_credentials",
            "client_id": HALO_CLIENT_ID,
            "client_secret": HALO_CLIENT_SECRET,
            "scope": "all"
        }
        r = session.post(
            HALO_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(payload),
            timeout=10
        )
        r.raise_for_status()
        return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}
    except Exception as e:
        log.critical(f"❌ AUTH MISLUKT: {str(e)}")
        if 'r' in locals():
            log.critical(f"➡️ Response: {r.text}")
        raise

def fetch_all_site_users(client_id: int, site_id: int, max_pages=20):
    """Ophalen gebruikers voor klant en locatie"""
    h = get_halo_headers()
    all_users = []
    page = 1
    page_size = 50
    
    while page <= max_pages:
        params = {
            "include": "site,client",
            "client_id": client_id,
            "site_id": site_id,
            "page": page,
            "page_size": page_size
        }
        
        try:
            r = session.get(
                f"{HALO_API_BASE}/Users",
                headers=h,
                params=params,
                timeout=15
            )
            
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
            
        except Exception as e:
            break
    
    return all_users

def get_main_users():
    """24-UURS CACHE MET UAT-SPECIFIEKE VALIDATIE"""
    current_time = time.time()
    
    # Controleer of cache geldig is
    if USER_CACHE["users"] and (current_time - USER_CACHE["timestamp"] < CACHE_DURATION):
        return USER_CACHE["users"]
    
    # Haal ALLE gebruikers op
    users = fetch_all_site_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    
    # Filter op juiste klant en locatie
    valid_users = []
    client_id_norm = normalize_id(HALO_CLIENT_ID_NUM)
    site_id_norm = normalize_id(HALO_SITE_ID)
    
    for user in users:
        user_client_id = normalize_id(user.get("client_id"))
        user_site_id = normalize_id(user.get("site_id"))
        
        if user_client_id == client_id_norm and user_site_id == site_id_norm:
            valid_users.append(user)
    
    USER_CACHE["users"] = valid_users
    USER_CACHE["timestamp"] = time.time()
    
    return USER_CACHE["users"]

def get_halo_user_id(email: str):
    """Email matching met UAT-compatibiliteit"""
    if not email: 
        return None
    
    email = email.strip().lower()
    main_users = get_main_users()
    
    for u in main_users:
        email_fields = [
            str(u.get("EmailAddress") or "").lower(),
            str(u.get("emailaddress") or "").lower(),
            str(u.get("PrimaryEmail") or "").lower(),
            str(u.get("username") or "").lower(),
            str(u.get("LoginName") or "").lower(),
            str(u.get("networklogin") or "").lower(),
            str(u.get("adobject") or "").lower()
        ]
        
        if email in [e for e in email_fields if e]:
            return u.get("id")
    
    return None

# ------------------------------------------------------------------------------
# Halo Tickets (EXACT WAT JE VRAAGT)
# ------------------------------------------------------------------------------
def create_halo_ticket(summary, name, email, omschrijving, sindswanneer,
                       watwerktniet, zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    h = get_halo_headers()
    requester_id = get_halo_user_id(email)
    
    # ✅ PROBLEEMOMSCHRIJVING ALLEEN IN DETAILS (GEEN PUBLIC NOTE)
    body = {
        "Summary": str(summary),
        "Details": str(omschrijving),  # ✅ ALLEEN HIER
        "TypeID": int(HALO_TICKET_TYPE_ID),
        "ClientID": int(HALO_CLIENT_ID_NUM),
        "SiteID": int(HALO_SITE_ID),
        "TeamID": int(HALO_TEAM_ID),
        "ImpactID": int(impact_id),
        "UrgencyID": int(urgency_id)
    }
    
    # Gebruiker koppelen
    if requester_id:
        body["UserID"] = int(requester_id)
    
    try:
        r = session.post(f"{HALO_API_BASE}/Tickets", headers=h, json=body, timeout=15)
        
        if r.status_code not in (200, 201):
            if room_id:
                send_message(room_id, f"⚠️ Ticket aanmaken mislukt ({r.status_code})")
            return None
        
        ticket = r.json()
        ticket_id = ticket.get("ID") or ticket.get("id")
        
        # ✅ REST VAN DE VRAGEN IN EEN PUBLIC NOTE (GEEN PROBLEEMOMSCHRIJVING)
        public_note = (
            f"**Naam:** {name}\n"
            f"**E-mail:** {email}\n"
            f"**Sinds wanneer:** {sindswanneer}\n"
            f"**Wat werkt niet:** {watwerktniet}\n"
            f"**Zelf geprobeerd:** {zelfgeprobeerd}\n"
            f"**Impact toelichting:** {impacttoelichting}"
        )
        
        add_note_to_ticket(
            ticket_id,
            public_note,
            "Webex Bot",
            email=email,
            room_id=room_id
        )
        
        return ticket
        
    except Exception as e:
        if room_id: 
            send_message(room_id, "⚠️ Verbinding met Halo mislukt")
        return None

# ------------------------------------------------------------------------------
# Notes
# ------------------------------------------------------------------------------
def add_note_to_ticket(ticket_id, text, sender, email=None, room_id=None):
    h = get_halo_headers()
    
    body = {
        "Details": str(text),
        "ActionTypeID": int(HALO_ACTIONTYPE_PUBLIC),
        "IsPrivate": False,
        "TimeSpent": "00:00:00"
    }
    
    if email:
        requester_id = get_halo_user_id(email)
        if requester_id:
            body["UserID"] = int(requester_id)
    
    try:
        r = session.post(
            f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions", 
            headers=h, 
            json=body, 
            timeout=10
        )
        
        return r.status_code in (200, 201)
        
    except Exception as e:
        return False

# ------------------------------------------------------------------------------
# Webex helpers
# ------------------------------------------------------------------------------
def send_message(room_id, text):
    try:
        session.post("https://webexapis.com/v1/messages",
                     headers=WEBEX_HEADERS,
                     json={"roomId": room_id, "markdown": text}, timeout=10)
    except Exception as e:
        pass

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
    try:
        session.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=card, timeout=10)
    except Exception as e:
        pass

# ------------------------------------------------------------------------------
# Webex Event Handler
# ------------------------------------------------------------------------------
def process_webex_event(data):
    res = data.get("resource")
    
    try:
        if res == "messages":
            msg_id = data["data"]["id"]
            msg = session.get(f"https://webexapis.com/v1/messages/{msg_id}", 
                             headers=WEBEX_HEADERS, timeout=10).json()
            text, room_id, sender = msg.get("text","").strip(), msg.get("roomId"), msg.get("personEmail")
            
            if sender and sender.endswith("@webex.bot"): 
                return
                
            if "nieuwe melding" in text.lower():
                send_adaptive_card(room_id)
                send_message(room_id,"📋 Vul formulier in om ticket te starten.")
            else:
                for t_id, rid in ticket_room_map.items():
                    if rid == room_id:
                        add_note_to_ticket(t_id, text, sender, email=sender, room_id=room_id)
                        
        elif res == "attachmentActions":
            act_id = data["data"]["id"]
            inputs = session.get(f"https://webexapis.com/v1/attachment/actions/{act_id}", 
                                headers=WEBEX_HEADERS, timeout=10).json().get("inputs",{})
            
            required_fields = ["name", "email", "omschrijving"]
            missing = [field for field in required_fields if not inputs.get(field)]
            
            if missing:
                send_message(data["data"]["roomId"], 
                            f"⚠️ Verplichte velden ontbreken: {', '.join(missing)}")
                return
                
            ticket = create_halo_ticket(
                inputs.get("omschrijving","Melding via Webex"),
                inputs["name"], inputs["email"], inputs["omschrijving"],
                inputs.get("sindswanneer","Niet opgegeven"),
                inputs.get("watwerktniet","Niet opgegeven"),
                inputs.get("zelfgeprobeerd","Niet opgegeven"),
                inputs.get("impacttoelichting","Niet opgegeven"),
                inputs.get("impact", HALO_DEFAULT_IMPACT), 
                inputs.get("urgency", HALO_DEFAULT_URGENCY),
                room_id=data["data"]["roomId"]
            )
            
            if ticket:
                ticket_id = ticket.get("ID") or ticket.get("id")
                ticket_room_map[ticket_id] = data["data"]["roomId"]
                ref = ticket.get('Ref', 'Onbekend')
                send_message(data["data"]["roomId"], 
                            f"✅ Ticket aangemaakt: **{ref}**\n"
                            f"🔢 Ticketnummer: {ticket_id}")
            else:
                send_message(data["data"]["roomId"], 
                           "⚠️ Ticket kon niet worden aangemaakt. Probeer opnieuw.")
                           
    except Exception as e:
        if "room_id" in locals():
            send_message(room_id, "⚠️ Er is een technische fout opgetreden")

@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    threading.Thread(target=process_webex_event, args=(data,)).start()
    return {"status": "ok"}

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Ticket bot draait!"}

# ------------------------------------------------------------------------------
# INITIELE CACHE LOADING BIJ OPSTARTEN
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    # Cache initialiseren bij opstarten
    get_main_users()
    
    app.run(host="0.0.0.0", port=port, debug=False)
