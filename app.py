import os, urllib.parse, logging, sys, time, threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import requests
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

# ✅ CORRECTE UAT ENDPOINTS (GEEN /v1 VOOR UAT)
HALO_AUTH_URL = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE = "https://bncuat.halopsa.com/api"  # GEEN /v1 VOOR UAT
log.info(f"✅ Halo API endpoints ingesteld: {HALO_AUTH_URL} en {HALO_API_BASE}")

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

# Halo ticket instellingen - ✅ ALLEEN STRINGS (GEEN INTEGERS)
HALO_TICKET_TYPE_ID = "65"
HALO_TEAM_ID = "1"
HALO_DEFAULT_IMPACT = "3"
HALO_DEFAULT_URGENCY = "3"
HALO_ACTIONTYPE_PUBLIC = "78"
log.info(f"✅ Halo ticket instellingen: Type={HALO_TICKET_TYPE_ID}, Team={HALO_TEAM_ID}")

# Klant en locatie ID's - ✅ ALLEEN STRINGS (CRUCIAAL VOOR UAT)
HALO_CLIENT_ID_NUM = "986"  # Bossers & Cnossen
HALO_SITE_ID = "992"        # Main site
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

def fetch_all_site_users(client_id: str, site_id: str, max_pages=20):
    """GEFIXTE OPHAALFUNCTIE VOOR KLANTGEBRUIKERS MET ONEINDIGE LUS FIX"""
    log.info(f"🔍 Start ophalen klantgebruikers voor klant {client_id} en locatie {site_id}")
    h = get_halo_headers()
    all_users = []
    page = 1
    processed_ids = set()  # ✅ VOORKOMT ONEINDIGE LUS
    
    # ✅ PROBEER EERST /Users ENDPOINT
    endpoint = "/Users"
    log.info(f"ℹ️ Probeer eerste endpoint: {HALO_API_BASE}{endpoint}")
    
    while page <= max_pages:
        log.info(f"📄 Ophalen pagina {page} (klantgebruikers)...")
        params = {
            "include": "site,client",
            "client_id": client_id,
            "site_id": site_id,
            "type": "contact",
            "page": page,
            "page_size": 50
        }
        
        try:
            log.debug(f"➡️ API aanvraag met parameters: {params}")
            r = requests.get(
                f"{HALO_API_BASE}{endpoint}",
                headers=h,
                params=params,
                timeout=15
            )
            
            if r.status_code == 200:
                log.info(f"✅ Succesvol verbonden met {endpoint} endpoint")
                try:
                    data = r.json()
                    # ✅ VERWERK VERSCHILLENDE RESPONSE STRUCTUREN
                    users = data.get('users', []) or data.get('items', []) or data
                    
                    if not users:
                        log.info(f"✅ Geen klantgebruikers gevonden op pagina {page}")
                        break
                    
                    new_users = []
                    for user in users:
                        # ✅ VOORKOMT DUBBELE GEBRUIKERS
                        user_id = str(user.get('id', ''))
                        if user_id and user_id not in processed_ids:
                            processed_ids.add(user_id)
                            new_users.append(user)
                            
                            # ✅ UITGEBREIDE LOGGING VOOR DEBUGGING
                            email_fields = [
                                user.get("EmailAddress", ""),
                                user.get("emailaddress", ""),
                                user.get("PrimaryEmail", ""),
                                user.get("username", "")
                            ]
                            log.info(
                                f"👤 Unieke klantgebruiker gevonden - "
                                f"ID: {user_id}, "
                                f"Naam: {user.get('name', 'N/A')}, "
                                f"Emails: {', '.join([e for e in email_fields if e])}"
                            )
                    
                    if not new_users:
                        log.warning("⚠️ Geen nieuwe gebruikers gevonden - mogelijke oneindige lus")
                        break
                        
                    all_users.extend(new_users)
                    log.info(f"📥 Pagina {page} opgehaald: {len(new_users)} nieuwe klantgebruikers (Totaal: {len(all_users)})")
                    
                    if len(new_users) < 50:
                        log.info("✅ Einde bereikt (minder dan page_size)")
                        break
                        
                    page += 1
                except Exception as e:
                    log.exception(f"❌ Fout bij verwerken API response: {str(e)}")
                    break
            else:
                # ✅ ALS /Users MISLUKT, PROBEER DAN /Person ENDPOINT
                if page == 1 and r.status_code == 404:
                    log.warning(f"⚠️ /Users endpoint niet gevonden (HTTP 404), probeer /Person endpoint...")
                    endpoint = "/Person"
                    log.info(f"ℹ️ Probeer alternatief endpoint: {HALO_API_BASE}{endpoint}")
                    page = 1  # Reset paginering voor nieuw endpoint
                else:
                    log.error(f"❌ Fout bij ophalen pagina {page}: HTTP {r.status_code}")
                    log.error(f"➡️ Response: {r.text}")
                    break
                    
        except Exception as e:
            log.exception(f"❌ Fout tijdens API-aanroep: {str(e)}")
            break
            
    log.info(f"👥 SUCCES: {len(all_users)} unieke klantgebruikers opgehaald voor klant {client_id} en locatie {site_id}")
    return all_users

def get_main_users():
    """24-UURS CACHE VOOR KLANTGEBRUIKERS"""
    current_time = time.time()
    # Controleer of cache geldig is
    if USER_CACHE["users"] and (current_time - USER_CACHE["timestamp"] < CACHE_DURATION):
        log.info(f"✅ Cache gebruikt (vernieuwd {int((current_time - USER_CACHE['timestamp'])/60)} minuten geleden)")
        return USER_CACHE["users"]
    
    log.warning("🔄 Cache verlopen, vernieuwen Bossers & Cnossen klantgebruikers…")
    log.info("⏳ Start ophalen van alle klantgebruikers...")
    start_time = time.time()
    users = fetch_all_site_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    duration = time.time() - start_time
    log.info(f"⏱️  Klantgebruikers opgehaald in {duration:.2f} seconden")
    
    USER_CACHE["users"] = users
    USER_CACHE["timestamp"] = time.time()
    log.info(f"✅ {len(users)} UNIEKE KLANTGEBRUIKERS GECACHED")
    return USER_CACHE["users"]

def get_halo_user_id(email: str):
    """ZOEK KLANTGEBRUIKER OP EMAIL MET CASE-INSENSITIVE MATCHING"""
    if not email:
        return None
    email = email.strip().lower()
    log.debug(f"🔍 Zoeken naar klantgebruiker met email: {email}")
    main_users = get_main_users()
    
    for u in main_users:
        # Alle mogelijke email velden controleren
        email_fields = [
            str(u.get("EmailAddress") or "").lower(),
            str(u.get("emailaddress") or "").lower(),
            str(u.get("PrimaryEmail") or "").lower(),
            str(u.get("username") or "").lower()
        ]
        
        # ✅ UITGEBREIDE LOGGING VOOR DEBUGGING
        for field in email_fields:
            if field:
                log.debug(f"🔍 Vergelijking: '{field}' vs '{email}'")
        
        if email in [e for e in email_fields if e]:
            log.info(f"✅ Email match gevonden: {email} → Klantgebruiker ID={u.get('id')}")
            return u.get("id")
    
    log.warning(f"⚠️ Geen klantgebruiker gevonden voor email: {email}")
    return None
log.info("✅ Klantgebruiker cache functies geregistreerd")
# ------------------------------------------------------------------------------
# Halo Tickets (GEFIXT VOOR UW SPECIFIEKE UAT)
# ------------------------------------------------------------------------------
def create_halo_ticket(summary, name, email, omschrijving, sindswanneer,
                       watwerktniet, zelfgeprobeerd, impacttoelichting,
                       impact_id, urgency_id, room_id=None):
    log.info(f"🎫 Ticket aanmaken: '{summary}' voor {email}")
    h = get_halo_headers()
    user_id = get_halo_user_id(email)
    
    # ✅ CRUCIALE FIX: ALLE ID'S ALS STRING (GEEN INTEGER) - UAT VEREIST STRINGS
    body = {
        "Summary": str(summary),
        "Details": str(omschrijving),
        "TypeID": str(HALO_TICKET_TYPE_ID),
        "ClientID": str(HALO_CLIENT_ID_NUM),
        "SiteID": str(HALO_SITE_ID),
        "TeamID": str(HALO_TEAM_ID),
        "ImpactID": str(impact_id),
        "UrgencyID": str(urgency_id)
    }
    
    # ✅ USER VALIDATIE VOOR UAT
    if not user_id:
        log.critical("❌ FATALE FOUT: Geen klantgebruiker gevonden - Controleer klant/locatie ID's")
        if room_id:
            send_message(room_id, "⚠️ Geen klantgebruiker gevonden in Halo. Controleer configuratie.")
        return None
    
    # ✅ CRUCIALE FIX: GEBRUIK UserID VOOR UW SPECIFIEKE UAT
    body["UserID"] = str(user_id)
    log.info(f"👤 Ticket gekoppeld aan klantgebruiker ID: {user_id}")
    log.debug(f"➡️ Volledige ticket payload: {body}")

    try:
        # ✅ CRUCIALE FIX: WRAP TICKET IN ARRAY VOOR HALO API
        request_body = [body]
        log.debug(f"➡️ Halo API aanroep voor basis ticket: {request_body}")
        
        r = requests.post(
            f"{HALO_API_BASE}/Tickets",
            headers=h,
            json=request_body,  # ✅ BELANGRIJK: Array in plaats van object
            timeout=15
        )
        
        log.info(f"⬅️ API response status: {r.status_code}")
        log.debug(f"⬅️ Volledige API response: {r.text}")
        
        if r.status_code not in (200, 201):
            log.error(f"❌ Basis ticket aanmaken mislukt: {r.status_code}")
            log.error(f"➡️ Response body: {r.text}")
            
            if room_id:
                send_message(room_id, f"⚠️ Ticket aanmaken mislukt ({r.status_code})")
            return None

        # ✅ FIX: Verwerk array response
        try:
            response_data = r.json()
            if isinstance(response_data, list) and len(response_data) > 0:
                ticket = response_data[0]  # Eerste ticket uit de array
                ticket_id = ticket.get("ID") or ticket.get("id")
                if ticket_id:
                    log.info(f"✅ Ticket succesvol aangemaakt met ID: {ticket_id}")
                else:
                    log.error("❌ Ticket ID niet gevonden in antwoord")
                    return None
            else:
                log.error("❌ Ongeldig antwoord van Halo API - geen ticket ontvangen")
                return None
        except Exception as e:
            log.exception("❌ Fout bij verwerken API response")
            return None

        # ✅ PUBLIC NOTE TOEVOEGEN MET ALLE INFORMATIE
        log.info(f"📝 Public note toevoegen aan ticket {ticket_id}...")
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
            room_id=room_id
        )
        
        if note_added:
            log.info(f"✅ Public note succesvol toegevoegd aan ticket {ticket_id}")
            return {"ID": ticket_id, "Ref": f"BC-{ticket_id}"}
        else:
            log.warning(f"⚠️ Public note kon niet worden toegevoegd aan ticket {ticket_id}")
            return {"ID": ticket_id}
            
    except Exception as e:
        log.exception(f"❌ Fout bij ticket aanmaken: {str(e)}")
        if room_id:
            send_message(room_id, "⚠️ Technische fout bij ticket aanmaken")
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
        "ActionTypeID": str(HALO_ACTIONTYPE_PUBLIC),
        "IsPrivate": False,
        "TimeSpent": "00:00:00"
    }
    
    # Koppel de note aan de gebruiker
    if email:
        user_id = get_halo_user_id(email)
        if user_id:
            body["UserID"] = str(user_id)
            log.info(f"📎 Note gekoppeld aan klantgebruiker ID: {user_id}")
    
    try:
        r = requests.post(
            f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions",
            headers=h,
            json=body,
            timeout=10
        )
        
        log.info(f"⬅️ Note API response status: {r.status_code}")
        
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
            msg = requests.get(
                f"https://webexapis.com/v1/messages/{msg_id}",
                headers=WEBEX_HEADERS,
                timeout=10
            ).json()
            text, room_id, sender = msg.get("text","").strip(), msg.get("roomId"), msg.get("personEmail")
            
            if sender and sender.endswith("@webex.bot"):
                return
                
            if "nieuwe melding" in text.lower():
                log.info("📝 'nieuwe melding' commando gedetecteerd")
                send_adaptive_card(room_id)
                send_message(room_id,"📋 Vul formulier in om ticket te starten.")
            else:
                for t_id, rid in ticket_room_map.items():
                    if rid == room_id:
                        log.info(f"💬 Webex bericht naar ticket {t_id}")
                        add_note_to_ticket(t_id, text, sender, email=sender, room_id=room_id)
                        
        elif res == "attachmentActions":
            act_id = data["data"]["id"]
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
                if ticket_id:
                    ticket_room_map[ticket_id] = data["data"]["roomId"]
                    ref = ticket.get('Ref', f"BC-{ticket_id}")
                    log.info(f"🎫 Ticket {ref} succesvol aangemaakt (ID: {ticket_id})")
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
            "user_cache_size": len(USER_CACHE["users"]),
            "cache_age_minutes": int((time.time() - USER_CACHE["timestamp"])/60) if USER_CACHE["users"] else 0,
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
    get_main_users()
    duration = time.time() - start_time
    log.info(f"⏱️  Cache geinitialiseerd in {duration:.2f} seconden")
    
    # Extra validatie
    if len(USER_CACHE['users']) == 0:
        log.critical("❌ CACHE IS LEEG! Mogelijke oorzaken:")
        log.critical("1. Verkeerde klant/locatie ID's (momenteel: Client=%s, Site=%s)", HALO_CLIENT_ID_NUM, HALO_SITE_ID)
        log.critical("2. Halo API token problemen")
        log.critical("3. Verkeerd API-endpoint (gebruikte endpoint: %s)", "/Users of /Person")
    
    return {
        "status": "initialized",
        "user_cache_size": len(USER_CACHE["users"]),
        "duration_seconds": duration,
        "cache_timestamp": USER_CACHE["timestamp"],
        "client_id": HALO_CLIENT_ID_NUM,
        "site_id": HALO_SITE_ID,
        "used_endpoint": "/Users or /Person"
    }

@app.route("/cache", methods=["GET"])
def inspect_cache():
    """Endpoint om de cache te inspecteren"""
    log.info("🔍 Cache inspectie aangevraagd")
    
    # Maak een schone versie van de cache voor weergave
    clean_cache = []
    for user in USER_CACHE["users"]:
        clean_user = {
            "id": user.get("id", "N/A"),
            "name": user.get("name", "N/A"),
            "emails": []
        }
        
        # Verzamel alle emailvelden
        email_fields = [
            user.get("EmailAddress", ""),
            user.get("emailaddress", ""),
            user.get("PrimaryEmail", ""),
            user.get("username", "")
        ]
        
        # Voeg alleen niet-lege emails toe
        for email in email_fields:
            if email and email.lower() not in [e.lower() for e in clean_user["emails"]]:
                clean_user["emails"].append(email)
        
        clean_cache.append(clean_user)
    
    log.info(f"📊 Cache inspectie: {len(clean_cache)} unieke gebruikers gevonden")
    return jsonify({
        "status": "success",
        "cache_size": len(clean_cache),
        "cache_timestamp": USER_CACHE["timestamp"],
        "users": clean_cache[:20],  # Toon maximaal 20 gebruikers voor overzicht
        "truncated": len(clean_cache) > 20,
        "message": "Toon slechts 20 gebruikers voor overzicht - gebruik filters voor specifieke zoekopdrachten"
    })
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
    log.info("✅ GEBRUIKT /Users OF /Person ENDPOINT VOOR KLANTGEBRUIKERS")
    log.info("✅ UserID GEBRUIKT VOOR KOPPELING (ALS STRING)")
    log.info("✅ ALLE ID'S WORDEN ALS STRING VERZONDEN")
    log.info("✅ ONEINDIGE LUS VOORKOMEN MET UNIEKE ID CHECK")
    log.info("✅ NIEUW /cache ENDPOINT VOOR CACHE INSPECTIE")
    log.info("✅ FIX VOOR 'PLEASE SELECT A VALID CLIENT/SITE/USER' FOUT")
    log.info("-"*70)
    
    # ✅ INITIELE CACHE LOADING BIJ OPSTARTEN
    log.warning("⏳ Initialiseren klantgebruikerscache bij opstarten...")
    start_time = time.time()
    try:
        get_main_users()
        init_time = time.time() - start_time
        log.info(f"✅ Klantgebruikerscache geïnitialiseerd in {init_time:.2f} seconden")
        log.info(f"📊 Cache bevat nu {len(USER_CACHE['users'])} unieke klantgebruikers")
        
        # Extra validatie
        if len(USER_CACHE['users']) == 0:
            log.critical("❗️ WAARSCHUWING: Lege cache - Controleer Halo configuratie!")
    
    except Exception as e:
        log.exception(f"❌ Fout bij initialiseren cache: {str(e)}")
    
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN:")
    log.info("1. Deploy deze code naar Render")
    log.info("2. Bezoek direct na deploy: /initialize")
    log.info("3. Controleer de logs op:")
    log.info("   - '✅ Unieke klantgebruiker gevonden'")
    log.info("   - '✅ {N} UNIEKE KLANTGEBRUIKERS GECACHED'")
    log.info("4. Bezoek /cache endpoint om de gecachte gebruikers te inspecteren")
    log.info("   Voorbeeld: https://uw-app-naam.onrender.com/cache")
    log.info("5. Typ in Webex: 'nieuwe melding' om het formulier te openen")
    log.info("6. Vul het formulier in en verstuur")
    log.info("7. Controleer logs op succesmeldingen:")
    log.info("   - '👤 Ticket gekoppeld aan klantgebruiker ID: 1086'")
    log.info("   - '➡️ Halo API aanroep voor basis ticket: [{...}]'")
    log.info("   - '✅ Ticket succesvol aangemaakt'")
    log.info("   - '✅ Public note succesvol toegevoegd'")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port, debug=False)
