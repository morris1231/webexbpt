import os, urllib.parse, logging, sys, time, threading
from flask import Flask, request
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json

# ------------------------------------------------------------------------------
# FORCEER LOGGING NAAR STDOUT (GEEN BUFFERING)
# ------------------------------------------------------------------------------
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("ticketbot")
log.info("✅ Logging systeem geïnitialiseerd - DEBUG niveau actief")
log.info("💡 TIP: Bezoek /initialize na deploy om cache te vullen")

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)
log.info("✅ Flask applicatie geïnitialiseerd")

# Webex token validatie
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
if not WEBEX_TOKEN:
    log.critical("❌ FOUT: WEBEX_BOT_TOKEN niet ingesteld in .env!")
else:
    log.info(f"✅ Webex token gevonden (lengte: {len(WEBEX_TOKEN)} tekens)")

WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"}

# Halo credentials validatie
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("❌ FOUT: Halo credentials niet ingesteld in .env!")
else:
    log.info(f"✅ Halo credentials gevonden (Client ID: {HALO_CLIENT_ID})")

# Halo API endpoints
HALO_AUTH_URL = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE = "https://bncuat.halopsa.com/api"  # Basis endpoint
log.info(f"✅ Halo API endpoints ingesteld: {HALO_AUTH_URL} en {HALO_API_BASE}")

# Halo ticket instellingen
HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", "65"))  # ✅ GEUPDATE NAAR 65
HALO_TEAM_ID = int(os.getenv("HALO_TEAM_ID", "1"))
HALO_DEFAULT_IMPACT = int(os.getenv("HALO_IMPACT", "3"))
HALO_DEFAULT_URGENCY = int(os.getenv("HALO_URGENCY", "3"))
HALO_ACTIONTYPE_PUBLIC = int(os.getenv("HALO_ACTIONTYPE_PUBLIC", "78"))
log.info(f"✅ Halo ticket instellingen: Type={HALO_TICKET_TYPE_ID}, Team={HALO_TEAM_ID}")

# Klant en locatie ID's
HALO_CLIENT_ID_NUM = 986  # Bossers & Cnossen
HALO_SITE_ID = 992        # Main site
log.info(f"✅ Gebruikt klant ID: {HALO_CLIENT_ID_NUM} (Bossers & Cnossen)")
log.info(f"✅ Gebruikt locatie ID: {HALO_SITE_ID} (Main site)")

# Globale cache variabele
USER_CACHE = {"users": [], "timestamp": 0}
CACHE_DURATION = 24 * 60 * 60  # 24 uur
log.info("✅ Cache systeem geïnitialiseerd (24-uurs cache)")

# Globale ticket kamer mapping
ticket_room_map = {}
log.info("✅ Ticket kamer mapping systeem geïnitialiseerd")

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
log.info("✅ ID normalisatie functie geregistreerd")

# ------------------------------------------------------------------------------
# User Cache (24-uurs cache met UAT-paginering)
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Haal Halo API headers met token"""
    log.debug("🔑 Aanvragen Halo API token...")
    try:
        payload = {
            "grant_type": "client_credentials",
            "client_id": HALO_CLIENT_ID,
            "client_secret": HALO_CLIENT_SECRET,
            "scope": "all"
        }
        log.debug(f"➡️ Authenticatie payload: {payload}")
        r = requests.post(
            HALO_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(payload),
            timeout=10
        )
        r.raise_for_status()
        log.info("✅ Halo API token succesvol verkregen")
        return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}
    except Exception as e:
        log.critical(f"❌ AUTH MISLUKT: {str(e)}")
        if 'r' in locals():
            log.critical(f"➡️ Response: {r.text}")
        raise

def fetch_all_site_users(client_id: int, site_id: int, max_pages=20):
    """GEAVANCEERDE OPHAALFUNCTIE MET ALLE MOGELIJKE ENDPOINTS"""
    log.info(f"🔍 Start ophalen gebruikers voor klant {client_id} en locatie {site_id} (UAT-modus)")
    
    # Probeer verschillende mogelijke API endpoints
    possible_endpoints = [
        "/Users",
        "/Person",
        "/People",
        "/Contact",
        "/Contacts"
    ]
    
    h = get_halo_headers()
    all_users = []
    
    for endpoint in possible_endpoints:
        log.info(f"🔄 Probeer endpoint: {endpoint}")
        page = 1
        page_size = 50
        users_found = False
        
        while page <= max_pages and not users_found:
            log.info(f"📄 Ophalen pagina {page} via {endpoint}...")
            params = {
                "include": "site,client",
                "client_id": client_id,
                "site_id": site_id,
                "page": page,
                "page_size": page_size
            }
            
            try:
                log.debug(f"➡️ API aanvraag met parameters: {params}")
                log.debug(f"➡️ API URL: {HALO_API_BASE}{endpoint}")
                
                r = requests.get(
                    f"{HALO_API_BASE}{endpoint}",
                    headers=h,
                    params=params,
                    timeout=15
                )
                
                log.debug(f"⬅️ Raw API response: {r.text}")
                
                if r.status_code == 200:
                    try:
                        data = r.json()
                        log.info(f"✅ Succesvol verbonden met endpoint: {endpoint}")
                        
                        # Probeer verschillende response structuren
                        users = []
                        if 'users' in data:
                            users = data['users']
                        elif 'person' in data:
                            users = data['person']
                        elif 'people' in data:
                            users = data['people']
                        elif 'contact' in data:
                            users = data['contact']
                        elif 'contacts' in data:
                            users = data['contacts']
                        elif isinstance(data, list):
                            users = data
                        else:
                            users = data
                        
                        if users:
                            log.info(f"📥 {len(users)} gebruikers gevonden op pagina {page} via {endpoint}")
                            
                            # Log details voor debugging
                            for user in users[:min(3, len(users))]:  # Log max 3 gebruikers voor overzicht
                                client_id_val = user.get('client_id', user.get('ClientID', 'N/A'))
                                site_id_val = user.get('site_id', user.get('SiteID', 'N/A'))
                                email_val = user.get('EmailAddress', user.get('emailaddress', 'N/A'))
                                log.info(f"👤 Gebruiker gevonden - ID: {user.get('id', 'N/A')}, Email: {email_val}, ClientID: {client_id_val}, SiteID: {site_id_val}")
                            
                            all_users.extend(users)
                            users_found = True
                            
                            # Stop na eerste succesvolle endpoint
                            break
                    except json.JSONDecodeError:
                        log.warning(f"⚠️ Geen JSON response van {endpoint}, mogelijk lege response")
                else:
                    log.debug(f"❌ Fout bij ophalen via {endpoint}: HTTP {r.status_code}")
                    log.debug(f"➡️ Response: {r.text}")
                    
            except Exception as e:
                log.exception(f"❌ Fout tijdens API-aanroep via {endpoint}: {str(e)}")
            
            page += 1
        
        if users_found:
            break
    
    if not all_users:
        log.error("❌ Geen gebruikers gevonden via alle mogelijke endpoints")
        log.error("❗️ PROBLEEMOPLOSSING:")
        log.error("1. Controleer of je klant en locatie ID's correct zijn:")
        log.error(f"   - Klant ID: {HALO_CLIENT_ID_NUM}")
        log.error(f"   - Locatie ID: {HALO_SITE_ID}")
        log.error("2. Ga naar je Halo UAT omgeving en controleer:")
        log.error("   a. Of de klant 'Bossers & Cnossen' bestaat met ID 986")
        log.error("   b. Of de locatie 'Main site' bestaat met ID 992")
        log.error("   c. Of de gebruiker is gekoppeld aan deze klant en locatie")
        log.error("3. Test de API endpoint handmatig met Postman:")
        log.error(f"   - URL: {HALO_API_BASE}/Users?client_id={HALO_CLIENT_ID_NUM}&site_id={HALO_SITE_ID}")
        log.error("   - Authorization: Bearer <access_token>")
        log.error("   - Response moet gebruikers retourneren")
        log.error("4. Als dit niet werkt, vraag dan aan je Halo beheerder:")
        log.error("   - Welke endpoint moet worden gebruikt voor klantcontacten")
        log.error("   - Of de gebruikers correct zijn gekoppeld aan klant en locatie")
    
    log.info(f"👥 SUCCES: {len(all_users)} gebruikers opgehaald voor klant {client_id} en locatie {site_id}")
    return all_users

def get_main_users():
    """24-UURS CACHE MET UAT-SPECIFIEKE VALIDATIE + INITIELE LOADING"""
    current_time = time.time()
    # Controleer of cache geldig is
    if USER_CACHE["users"] and (current_time - USER_CACHE["timestamp"] < CACHE_DURATION):
        log.info(f"✅ Cache gebruikt (vernieuwd {int((current_time - USER_CACHE['timestamp'])/60)} minuten geleden)")
        return USER_CACHE["users"]
        
    log.warning("🔄 Cache verlopen, vernieuwen Bossers & Cnossen Main users…")
    # Haal ALLE gebruikers op
    log.info("⏳ Start ophalen van alle gebruikers...")
    start_time = time.time()
    users = fetch_all_site_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    duration = time.time() - start_time
    log.info(f"⏱️  Gebruikers opgehaald in {duration:.2f} seconden")
    
    # Geen validatie nodig - de API filtert al op client_id en site_id
    USER_CACHE["users"] = users
    USER_CACHE["timestamp"] = time.time()
    
    log.info(f"✅ {len(users)} GEBRUIKERS GECACHED (van API-responses)")
    return USER_CACHE["users"]

def get_halo_user_id(email: str):
    """GEAVANCEERDE EMAIL MATCHING MET DEBUGGING"""
    if not email:
        return None
    email = email.strip().lower()
    log.debug(f"🔍 Zoeken naar gebruiker met email: {email}")
    main_users = get_main_users()
    
    for u in main_users:
        # Verbeterde email matching met meerdere mogelijke veldnamen
        email_fields = [
            str(u.get("EmailAddress") or u.get("emailaddress") or "").lower(),
            str(u.get("PrimaryEmail") or u.get("primaryemail") or "").lower(),
            str(u.get("username") or u.get("Username") or "").lower(),
            str(u.get("LoginName") or u.get("loginname") or "").lower(),
            str(u.get("networklogin") or u.get("NetworkLogin") or "").lower(),
            str(u.get("adobject") or u.get("ADObject") or "").lower()
        ]
        
        # Log alle email velden voor debugging
        log.debug(f"📧 Email velden voor gebruiker {u.get('id', 'N/A')}: {email_fields}")
        
        if email in [e for e in email_fields if e]:
            log.info(f"✅ Email match gevonden: {email} → Gebruiker ID={u.get('id')}")
            return u.get("id")
    
    log.warning(f"⚠️ Geen gebruiker gevonden voor email: {email}")
    
    # Geavanceerde debug informatie
    log.warning("❗️ PROBLEEMOPLOSSING:")
    log.warning("1. Controleer of de gebruiker bestaat in Halo:")
    log.warning(f"   - Email: {email}")
    log.warning(f"   - Klant ID: {HALO_CLIENT_ID_NUM}")
    log.warning(f"   - Locatie ID: {HALO_SITE_ID}")
    log.warning("2. Ga naar je Halo UAT omgeving en controleer:")
    log.warning("   a. Of de gebruiker bestaat met dit e-mailadres")
    log.warning("   b. Of de gebruiker is gekoppeld aan klant en locatie")
    log.warning("3. Test de API endpoint handmatig met Postman:")
    log.warning(f"   - URL: {HALO_API_BASE}/Users?client_id={HALO_CLIENT_ID_NUM}&site_id={HALO_SITE_ID}")
    log.warning("   - Authorization: Bearer <access_token>")
    log.warning("   - Zoek in de response naar het e-mailadres")
    
    return None
log.info("✅ Gebruikers cache functies geregistreerd")

# ------------------------------------------------------------------------------
# Halo Tickets (ULTRA-ROBUSTE AANMAAK MET ALLE MOGELIJKE COMBINATIES)
# ------------------------------------------------------------------------------
def create_halo_ticket(summary, name, email, omschrijving, sindswanneer,
                       watwerktniet, zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    log.info(f"🎫 Ticket aanmaken: '{summary}' voor {email}")
    h = get_halo_headers()
    contact_id = get_halo_user_id(email)
    
    # ✅ STAP 1: BASIS TICKET AANMAKEN MET ALLE MOGELIJKE COMBINATIES
    base_body = {
        "Summary": str(summary),
        "Details": str(omschrijving),
        "TypeID": int(HALO_TICKET_TYPE_ID),
        "ClientID": int(HALO_CLIENT_ID_NUM),
        "SiteID": int(HALO_SITE_ID),
        "TeamID": int(HALO_TEAM_ID),
        "ImpactID": int(impact_id),
        "UrgencyID": int(urgency_id)
    }
    
    # Mogelijke veldnamen voor gebruikerskoppeling
    user_field_options = [
        "UserID",
        "ContactID",
        "PersonID",
        "RequesterID"
    ]
    
    # Mogelijke payload types
    payload_types = [
        "single_object",  # Enkele object
        "array",           # Array met 1 object
        "wrapped"          # Speciale wrapper
    ]
    
    successful_creation = False
    ticket = None
    
    # Probeer alle combinaties
    for user_field in user_field_options:
        for payload_type in payload_types:
            # Maak de body afhankelijk van het payload type
            if payload_type == "single_object":
                body = base_body.copy()
                if contact_id:
                    body[user_field] = int(contact_id)
                request_body = body
                log.debug(f"🔄 Probeer met {user_field} als veldnaam (single object)")
            elif payload_type == "array":
                body = base_body.copy()
                if contact_id:
                    body[user_field] = int(contact_id)
                request_body = [body]
                log.debug(f"🔄 Probeer met {user_field} als veldnaam (array)")
            else:  # wrapped
                body = base_body.copy()
                if contact_id:
                    body[user_field] = int(contact_id)
                request_body = {"ticket": body}
                log.debug(f"🔄 Probeer met {user_field} als veldnaam (wrapped)")
            
            try:
                log.debug(f"➡️ Probeer Halo API aanroep met body: {json.dumps(request_body, indent=2)}")
                
                r = requests.post(
                    f"{HALO_API_BASE}/Tickets",
                    headers=h,
                    json=request_body,
                    timeout=15
                )
                
                log.debug(f"⬅️ Raw API response: {r.text}")
                
                if r.status_code in (200, 201):
                    log.info(f"✅ Ticket succesvol aangemaakt met {user_field} als veldnaam ({payload_type} payload)")
                    
                    # Verwerk de response
                    if payload_type == "array":
                        response_data = r.json()
                        if isinstance(response_data, list) and len(response_data) > 0:
                            ticket = response_data[0]
                        else:
                            ticket = r.json()
                    else:
                        ticket = r.json()
                    
                    successful_creation = True
                    break
                else:
                    log.warning(f"❌ Mislukt met {user_field} als veldnaam ({payload_type} payload): HTTP {r.status_code}")
                    # Probeer de volgende combinatie
                    
            except Exception as e:
                log.exception(f"❌ Fout bij ticket aanmaken met {user_field} ({payload_type}): {str(e)}")
            
            if successful_creation:
                break
        
        if successful_creation:
            break
    
    if not successful_creation:
        log.error("❌ Alle pogingen om een ticket aan te maken zijn mislukt")
        log.error("❗️ GEAVANCEERDE PROBLEEMOPLOSSING:")
        log.error("1. De meest waarschijnlijke oorzaak:")
        log.error("   - De gebruiker is niet correct gekoppeld aan de klant en locatie in Halo")
        log.error("   - OF de verkeerde veldnaam wordt gebruikt voor de koppeling")
        
        log.error("2. Stappen om dit op te lossen:")
        log.error("   a. Ga naar de gebruiker in Halo (met ID van de gebruiker)")
        log.error("   b. Controleer of deze gekoppeld is aan:")
        log.error(f"      - Klant: Bossers & Cnossen (ID {HALO_CLIENT_ID_NUM})")
        log.error(f"      - Locatie: Main site (ID {HALO_SITE_ID})")
        log.error("   c. Zo niet, koppel de gebruiker dan handmatig aan deze klant en locatie")
        
        log.error("3. Als dat niet werkt, test dan de API handmatig:")
        log.error("   a. Haal een access token op via:")
        log.error(f"      POST {HALO_AUTH_URL}")
        log.error("      Body: grant_type=client_credentials&client_id=YOUR_ID&client_secret=YOUR_SECRET")
        log.error("   b. Test de ticket aanmaak via Postman:")
        log.error(f"      POST {HALO_API_BASE}/Tickets")
        log.error("      Headers: Authorization: Bearer YOUR_TOKEN, Content-Type: application/json")
        log.error("      Body:")
        log.error("      {")
        log.error('        "Summary": "Test",')
        log.error('        "Details": "Test",')
        log.error(f'        "TypeID": {HALO_TICKET_TYPE_ID},')
        log.error(f'        "ClientID": {HALO_CLIENT_ID_NUM},')
        log.error(f'        "SiteID": {HALO_SITE_ID},')
        log.error(f'        "TeamID": {HALO_TEAM_ID},')
        log.error(f'        "ImpactID": {impact_id},')
        log.error(f'        "UrgencyID": {urgency_id},')
        log.error(f'        "UserID": {contact_id if contact_id else "MISSING"}')
        log.error("      }")
        log.error("   c. Probeer verschillende veldnamen in plaats van 'UserID':")
        log.error("      - ContactID")
        log.error("      - PersonID")
        log.error("      - RequesterID")
        
        log.error("4. Belangrijke informatie voor je Halo beheerder:")
        log.error(f"   - Klant ID: {HALO_CLIENT_ID_NUM}")
        log.error(f"   - Locatie ID: {HALO_SITE_ID}")
        log.error(f"   - Gebruiker ID: {contact_id if contact_id else 'Niet gevonden'}")
        log.error("   - Foutmelding: 'Please select a valid Client/Site/User'")
        log.error("   - Vraag specifiek welke veldnaam moet worden gebruikt voor de koppeling")
        
        if room_id:
            send_message(room_id, 
                "❌ Ticket aanmaken mislukt\n\n"
                "❗️ PROBLEEMOPLOSSING:\n"
                "1. De gebruiker is mogelijk niet correct gekoppeld aan de klant en locatie in Halo\n"
                "2. Probeer de volgende stappen:\n"
                f"   - Ga naar de gebruiker in Halo (ID: {contact_id if contact_id else 'Niet gevonden'})\n"
                f"   - Controleer of gekoppeld aan Klant ID {HALO_CLIENT_ID_NUM} en Locatie ID {HALO_SITE_ID}\n"
                "   - Als dit niet het geval is, koppel dan handmatig\n\n"
                "💡 Tip: Bezoek /initialize na correctie om cache te verversen"
            )
        return None
    
    # Haal ticket ID op
    ticket_id = ticket.get("ID") or ticket.get("id")
    if not ticket_id:
        log.error("❌ Ticket ID niet gevonden in antwoord")
        return None
    
    log.info(f"🎫 Ticket ID: {ticket_id}")
    
    # ✅ STAP 2: PUBLIC NOTE TOEVOEGEN MET ALLE INFORMATIE
    log.info(f"📝 Public note toevoegen aan ticket {ticket_id}...")
    
    # Maak de public note met alle informatie
    public_note = (
        f"**Naam:** {name}\n"
        f"**E-mail:** {email}\n"
        f"**Probleemomschrijving:** {omschrijving}\n\n"
        f"**Sinds wanneer:** {sindswanneer}\n"
        f"**Wat werkt niet:** {watwerktniet}\n"
        f"**Zelf geprobeerd:** {zelfgeprobeerd}\n"
        f"**Impact toelichting:** {impacttoelichting}\n\n"
        f"Ticket aangemaakt via Webex bot"
    )
    
    # Voeg de public note toe
    note_added = add_note_to_ticket(
        ticket_id,
        public_output=public_note,
        sender=name,
        email=email,
        room_id=room_id
    )
    
    if note_added:
        log.info(f"✅ Public note succesvol toegevoegd aan ticket {ticket_id}")
    else:
        log.warning(f"⚠️ Public note kon niet worden toegevoegd aan ticket {ticket_id}")
    
    return ticket
log.info("✅ Ticket aanmaak functie geregistreerd")

# ------------------------------------------------------------------------------
# Notes (GEFIXTE PUBLIC NOTES)
# ------------------------------------------------------------------------------
def add_note_to_ticket(ticket_id, public_output, sender, email=None, room_id=None):
    log.info(f"📎 Note toevoegen aan ticket {ticket_id}")
    h = get_halo_headers()
    body = {
        "Details": str(public_output),
        "ActionTypeID": int(HALO_ACTIONTYPE_PUBLIC),
        "IsPrivate": False,
        "TimeSpent": "00:00:00"
    }
    
    # Koppel de note aan de gebruiker als we een e-mail hebben
    if email:
        contact_id = get_halo_user_id(email)
        if contact_id:
            # Probeer verschillende mogelijke veldnamen
            possible_fields = ["UserID", "ContactID", "PersonID"]
            for field in possible_fields:
                try:
                    body[field] = int(contact_id)
                    log.info(f"📎 Note gekoppeld aan gebruiker ID: {contact_id} (via {field})")
                    break
                except:
                    continue
    
    try:
        r = requests.post(
            f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions",
            headers=h,
            json=body,
            timeout=10
        )
        
        log.debug(f"⬅️ Raw note API response: {r.text}")
        
        if r.status_code in (200, 201):
            log.info(f"✅ Note succesvol toegevoegd aan ticket {ticket_id}")
            return True
        log.error(f"❌ Note toevoegen mislukt ({r.status_code}): {r.text[:500]}")
        if room_id:
            send_message(room_id, f"⚠️ Note toevoegen mislukt ({r.status_code})")
        return False
    except Exception as e:
        log.exception(f"❌ Fout bij notitie toevoegen: {str(e)}")
        if room_id:
            send_message(room_id, "⚠️ Verbinding met Halo mislukt")
        return False
log.info("✅ Note toevoeg functie geregistreerd")

# ------------------------------------------------------------------------------
# Webex helpers
# ------------------------------------------------------------------------------
def send_message(room_id, text):
    log.debug(f"📤 Webex bericht versturen naar kamer {room_id}: {text[:50]}...")
    try:
        response = requests.post(
            "https://webexapis.com/v1/messages",
            headers=WEBEX_HEADERS,
            json={"roomId": room_id, "markdown": text},
            timeout=10
        )
        if response.status_code != 200:
            log.error(f"❌ Webex bericht versturen mislukt: {response.status_code} - {response.text}")
    except Exception as e:
        log.error(f"❌ Fout bij Webex bericht: {str(e)}")

def send_adaptive_card(room_id):
    log.info(f"🎨 Adaptive Card versturen naar kamer {room_id}")
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul het formulier hieronder in:",
        "attachments":[{
            "contentType":"application/vnd.microsoft.card.adaptive",
            "content":{
                "$schema":"http://adaptivecards.io/schemas/adaptive-card.json",
                "type":"AdaptiveCard","version":"1.2","body":[
                    {"type":"Input.Text","id":"name","placeholder":"Naam","isRequired":True},
                    {"type":"Input.Text","id":"email","placeholder":"E-mailadres","isRequired":True},
                    {"type":"Input.Text","id":"omschrijving","isMultiline":True,"placeholder":"Probleemomschrijving","isRequired":True},
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
        response = requests.post(
            "https://webexapis.com/v1/messages",
            headers=WEBEX_HEADERS,
            json=card,
            timeout=10
        )
        if response.status_code != 200:
            log.error(f"❌ Adaptive Card versturen mislukt: {response.status_code} - {response.text}")
    except Exception as e:
        log.error(f"❌ Fout bij Adaptive Card: {str(e)}")
log.info("✅ Webex helper functies geregistreerd")

# ------------------------------------------------------------------------------
# Webex Event Handler
# ------------------------------------------------------------------------------
def process_webex_event(data):
    res = data.get("resource")
    log.info(f"📩 Webex event ontvangen: {res}")
    try:
        if res == "messages":
            msg_id = data["data"]["id"]
            log.debug(f"🔍 Ophalen bericht details voor ID: {msg_id}")
            msg = requests.get(
                f"https://webexapis.com/v1/messages/{msg_id}",
                headers=WEBEX_HEADERS,
                timeout=10
            ).json()
            text, room_id, sender = msg.get("text","").strip(), msg.get("roomId"), msg.get("personEmail")
            log.debug(f"💬 Bericht inhoud: '{text[:50]}...' van {sender} in kamer {room_id}")
            
            if sender and sender.endswith("@webex.bot"):
                log.debug("🤖 Bericht is van een bot - negeren")
                return
                
            if "nieuwe melding" in text.lower():
                log.info("📝 'nieuwe melding' commando gedetecteerd")
                send_adaptive_card(room_id)
                send_message(room_id,"📋 Vul formulier in om ticket te starten.")
            else:
                log.info("💬 Webex bericht naar ticket kamer")
                for t_id, rid in ticket_room_map.items():
                    if rid == room_id:
                        log.info(f"💬 Webex bericht naar ticket {t_id}")
                        add_note_to_ticket(t_id, text, sender, email=sender, room_id=room_id)
                        
        elif res == "attachmentActions":
            act_id = data["data"]["id"]
            log.info(f"🔘 Formulier actie ontvangen met ID: {act_id}")
            inputs = requests.get(
                f"https://webexapis.com/v1/attachment/actions/{act_id}",
                headers=WEBEX_HEADERS,
                timeout=10
            ).json().get("inputs",{})
            log.info(f"➡️ Formulier inputs ontvangen: {inputs}")
            
            # Controleer verplichte velden
            required_fields = ["name", "email", "omschrijving"]
            missing = [field for field in required_fields if not inputs.get(field)]
            if missing:
                log.warning(f"❌ Verplichte velden ontbreken: {', '.join(missing)}")
                send_message(data["data"]["roomId"],
                            f"⚠️ Verplichte velden ontbreken: {', '.join(missing)}")
                return
                
            # Standaardwaarden voor optionele velden
            sindswanneer = inputs.get("sindswanneer", "Niet opgegeven")
            watwerktniet = inputs.get("watwerktniet", "Niet opgegeven")
            zelfgeprobeerd = inputs.get("zelfgeprobeerd", "Niet opgegeven")
            impacttoelichting = inputs.get("impacttoelichting", "Niet opgegeven")
            
            log.info(f"🚀 Ticket aanmaken voor {inputs['email']}")
            ticket = create_halo_ticket(
                inputs.get("omschrijving", "Melding via Webex"),
                inputs["name"], 
                inputs["email"], 
                inputs["omschrijving"],
                sindswanneer,
                watwerktniet,
                zelfgeprobeerd,
                impacttoelichting,
                inputs.get("impact", HALO_DEFAULT_IMPACT),
                inputs.get("urgency", HALO_DEFAULT_URGENCY),
                room_id=data["data"]["roomId"]
            )
            
            if ticket:
                ticket_id = ticket.get("ID") or ticket.get("id")
                ticket_room_map[ticket_id] = data["data"]["roomId"]
                ref = ticket.get('Ref', 'Onbekend')
                log.info(f"🎫 Ticket {ref} succesvol aangemaakt (ID: {ticket_id})")
                send_message(data["data"]["roomId"],
                            f"✅ Ticket aangemaakt: **{ref}**\n"
                            f"🔢 Ticketnummer: {ticket_id}\n\n"
                            f"Alle details zijn toegevoegd in een public note.")
            else:
                log.error("❌ Ticket kon niet worden aangemaakt")
                send_message(data["data"]["roomId"],
                           "⚠️ Ticket kon niet worden aangemaakt. Probeer opnieuw.")
    except Exception as e:
        log.exception(f"❌ Fout bij verwerken Webex event: {str(e)}")
        if "room_id" in locals():
            send_message(room_id, "⚠️ Er is een technische fout opgetreden")

@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    log.debug(f"📥 Webhook ontvangen: {data}")
    threading.Thread(target=process_webex_event, args=(data,)).start()
    return {"status": "ok"}

@app.route("/", methods=["GET"])
def health():
    log.info("🏥 Health check aangevraagd")
    return {
        "status": "ok",
        "message": "Bossers & Cnossen Webex Ticket Bot",
        "environment": "UAT",
        "cache_status": {
            "user_cache_size": len(USER_CACHE["users"]),
            "cache_age_minutes": int((time.time() - USER_CACHE["timestamp"])/60) if USER_CACHE["users"] else 0,
            "cache_expires_in_minutes": max(0, int((CACHE_DURATION - (time.time() - USER_CACHE["timestamp"]))/60)) if USER_CACHE["users"] else 0
        },
        "endpoints": [
            "/webex (POST) - Webex webhook",
            "/ (GET) - Health check",
            "/initialize (GET) - Cache verversen"
        ],
        "timestamp": time.time()
    }

@app.route("/initialize", methods=["GET"])
def initialize_cache():
    """Endpoint om de cache handmatig te initialiseren"""
    log.warning("⚠️ Handmatige cache initialisatie aangevraagd")
    start_time = time.time()
    get_main_users()
    duration = time.time() - start_time
    log.info(f"⏱️  Cache geinitialiseerd in {duration:.2f} seconden")
    return {
        "status": "initialized",
        "user_cache_size": len(USER_CACHE["users"]),
        "duration_seconds": duration,
        "cache_timestamp": USER_CACHE["timestamp"]
    }
log.info("✅ Webex event handler geregistreerd")

# ------------------------------------------------------------------------------
# INITIELE CACHE LOADING BIJ OPSTARTEN
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 BOSSERS & CNOSSEN WEBEX TICKET BOT - UAT OMGEVING")
    log.info("-"*70)
    log.info(f"✅ Gebruikt klant ID: {HALO_CLIENT_ID_NUM} (Bossers & Cnossen B.V.)")
    log.info(f"✅ Gebruikt locatie ID: {HALO_SITE_ID} (Main)")
    log.info("✅ CACHE WORDT DIRECT BIJ OPSTARTEN GEVULD")
    log.info("✅ PROBEERT ALLE MOGELIJKE ENDPOINTS EN VELDNAMEN")
    log.info("✅ GEAVANCEERDE DEBUGGING INGEBOUWD")
    log.info("-"*70)
    
    # ✅ INITIELE CACHE LOADING BIJ OPSTARTEN
    log.warning("⏳ Initialiseren gebruikerscache bij opstarten...")
    start_time = time.time()
    try:
        get_main_users()
        init_time = time.time() - start_time
        log.info(f"✅ Gebruikerscache geïnitialiseerd in {init_time:.2f} seconden")
        log.info(f"📊 Cache bevat nu {len(USER_CACHE['users'])} gebruikers")
    except Exception as e:
        log.exception(f"❌ Fout bij initialiseren cache: {str(e)}")
    
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN:")
    log.info("1. Deploy deze code naar Render")
    log.info("2. Bezoek direct na deploy: /initialize (vul URL in browser)")
    log.info("   Voorbeeld: https://jouw-app-naam.onrender.com/initialize")
    log.info("3. Controleer de logs voor cache details")
    log.info("4. Typ in Webex: 'nieuwe melding' om het formulier te openen")
    log.info("5. Vul het formulier in en verstuur")
    log.info("6. ALS HET MISLUKT:")
    log.info("   a. Controleer of de gebruiker gekoppeld is aan klant en locatie in Halo")
    log.info("   b. Test de API handmatig met Postman (zie logs voor instructies)")
    log.info("   c. Vraag aan je Halo beheerder welke veldnaam moet worden gebruikt")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port, debug=False)
else:
    # Voor WSGI-servers (zoals op Render.com)
    log.warning("🌐 App wordt gestart via WSGI-server - cache wordt gevuld bij eerste aanvraag")
    log.warning("💡 Tip: Bezoek /initialize na deploy om de cache direct te vullen")
