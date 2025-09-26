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

# **✅ CORRECTE UAT ENDPOINTS (GEEN /v1 VOOR UAT)**
HALO_AUTH_URL = "https://bncuat.halopsa.com/auth/token"  
HALO_API_BASE = "https://bncuat.halopsa.com/api" # GEEN /v1 VOOR UAT  
log.info(f"✅ Halo API endpoints ingesteld: {HALO_AUTH_URL} en {HALO_API_BASE}")

# **Webex token validatie**
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")  
if not WEBEX_TOKEN:  
    log.critical("❌ FOUT: WEBEX_BOT_TOKEN niet ingesteld in .env!")  
else:  
    log.info(f"✅ Webex token gevonden (lengte: {len(WEBEX_TOKEN)} tekens)")  
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"}

# **Halo credentials validatie - AGENT CREDENTIALS REQUIRED**
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()  
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()  
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:  
    log.critical("❌ FOUT: Halo credentials niet ingesteld in .env!")  
else:  
    log.info(f"✅ Halo AGENT credentials gevonden (Client ID: {HALO_CLIENT_ID})")

# **Halo ticket instellingen**
HALO_TICKET_TYPE_ID = 65  
HALO_TEAM_ID = 1  
HALO_DEFAULT_IMPACT = 3  
HALO_DEFAULT_URGENCY = 3  
HALO_ACTIONTYPE_PUBLIC = 78  

# **Klant en locatie ID's - ALTIJD DEZELFDE VOOR DEZE USE CASE**
HALO_CLIENT_ID_NUM = 986 # Bossers & Cnossen  
HALO_SITE_ID = 992 # Main site  
log.info(f"✅ Gebruikt klant ID: {HALO_CLIENT_ID_NUM} (Bossers & Cnossen)")  
log.info(f"✅ Gebruikt locatie ID: {HALO_SITE_ID} (Main site)")

# **Globale cache variabele**
CONTACT_CACHE = {"contacts": [], "timestamp": 0}  
CACHE_DURATION = 24 * 60 * 60 # 24 uur  
log.info("✅ Cache systeem geïnitialiseerd (24-uurs cache)")

# **Globale ticket kamer mapping**
ticket_room_map = {}  
log.info("✅ Ticket kamer mapping systeem geïnitialiseerd")

# **------------------------------------------------------------------------------**
# **Contact Cache (VEREENVLODIGD VOOR ALLEEN BOSSERS & CNOSSEN)**
# **------------------------------------------------------------------------------**
def get_halo_headers():  
    """Haal Halo API headers met token - USES AGENT CREDENTIALS"""  
    log.debug("🔑 Aanvragen Halo API token...")  
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
        log.info("✅ Halo API token succesvol verkregen (AGENT TOKEN)")  
        return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}  
    except Exception as e:  
        log.critical(f"❌ AUTH MISLUKT: {str(e)}")  
        if 'r' in locals():  
            log.critical(f"➡️ Response: {r.text}")  
        raise  

def fetch_all_site_contacts():  
    """Ophalen ALLE klantcontacten voor Bossers & Cnossen (geen dynamische parameters)"""  
    log.info(f"🔍 Start ophalen klantcontacten voor Bossers & Cnossen (Client ID: {HALO_CLIENT_ID_NUM}, Site ID: {HALO_SITE_ID})")  
    h = get_halo_headers()  
    all_contacts = []  
    page = 1  
    processed_ids = set() # VOORKOMT DUBBELE CONTACTEN
    
    # Probeer /Users endpoint
    endpoint = "/Users"
    while page <= 20:  # Max 20 pagina's
        log.info(f"📄 Ophalen pagina {page} (klantcontacten)...")
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
                            
                            # Log alle e-mailadressen van het contact
                            email_fields = [
                                contact.get("EmailAddress", ""),
                                contact.get("emailaddress", ""),
                                contact.get("PrimaryEmail", ""),
                                contact.get("username", "")
                            ]
                            emails = [e for e in email_fields if e]
                            
                            log.info(
                                f"👤 Uniek klantcontact gevonden - "
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
    
    log.info(f"👥 SUCCES: {len(all_contacts)} klantcontacten opgehaald voor Bossers & Cnossen")
    return all_contacts

def get_main_contacts():  
    """24-UURS CACHE VOOR KLANTCONTACTEN"""  
    current_time = time.time()  
    
    # Gebruik cache als het nog geldig is
    if CONTACT_CACHE["contacts"] and (current_time - CONTACT_CACHE["timestamp"] < CACHE_DURATION):  
        log.info(f"✅ Cache gebruikt (vernieuwd {int((current_time - CONTACT_CACHE['timestamp'])/60)} minuten geleden)")  
        return CONTACT_CACHE["contacts"]  
    
    log.warning("🔄 Cache verlopen, vernieuwen Bossers & Cnossen klantcontacten…")  
    log.info("⏳ Start ophalen van alle klantcontacten...")  
    start_time = time.time()  
    contacts = fetch_all_site_contacts()
    duration = time.time() - start_time  
    
    if not contacts:
        log.critical("❌ GEEN KLANTCONTACTEN GEVONDEN - Controleer Halo configuratie!")
    
    log.info(f"⏱️ Klantcontacten opgehaald in {duration:.2f} seconden")  
    CONTACT_CACHE["contacts"] = contacts  
    CONTACT_CACHE["timestamp"] = time.time()  
    log.info(f"✅ {len(contacts)} KLANTCONTACTEN GECACHED")  
    return CONTACT_CACHE["contacts"]  

def get_halo_contact_id(email: str):  
    """ZOEK KLANTCONTACT OP EMAIL MET CASE-INSENSITIVE MATCHING"""  
    if not email:  
        return None  
    
    email = email.strip().lower()  
    log.debug(f"🔍 Zoeken naar klantcontact met email: {email}")  
    
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
                log.info(f"✅ Email match gevonden: {email} → Klantcontact ID={c.get('id')}")  
                return c.get("id")  
    
    log.warning(f"⚠️ Geen klantcontact gevonden voor email: {email}")  
    return None  
log.info("✅ Klantcontact cache functies geregistreerd")

# **------------------------------------------------------------------------------**
# **Halo Tickets (VEREENVLODIGD VOOR JOUW USE CASE)**
# **------------------------------------------------------------------------------**
def create_halo_ticket(summary, name, email, omschrijving, sindswanneer,  
                      watwerktniet, zelfgeprobeerd, impacttoelichting,  
                      impact_id, urgency_id, room_id=None):  
    log.info(f"🎫 Ticket aanmaken: '{summary}' voor {email} (AGENT GEBRUIKT)")  
    h = get_halo_headers()  
    
    # Haal contact ID op
    contact_id = get_halo_contact_id(email)
    if not contact_id:
        log.critical(f"❌ FATALE FOUT: Geen klantcontact gevonden voor {email}")
        if room_id:  
            send_message(room_id, "⚠️ Geen klantcontact gevonden in Halo. Controleer e-mailadres.")  
        return None
    
    # Ticket payload met vaste waarden
    body = {  
        "Summary": str(summary),  
        "Details": str(omschrijving),  
        "TypeID": int(HALO_TICKET_TYPE_ID),  
        "ClientID": int(HALO_CLIENT_ID_NUM),  
        "SiteID": int(HALO_SITE_ID),  
        "TeamID": int(HALO_TEAM_ID),  
        "ImpactID": int(impact_id),  
        "UrgencyID": int(urgency_id),
        "ContactId": int(contact_id),  # JUISTE VELD VOOR KLANTCONTACTEN
        "RequesterEmail": str(email)
    }  
    
    log.debug(f"➡️ Volledige ticket payload: {body}")  
    try:  
        request_body = [body]  
        r = requests.post(  
            f"{HALO_API_BASE}/Tickets",  
            headers=h,  
            json=request_body,  
            timeout=15  
        )  
        
        log.info(f"⬅️ API response status: {r.status_code}")  
        log.debug(f"⬅️ Volledige API response: {r.text}")  
        
        if r.status_code not in (200, 201):  
            log.error(f"❌ Basis ticket aanmaken mislukt: {r.status_code}")  
            log.error(f"➡️ Response body: {r.text}")  
            
            error_msg = "Onbekende fout"
            try:
                error_msg = r.json().get('message', r.text[:100])
            except:
                pass
                
            if room_id:  
                send_message(room_id, f"⚠️ Ticket aanmaken mislukt: {error_msg}")  
            return None  
        
        # Verwerk response
        try:  
            response_data = r.json()  
            if isinstance(response_data, list) and response_data:  
                ticket = response_data[0]
                ticket_id = ticket.get("ID") or ticket.get("id")
                
                if ticket_id:  
                    log.info(f"✅ Ticket succesvol aangemaakt met ID: {ticket_id}")  
                else:  
                    log.error("❌ Ticket ID niet gevonden in antwoord")  
                    return None  
            else:  
                log.error("❌ Ongeldig antwoord van Halo API")  
                return None  
            
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
                log.info(f"✅ Public note succesvol toegevoegd aan ticket {ticket_id}")  
                return {"ID": ticket_id, "Ref": f"BC-{ticket_id}", "contact_id": contact_id}  
            else:  
                log.warning(f"⚠️ Public note kon niet worden toegevoegd aan ticket {ticket_id}")  
                return {"ID": ticket_id, "contact_id": contact_id}  
        except Exception as e:  
            log.exception("❌ Fout bij verwerken API response")  
            return None  
    except Exception as e:  
        log.exception(f"❌ Fout bij ticket aanmaken: {str(e)}")  
        if room_id:  
            send_message(room_id, "⚠️ Technische fout bij ticket aanmaken")  
        return None  
log.info("✅ Ticket aanmaak functie geregistreerd")

# **------------------------------------------------------------------------------**
# **Notes (GEEN WIJZIGINGEN NODIG)**
# **------------------------------------------------------------------------------**
def add_note_to_ticket(ticket_id, public_output, sender, email=None, room_id=None, contact_id=None):  
    log.info(f"📎 Note toevoegen aan ticket {ticket_id}")  
    h = get_halo_headers()  
    
    if not contact_id:
        log.error("❌ Geen contact ID beschikbaar voor notitie")
        if room_id:
            send_message(room_id, "⚠️ Technische fout bij notitie toevoegen")
        return False
    
    body = {  
        "Details": str(public_output),  
        "ActionTypeID": int(HALO_ACTIONTYPE_PUBLIC),  
        "IsPrivate": False,  
        "TimeSpent": "00:00:00",
        "UserId": int(contact_id)  # Dit moet UserId blijven voor notities
    }  
    
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

# **------------------------------------------------------------------------------**
# **Webex helpers**
# **------------------------------------------------------------------------------**
def send_message(room_id, text):  
    try:  
        response = requests.post(  
            "https://webexapis.com/v1/messages",  
            headers=WEBEX_HEADERS,  
            json={"roomId": room_id, "markdown": text},  
            timeout=10  
        )  
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
    except Exception as e:  
        log.error(f"❌ Fout bij Adaptive Card: {str(e)}")  
log.info("✅ Webex helper functies geregistreerd")

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
                f"https://webexapis.com/v1/attachment/actions/{act_id}",  
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
        },  
        "endpoints": [  
            "/webex (POST) - Webex webhook",  
            "/ (GET) - Health check",  
            "/initialize (GET) - Cache verversen",  
            "/cache (GET) - Cache inspectie"  
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
    log.info(f"⏱️ Cache geinitialiseerd in {duration:.2f} seconden")  
    
    # Validatie
    if not CONTACT_CACHE["contacts"]:
        log.critical("❌ GEEN KLANTCONTACTEN GEVONDEN - Controleer Halo configuratie!")
    
    return {  
        "status": "initialized",  
        "contact_cache_size": len(CONTACT_CACHE["contacts"]),  
        "duration_seconds": duration,  
        "cache_timestamp": CONTACT_CACHE["timestamp"],  
        "client_id": HALO_CLIENT_ID_NUM,  
        "site_id": HALO_SITE_ID,  
        "message": "Cache geinitialiseerd voor Bossers & Cnossen klantcontacten"  
    }  

@app.route("/cache", methods=["GET"])  
def inspect_cache():  
    """Endpoint om de cache te inspecteren"""  
    log.info("🔍 Cache inspectie aangevraagd")  
    
    # Maak schone versie van de cache
    clean_cache = []  
    for contact in CONTACT_CACHE["contacts"]:  
        clean_contact = {  
            "id": contact.get("id", "N/A"),  
            "name": contact.get("name", "N/A"),  
            "emails": []  
        }  
        
        # Verzamel alle emailvelden  
        email_fields = [  
            contact.get("EmailAddress", ""),  
            contact.get("emailaddress", ""),  
            contact.get("PrimaryEmail", ""),  
            contact.get("username", "")  
        ]  
        
        # Voeg alleen niet-lege emails toe  
        for email in email_fields:  
            if email and email.lower() not in [e.lower() for e in clean_contact["emails"]]:  
                clean_contact["emails"].append(email)  
                
        clean_cache.append(clean_contact)  
    
    log.info(f"📊 Cache inspectie: {len(clean_cache)} contacten gevonden")  
    return jsonify({  
        "status": "success",  
        "cache_size": len(clean_cache),  
        "cache_timestamp": CONTACT_CACHE["timestamp"],  
        "contacts": clean_cache,  
        "message": f"Cache bevat {len(clean_cache)} klantcontacten voor Bossers & Cnossen"  
    })  
log.info("✅ Webex event handler geregistreerd")

# **------------------------------------------------------------------------------**
# **INITIELE CACHE LOADING BIJ OPSTARTEN**
# **------------------------------------------------------------------------------**
if __name__ == "__main__":  
    port = int(os.getenv("PORT", 5000))  
    log.info("="*70)  
    log.info("🚀 BOSSERS & CNOSSEN WEBEX TICKET BOT - UAT OMGEVING")  
    log.info("-"*70)  
    log.info(f"✅ Gebruikt klant ID: {HALO_CLIENT_ID_NUM} (Bossers & Cnossen B.V.)")  
    log.info(f"✅ Gebruikt locatie ID: {HALO_SITE_ID} (Main)")  
    log.info("✅ CACHE WORDT DIRECT BIJ OPSTARTEN GEVULD")  
    log.info("✅ ALLE GEBRUIKERS ZIJN VAN DEZELFDE KLANT/LOCATIE")  
    log.info("✅ AGENT CREDENTIALS GEBRUIKT VOOR API TOEGANG")  
    log.info("✅ CONTACTID GEBRUIKT VOOR KLANTKOPPELING")  
    log.info("✅ ALLE ID'S WORDEN ALS INTEGER VERZONDEN")  
    log.info("✅ NIEUW /cache ENDPOINT VOOR CACHE INSPECTIE")  
    log.info("✅ FIX VOOR 'PLEASE SELECT A VALID CLIENT/SITE/USER' FOUT")  
    log.info("✅ FIX VOOR ADAPTIVE CARD VERSIE (1.0 IN PLAATS VAN 1.2)")  
    log.info("-"*70)  
    
    # INITIELE CACHE LOADING BIJ OPSTARTEN  
    log.warning("⏳ Initialiseren klantcontactcache bij opstarten...")  
    start_time = time.time()  
    try:  
        get_main_contacts()  
        init_time = time.time() - start_time  
        log.info(f"✅ Klantcontactcache geïnitialiseerd in {init_time:.2f} seconden")  
        log.info(f"📊 Cache bevat nu {len(CONTACT_CACHE['contacts'])} klantcontacten")  
        
        if not CONTACT_CACHE['contacts']:  
            log.critical("❗️ WAARSCHUWING: Lege cache - Controleer Halo configuratie!")  
    except Exception as e:  
        log.exception(f"❌ Fout bij initialiseren cache: {str(e)}")  
    
    log.info("-"*70)  
    log.info("👉 VOLG DEZE STAPPEN:")  
    log.info("1. Deploy deze code naar Render")  
    log.info("2. Bezoek direct na deploy: /initialize")  
    log.info("3. Controleer de logs op:")  
    log.info(" - '✅ Uniek klantcontact gevonden - ID: 1086...'")  
    log.info(" - '✅ 5 KLANTCONTACTEN GECACHED'")  
    log.info("4. Bezoek /cache endpoint om de gecachte contacten te inspecteren")  
    log.info(" Voorbeeld: https://uw-app-naam.onrender.com/cache")  
    log.info("5. Typ in Webex: 'nieuwe melding' om het formulier te openen")  
    log.info("6. Vul het formulier in en verstuur")  
    log.info("7. Controleer logs op succesmeldingen:")  
    log.info(" - '✅ Ticket succesvol aangemaakt met ID: 12345'")  
    log.info(" - '✅ Public note succesvol toegevoegd aan ticket 12345'")  
    log.info("="*70)  
    app.run(host="0.0.0.0", port=port, debug=False)
