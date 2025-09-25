import os, urllib.parse, logging, sys, time, threading
from flask import Flask, request
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
log.info("✅ Logging systeem geïnitialiseerd - INFO niveau actief")
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
HALO_API_BASE = "https://bncuat.halopsa.com/api"
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
CONTACT_CACHE = {"contacts": [], "timestamp": 0}
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
# Contact Cache (24-uurs cache met UAT-paginering)
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

def fetch_all_site_contacts(client_id: int, site_id: int, max_pages=20):
    """GEFIXTE UAT-COMPATIBELE OPHAALFUNCTIE MET PAGINERING - GEBRUIKT /Contacts"""
    log.info(f"🔍 Start ophalen contacten voor klant {client_id} en locatie {site_id} (UAT-modus)")
    h = get_halo_headers()
    all_contacts = []
    page = 1
    page_size = 50
    while page <= max_pages:
        log.info(f"📄 Ophalen pagina {page} ({page_size} contacten per pagina)...")
        params = {
            "include": "site,client",
            "client_id": client_id,
            "site_id": site_id,
            "page": page,
            "page_size": page_size
        }
        try:
            log.debug(f"➡️ API aanvraag met parameters: {params}")
            r = requests.get(
                f"{HALO_API_BASE}/Contacts",  # ✅ CRUCIALE WIJZIGING: /Contacts in plaats van /Users
                headers=h,
                params=params,
                timeout=15
            )
            if r.status_code != 200:
                log.error(f"❌ Fout bij ophalen pagina {page}: HTTP {r.status_code}")
                log.debug(f"➡️ Response: {r.text}")
                break
            data = r.json()
            log.debug(f"⬅️ API response ontvangen: {len(data.get('contacts', []))} contacten gevonden")
            contacts = data.get("contacts", [])
            if not contacts:
                log.info(f"✅ Geen contacten gevonden op pagina {page} - einde bereikt")
                break
            all_contacts.extend(contacts)
            log.info(f"📥 Pagina {page} opgehaald: {len(contacts)} contacten (Totaal: {len(all_contacts)})")
            if len(contacts) < page_size:
                log.info("✅ Minder contacten dan page_size - einde bereikt")
                break
            page += 1
        except Exception as e:
            log.exception(f"❌ Fout tijdens API-aanroep: {str(e)}")
            break
    log.info(f"👥 SUCCES: {len(all_contacts)} contacten opgehaald voor klant {client_id} en locatie {site_id}")
    return all_contacts

def get_main_contacts():
    """24-UURS CACHE MET UAT-SPECIFIEKE VALIDATIE + INITIELE LOADING"""
    current_time = time.time()
    # Controleer of cache geldig is
    if CONTACT_CACHE["contacts"] and (current_time - CONTACT_CACHE["timestamp"] < CACHE_DURATION):
        log.info(f"✅ Cache gebruikt (vernieuwd {int((current_time - CONTACT_CACHE['timestamp'])/60)} minuten geleden)")
        return CONTACT_CACHE["contacts"]
    log.warning("🔄 Cache verlopen, vernieuwen Bossers & Cnossen Main contacten…")
    # Haal ALLE contacten op
    log.info("⏳ Start ophalen van alle contacten...")
    start_time = time.time()
    contacts = fetch_all_site_contacts(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    duration = time.time() - start_time
    log.info(f"⏱️  Contacten opgehaald in {duration:.2f} seconden")
    # Filter op juiste klant en locatie
    valid_contacts = []
    client_id_norm = normalize_id(HALO_CLIENT_ID_NUM)
    site_id_norm = normalize_id(HALO_SITE_ID)
    for contact in contacts:
        contact_client_id = normalize_id(contact.get("client_id"))
        contact_site_id = normalize_id(contact.get("site_id"))
        if contact_client_id == client_id_norm and contact_site_id == site_id_norm:
            valid_contacts.append(contact)
    CONTACT_CACHE["contacts"] = valid_contacts
    CONTACT_CACHE["timestamp"] = time.time()
    log.info(f"✅ {len(valid_contacts)} GEVALIDEERDE Main contacten gecached (van {len(contacts)} API-responses)")
    return CONTACT_CACHE["contacts"]

def get_halo_contact_id(email: str):
    """GEFIXTE EMAIL MATCHING MET UAT-COMPATIBILITEIT - GEBRUIKT CONTACTEN"""
    if not email:
        return None
    email = email.strip().lower()
    log.debug(f"🔍 Zoeken naar contact met email: {email}")
    main_contacts = get_main_contacts()
    for c in main_contacts:
        email_fields = [
            str(c.get("EmailAddress") or "").lower(),
            str(c.get("emailaddress") or "").lower(),
            str(c.get("PrimaryEmail") or "").lower(),
            str(c.get("username") or "").lower(),
            str(c.get("LoginName") or "").lower(),
            str(c.get("networklogin") or "").lower(),
            str(c.get("adobject") or "").lower()
        ]
        if email in [e for e in email_fields if e]:
            log.info(f"✅ Email match gevonden: {email} → Contact ID={c.get('id')}")
            return c.get("id")
    log.warning(f"⚠️ Geen contact gevonden voor email: {email}")
    return None
log.info("✅ Contact cache functies geregistreerd")

# ------------------------------------------------------------------------------
# Halo Tickets (GEFIXT VOOR HALO API ARRAY VERWACHTING EN CONTACTEN)
# ------------------------------------------------------------------------------
def create_halo_ticket(summary, name, email, omschrijving, sindswanneer,
                       watwerktniet, zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    log.info(f"🎫 Ticket aanmaken: '{summary}' voor {email}")
    h = get_halo_headers()
    contact_id = get_halo_contact_id(email)
    
    # ✅ STAP 1: BASIS TICKET AANMAKEN (ALLEEN STANDAARD FIELDS)
    body = {
        "Summary": str(summary),
        "Details": str(omschrijving),
        "TypeID": int(HALO_TICKET_TYPE_ID),
        "ClientID": int(HALO_CLIENT_ID_NUM),
        "SiteID": int(HALO_SITE_ID),
        "TeamID": int(HALO_TEAM_ID),
        "ImpactID": int(impact_id),
        "UrgencyID": int(urgency_id)
    }
    
    # ✅ GEBRUIKER KOPPELEN MET CONTACTID (NIET USERID)
    if contact_id:
        body["ContactID"] = int(contact_id)
        log.info(f"👤 Ticket gekoppeld aan contact ID: {contact_id}")
    else:
        log.warning("⚠️ Geen contact gevonden in Halo voor het opgegeven e-mailadres")
    
    try:
        # ✅ CRUCIALE FIX: Wrap ticket in array voor Halo API
        request_body = [body]
        log.debug(f"➡️ Halo API aanroep voor basis ticket: {request_body}")
        r = requests.post(
            f"{HALO_API_BASE}/Tickets",
            headers=h,
            json=request_body,  # Nu een array in plaats van object
            timeout=15
        )
        
        if r.status_code not in (200, 201):
            log.error(f"❌ Basis ticket aanmaken mislukt: {r.status_code} - {r.text[:500]}")
            if room_id:
                send_message(room_id, f"⚠️ Basis ticket aanmaken mislukt ({r.status_code})")
            return None
            
        log.info("✅ Basis ticket succesvol aangemaakt")
        
        # ✅ FIX: Verwerk array response
        response_data = r.json()
        if isinstance(response_data, list) and len(response_data) > 0:
            ticket = response_data[0]  # Eerste ticket uit de array
            ticket_id = ticket.get("ID") or ticket.get("id")
            if ticket_id:
                log.info(f"🎫 Ticket ID: {ticket_id}")
            else:
                log.error("❌ Ticket ID niet gevonden in antwoord")
                return None
        else:
            log.error("❌ Ongeldig antwoord van Halo API - geen ticket ontvangen")
            return None
        
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
    except Exception as e:
        log.exception(f"❌ Fout bij ticket aanmaken: {str(e)}")
        if room_id:
            send_message(room_id, "⚠️ Verbinding met Halo mislukt")
        return None
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
    
    # Koppel de note aan het contact als we een e-mail hebben
    if email:
        contact_id = get_halo_contact_id(email)
        if contact_id:
            body["ContactID"] = int(contact_id)
            log.info(f"📎 Note gekoppeld aan contact ID: {contact_id}")
    
    try:
        r = requests.post(
            f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions",
            headers=h,
            json=body,
            timeout=10
        )
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
            "contact_cache_size": len(CONTACT_CACHE["contacts"]),
            "cache_age_minutes": int((time.time() - CONTACT_CACHE["timestamp"])/60) if CONTACT_CACHE["contacts"] else 0,
            "cache_expires_in_minutes": max(0, int((CACHE_DURATION - (time.time() - CONTACT_CACHE["timestamp"]))/60)) if CONTACT_CACHE["contacts"] else 0
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
    get_main_contacts()
    duration = time.time() - start_time
    log.info(f"⏱️  Cache geinitialiseerd in {duration:.2f} seconden")
    return {
        "status": "initialized",
        "contact_cache_size": len(CONTACT_CACHE["contacts"]),
        "duration_seconds": duration,
        "cache_timestamp": CONTACT_CACHE["timestamp"]
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
    log.info("✅ GEBRUIKT /Contacts ENDPOINT IN PLAATS VAN /Users")
    log.info("✅ CONTACTID IN PLAATS VAN USERID GEBRUIKT")
    log.info("✅ GEEN CUSTOM FIELDS - ALLES GAAT NAAR PUBLIC NOTE")
    log.info("-"*70)
    
    # ✅ INITIELE CACHE LOADING BIJ OPSTARTEN
    log.warning("⏳ Initialiseren contactcache bij opstarten...")
    start_time = time.time()
    try:
        get_main_contacts()
        init_time = time.time() - start_time
        log.info(f"✅ Contactcache geïnitialiseerd in {init_time:.2f} seconden")
        log.info(f"📊 Cache bevat nu {len(CONTACT_CACHE['contacts'])} contacten")
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
    log.info("6. Controleer logs voor alle stappen")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port, debug=False)
else:
    # Voor WSGI-servers (zoals op Render.com)
    log.warning("🌐 App wordt gestart via WSGI-server - cache wordt gevuld bij eerste aanvraag")
    log.warning("💡 Tip: Bezoek /initialize na deploy om de cache direct te vullen")
