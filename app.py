import os, urllib.parse, logging, sys, time, threading  
from flask import Flask, request, jsonify  
from dotenv import load_dotenv  
import requests

# **------------------------------------------------------------------------------**
# **FORCEER LOGGING NAAR STDOUT (GEEN BUFFERING)**
# **------------------------------------------------------------------------------**
sys.stdout.reconfigure(line_buffering=True)  
logging.basicConfig(  
level=logging.INFO,  
format="%(asctime)s [%(levelname)s] %(message)s",  
handlers=[logging.StreamHandler(sys.stdout)]  
)  
log = logging.getLogger("ticketbot")  
log.info("✅ Logging systeem geïnitialiseerd - INFO niveau actief")  
log.info("💡 TIP: Bezoek /initialize na deploy om cache te vullen")

# **------------------------------------------------------------------------------**
# **Config**
# **------------------------------------------------------------------------------**
load_dotenv()  
app = Flask(__name__)  
log.info("✅ Flask applicatie geïnitialiseerd")

# **✅ CORRECTE UAT ENDPOINTS**
HALO_AUTH_URL = "https://bncuat.halopsa.com/auth/token"  
HALO_API_BASE = "https://bncuat.halopsa.com/api"  
log.info(f"✅ Halo API endpoints ingesteld: {HALO_AUTH_URL} en {HALO_API_BASE}")

# **Webex token validatie**
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")  
if not WEBEX_TOKEN:  
    log.critical("❌ FOUT: WEBEX_BOT_TOKEN niet ingesteld in .env!")  
else:  
    log.info(f"✅ Webex token gevonden (lengte: {len(WEBEX_TOKEN)} tekens)")  
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"}

# **Halo credentials**
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()  
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()  
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:  
    log.critical("❌ FOUT: Halo credentials niet ingesteld in .env!")  
else:  
    log.info(f"✅ Halo AGENT credentials gevonden (Client ID: {HALO_CLIENT_ID})")

# **Vaste waarden voor jouw specifieke use case**
HALO_TICKET_TYPE_ID = 65  
HALO_TEAM_ID = 1  
HALO_DEFAULT_IMPACT = 3  
HALO_DEFAULT_URGENCY = 3  
HALO_ACTIONTYPE_PUBLIC = 78  
HALO_CLIENT_ID_NUM = 986  # Bossers & Cnossen  
HALO_SITE_ID = 992        # Main site  

log.info(f"✅ Gebruikt klant ID: {HALO_CLIENT_ID_NUM} (Bossers & Cnossen)")  
log.info(f"✅ Gebruikt locatie ID: {HALO_SITE_ID} (Main site)")

# **Globale cache variabele**
CONTACT_CACHE = {"contacts": [], "timestamp": 0}  
CACHE_DURATION = 24 * 60 * 60 # 24 uur  
log.info("✅ Cache systeem geïnitialiseerd (24-uurs cache)")

# **Globale ticket kamer mapping**
ticket_room_map = {}  

# **------------------------------------------------------------------------------**
# **Contact Cache (BEHOUDE DE WERKENDE CACHE)**
# **------------------------------------------------------------------------------**
def get_halo_headers():  
    """Haal Halo API headers met token"""  
    try:  
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
        return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}  
    except Exception as e:  
        log.critical(f"❌ AUTH MISLUKT: {str(e)}")  
        raise  

def fetch_all_site_contacts():  
    """Ophalen klantcontacten voor Bossers & Cnossen"""  
    h = get_halo_headers()  
    all_contacts = []  
    page = 1  
    processed_ids = set()  
    
    # Probeer /Users endpoint
    endpoint = "/Users"
    while page <= 20:
        params = {
            "include": "site,client",
            "client_id": HALO_CLIENT_ID_NUM,
            "site_id": HALO_SITE_ID,
            "type": "contact",
            "page": page,
            "page_size": 50
        }
        
        try:
            r = requests.get(
                f"{HALO_API_BASE}{endpoint}",
                headers=h,
                params=params,
                timeout=15
            )
            
            if r.status_code == 200:
                try:
                    data = r.json()
                    contacts = data.get('users', []) or data.get('items', []) or data
                    
                    if not contacts:
                        break
                        
                    for contact in contacts:
                        contact_id = str(contact.get('id', ''))
                        if contact_id and contact_id not in processed_ids:
                            processed_ids.add(contact_id)
                            all_contacts.append(contact)
                            
                            # Log alle e-mailadressen
                            email_fields = [
                                contact.get("EmailAddress", ""),
                                contact.get("emailaddress", ""),
                                contact.get("PrimaryEmail", ""),
                                contact.get("username", "")
                            ]
                            emails = [e for e in email_fields if e]
                            
                            log.info(
                                f"👤 Klantcontact gevonden - "
                                f"ID: {contact_id}, "
                                f"Naam: {contact.get('name', 'N/A')}, "
                                f"Emails: {', '.join(emails)}"
                            )
                    
                    if len(contacts) < 50:
                        break
                        
                    page += 1
                except Exception as e:
                    log.exception(f"❌ Fout bij verwerken API response: {str(e)}")
                    break
            else:
                # Probeer /Person endpoint als /Users faalt
                if page == 1 and r.status_code == 404:
                    log.warning("⚠️ /Users endpoint niet gevonden, probeer /Person endpoint...")
                    endpoint = "/Person"
                    page = 1
                else:
                    log.error(f"❌ Fout bij ophalen pagina {page}: HTTP {r.status_code}")
                    break
        except Exception as e:
            log.exception(f"❌ Fout tijdens API-aanroep: {str(e)}")
            break
    
    return all_contacts

def get_main_contacts():  
    """24-UURS CACHE VOOR KLANTCONTACTEN"""  
    current_time = time.time()  
    
    # Gebruik cache als het nog geldig is
    if CONTACT_CACHE["contacts"] and (current_time - CONTACT_CACHE["timestamp"] < CACHE_DURATION):  
        return CONTACT_CACHE["contacts"]  
    
    log.warning("🔄 Cache verlopen, vernieuwen klantcontacten…")  
    contacts = fetch_all_site_contacts()
    
    CONTACT_CACHE["contacts"] = contacts  
    CONTACT_CACHE["timestamp"] = time.time()  
    
    if contacts:
        log.info(f"✅ {len(contacts)} KLANTCONTACTEN GECACHED")  
    else:
        log.critical("❌ GEEN KLANTCONTACTEN GEVONDEN - Controleer Halo configuratie!")
    
    return CONTACT_CACHE["contacts"]  

def get_halo_contact_id(email: str):  
    """ZOEK KLANTCONTACT OP EMAIL"""  
    if not email:  
        return None  
    
    email = email.strip().lower()  
    
    main_contacts = get_main_contacts()  
    for c in main_contacts:  
        # Alle mogelijke email velden controleren  
        email_fields = [  
            str(c.get("EmailAddress") or "").lower(),  
            str(c.get("emailaddress") or "").lower(),  
            str(c.get("PrimaryEmail") or "").lower(),  
            str(c.get("username") or "").lower()  
        ]  
        
        for field in email_fields:  
            if field and email in field:  
                return c.get("id")  
    
    return None

# **------------------------------------------------------------------------------**
# **Halo Tickets (DEFINITIEVE FIX VOOR JOUW USE CASE)**
# **------------------------------------------------------------------------------**
def create_halo_ticket(summary, name, email, omschrijving, sindswanneer,  
                      watwerktniet, zelfgeprobeerd, impacttoelichting,  
                      impact_id, urgency_id, room_id=None):  
    log.info(f"🎫 Ticket aanmaken: '{summary}' voor {email} (AGENT GEBRUIKT)")  
    h = get_halo_headers()  
    
    # Haal contact ID op
    contact_id = get_halo_contact_id(email)
    if not contact_id:
        log.error(f"❌ Geen klantcontact gevonden voor {email}")
        if room_id:  
            send_message(room_id, "⚠️ Geen klantcontact gevonden in Halo.")  
        return None
    
    # ✅ CRUCIALE FIX: CORRECTE VELDNAME VOLGENS HALO API
    body = {  
        "summary": str(summary),  
        "details": str(omschrijving),  
        "typeId": int(HALO_TICKET_TYPE_ID),  
        "clientId": int(HALO_CLIENT_ID_NUM),  # camelCase!
        "siteId": int(HALO_SITE_ID),         # camelCase!
        "teamId": int(HALO_TEAM_ID),  
        "impactId": int(impact_id),  
        "urgencyId": int(urgency_id),
        "requesterId": int(contact_id),     # camelCase!
        "requesterEmail": str(email)  
    }  
    
    try:  
        # Wrap ticket in array
        request_body = [body]  
        
        r = requests.post(  
            f"{HALO_API_BASE}/Tickets",  
            headers=h,  
            json=request_body,  
            timeout=15  
        )  
        
        if r.status_code not in (200, 201):  
            log.error(f"❌ Ticket aanmaken mislukt: {r.status_code} - {r.text[:100]}")  
            if room_id:  
                send_message(room_id, "⚠️ Ticket aanmaken mislukt")  
            return None  
        
        try:  
            response_data = r.json()  
            if isinstance(response_data, list) and response_data:  
                ticket = response_data[0]
                ticket_id = ticket.get("id") or ticket.get("ID")
                
                if ticket_id:  
                    # Public note toevoegen
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
                    
                    note_added = add_note_to_ticket(  
                        ticket_id,  
                        public_output=public_note,  
                        sender=name,  
                        email=email,  
                        room_id=room_id,
                        contact_id=contact_id
                    )  
                    
                    if note_added:  
                        return {"ID": ticket_id, "Ref": f"BC-{ticket_id}", "contact_id": contact_id}  
                    return {"ID": ticket_id, "contact_id": contact_id}
        except Exception as e:  
            log.exception("❌ Fout bij verwerken API response")  
            return None  
    except Exception as e:  
        log.exception(f"❌ Fout bij ticket aanmaken: {str(e)}")  
        if room_id:  
            send_message(room_id, "⚠️ Technische fout bij ticket aanmaken")  
        return None

# **------------------------------------------------------------------------------**
# **Notes (GEEN WIJZIGINGEN NODIG)**
# **------------------------------------------------------------------------------**
def add_note_to_ticket(ticket_id, public_output, sender, email=None, room_id=None, contact_id=None):  
    if not contact_id:
        return False
    
    h = get_halo_headers()
    
    body = {  
        "details": str(public_output),  
        "actionTypeId": int(HALO_ACTIONTYPE_PUBLIC),  
        "isPrivate": False,  
        "timeSpent": "00:00:00",
        "userId": int(contact_id)  # Dit moet UserId blijven voor notities
    }  
    
    try:  
        r = requests.post(  
            f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions",  
            headers=h,  
            json=body,  
            timeout=10  
        )  
        
        return r.status_code in (200, 201)  
    except Exception as e:  
        return False

# **------------------------------------------------------------------------------**
# **Webex helpers**
# **------------------------------------------------------------------------------**
def send_message(room_id, text):  
    try:  
        requests.post(  
            "https://webexapis.com/v1/messages",  
            headers=WEBEX_HEADERS,  
            json={"roomId": room_id, "markdown": text},  
            timeout=10  
        )  
    except:  
        pass  

def send_adaptive_card(room_id):  
    card = {  
        "roomId": room_id,  
        "markdown": "✍ Vul het formulier hieronder in:",  
        "attachments":[{  
            "contentType":"application/vnd.microsoft.card.adaptive",  
            "content":{  
                "$schema":"http://adaptivecards.io/schemas/adaptive-card.json",  
                "type":"AdaptiveCard",  
                "version":"1.0",  
                "body":[  
                    {"type":"TextBlock","text":"Naam","weight":"Bolder","wrap":True},  
                    {"type":"Input.Text","id":"name","placeholder":"Naam","isRequired":True,"wrap":True},  
                    {"type":"TextBlock","text":"E-mailadres","weight":"Bolder","wrap":True},  
                    {"type":"Input.Text","id":"email","placeholder":"E-mailadres","isRequired":True,"wrap":True},  
                    {"type":"TextBlock","text":"Probleemomschrijving","weight":"Bolder","wrap":True},  
                    {"type":"Input.Text","id":"omschrijving","placeholder":"Probleemomschrijving","isRequired":True,"isMultiline":True,"wrap":True},  
                    {"type":"TextBlock","text":"Sinds wanneer?","weight":"Bolder","wrap":True},  
                    {"type":"Input.Text","id":"sindswanneer","placeholder":"Sinds wanneer?","wrap":True},  
                    {"type":"TextBlock","text":"Wat werkt niet?","weight":"Bolder","wrap":True},  
                    {"type":"Input.Text","id":"watwerktniet","placeholder":"Wat werkt niet?","wrap":True},  
                    {"type":"TextBlock","text":"Zelf geprobeerd?","weight":"Bolder","wrap":True},  
                    {"type":"Input.Text","id":"zelfgeprobeerd","placeholder":"Zelf geprobeerd?","isMultiline":True,"wrap":True},  
                    {"type":"TextBlock","text":"Impact toelichting","weight":"Bolder","wrap":True},  
                    {"type":"Input.Text","id":"impacttoelichting","placeholder":"Impact toelichting","isMultiline":True,"wrap":True}  
                ],  
                "actions":[  
                    {  
                        "type":"Action.Submit",  
                        "title":"Versturen",  
                        "data": {}  
                    }  
                ]  
            }  
        }]  
    }  
    try:  
        requests.post(  
            "https://webexapis.com/v1/messages",  
            headers=WEBEX_HEADERS,  
            json=card,  
            timeout=10  
        )  
    except:  
        pass

# **------------------------------------------------------------------------------**
# **Webex Event Handler**
# **------------------------------------------------------------------------------**
def process_webex_event(data):  
    res = data.get("resource")  
    try:  
        if res == "messages":  
            msg_id = data["data"]["id"]  
            msg = requests.get(  
                f"https://webexapis.com/v1/messages/{msg_id}",  
                headers=WEBEX_HEADERS,  
                timeout=10  
            ).json()  
            text, room_id, sender = msg.get("text","").strip(), msg.get("roomId"), msg.get("personEmail")  
            if sender and sender.endswith("@webex.bot"):  
                return  
            if "nieuwe melding" in text.lower():  
                send_adaptive_card(room_id)  
                send_message(room_id,"📋 Vul formulier in om ticket te starten.")  
            else:  
                # Verwerk berichten in ticket kamers
                for t_id, room_info in ticket_room_map.items():
                    if isinstance(room_info, dict) and room_info.get("room_id") == room_id:
                        add_note_to_ticket(
                            t_id, 
                            text, 
                            sender, 
                            email=sender, 
                            room_id=room_id,
                            contact_id=room_info.get("contact_id")
                        )
                        break
        elif res == "attachmentActions":  
            act_id = data["data"]["id"]  
            inputs = requests.get(  
                f"https://webexapis.com/v1/attachment/actions/{act__id}",  
                headers=WEBEX_HEADERS,  
                timeout=10  
            ).json().get("inputs",{})  
            
            # Controleer verplichte velden  
            required_fields = ["name", "email", "omschrijving"]  
            missing = [field for field in required_fields if not inputs.get(field)]  
            if missing:  
                if "data" in data and "roomId" in data["data"]:
                    send_message(data["data"]["roomId"],  
                                f"⚠️ Verplichte velden ontbreken: {', '.join(missing)}")  
                return  
            
            # Standaardwaarden voor optionele velden  
            sindswanneer = inputs.get("sindswanneer", "Niet opgegeven")  
            watwerktniet = inputs.get("watwerktniet", "Niet opgegeven")  
            zelfgeprobeerd = inputs.get("zelfgeprobeerd", "Niet opgegeven")  
            impacttoelichting = inputs.get("impacttoelichting", "Niet opgegeven")  
            
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
                room_id=data["data"]["roomId"] if "data" in data and "roomId" in data["data"] else None
            )  
            
            if ticket:  
                ticket_id = ticket.get("ID")  
                if ticket_id and "data" in data and "roomId" in data["data"]:  
                    # Bewaar kamer en contact ID
                    ticket_room_map[ticket_id] = {
                        "room_id": data["data"]["roomId"],
                        "contact_id": ticket.get("contact_id")
                    }
                    ref = ticket.get('Ref', f"BC-{ticket_id}")  
                    send_message(data["data"]["roomId"],  
                                f"✅ Ticket aangemaakt: **{ref}**\n"  
                                f"🔢 Ticketnummer: {ticket_id}\n\n"  
                                f"Alle details zijn toegevoegd in een public note.")  
    except Exception as e:  
        log.exception(f"❌ Fout bij verwerken Webex event: {str(e)}")  

@app.route("/webex", methods=["POST"])  
def webex_webhook():  
    data = request.json  
    threading.Thread(target=process_webex_event, args=(data,)).start()  
    return {"status": "ok"}  

@app.route("/", methods=["GET"])  
def health():  
    return {  
        "status": "ok",  
        "message": "Bossers & Cnossen Webex Ticket Bot",  
        "environment": "UAT",  
        "cache_status": {  
            "contact_cache_size": len(CONTACT_CACHE["contacts"]),  
            "cache_age_minutes": int((time.time() - CONTACT_CACHE["timestamp"])/60) if CONTACT_CACHE["contacts"] else 0,  
        }  
    }  

@app.route("/initialize", methods=["GET"])  
def initialize_cache():  
    """Endpoint om de cache handmatig te initialiseren"""  
    get_main_contacts()  
    return {  
        "status": "initialized",  
        "contact_cache_size": len(CONTACT_CACHE["contacts"]),  
        "cache_timestamp": CONTACT_CACHE["timestamp"],  
        "client_id": HALO_CLIENT_ID_NUM,  
        "site_id": HALO_SITE_ID  
    }  

# **------------------------------------------------------------------------------**
# **INITIELE CACHE LOADING BIJ OPSTARTEN**
# **------------------------------------------------------------------------------**
if __name__ == "__main__":  
    port = int(os.getenv("PORT", 5000))  
    
    # INITIELE CACHE LOADING BIJ OPSTARTEN  
    try:  
        get_main_contacts()  
    except Exception as e:  
        log.exception(f"❌ Fout bij initialiseren cache: {str(e)}")  
    
    app.run(host="0.0.0.0", port=port, debug=False)
