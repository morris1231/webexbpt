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

HALO_AUTH_URL = "https://bncuat.halopsa.com/auth/token"  
HALO_API_BASE = "https://bncuat.halopsa.com/api"  
log.info(f"✅ Halo API endpoints ingesteld: {HALO_AUTH_URL} en {HALO_API_BASE}")

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")  
if not WEBEX_TOKEN:  
    log.critical("❌ FOUT: WEBEX_BOT_TOKEN niet ingesteld in .env!")  
else:  
    log.info(f"✅ Webex token gevonden (lengte: {len(WEBEX_TOKEN)} tekens)")  
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"}

HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()  
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()  
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:  
    log.critical("❌ FOUT: Halo credentials niet ingesteld in .env!")  
else:  
    log.info(f"✅ Halo AGENT credentials gevonden (Client ID: {HALO_CLIENT_ID})")

HALO_TICKET_TYPE_ID = 65  
HALO_TEAM_ID = 1  
HALO_DEFAULT_IMPACT = 3  
HALO_DEFAULT_URGENCY = 3  
HALO_ACTIONTYPE_PUBLIC = 78  
log.info(f"✅ Halo ticket instellingen: Type={HALO_TICKET_TYPE_ID}, Team={HALO_TEAM_ID}")

HALO_CLIENT_ID_NUM = 986 # Bossers & Cnossen  
HALO_SITE_ID = 992 # Main site  
log.info(f"✅ Gebruikt klant ID: {HALO_CLIENT_ID_NUM} (Bossers & Cnossen)")  
log.info(f"✅ Gebruikt locatie ID: {HALO_SITE_ID} (Main site)")

CONTACT_CACHE = {"contacts": [], "timestamp": 0}  
CACHE_DURATION = 24 * 60 * 60 # ✅ FIXED  
log.info("✅ Cache systeem geïnitialiseerd (24-uurs cache)")

ticket_room_map = {}  
log.info("✅ Ticket kamer mapping systeem geïnitialiseerd")

# **------------------------------------------------------------------------------**
# **Contact Cache (BEHOUDE DE OPRINTELIJKE WERKENDE CACHE)**
# **------------------------------------------------------------------------------**
def get_halo_headers():  
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

def fetch_all_site_contacts(client_id: int, site_id: int, max_pages=20):  
    log.info(f"🔍 Start ophalen klantcontacten voor klant {client_id} en locatie {site_id}")  
    h = get_halo_headers()  
    all_contacts = []  
    page = 1  
    processed_ids = set()  
    endpoint = "/Users"  
    while page <= max_pages:  
        params = {"include": "site,client", "client_id": client_id, "site_id": site_id, "type": "contact", "page": page, "page_size": 50}  
        try:  
            r = requests.get(f"{HALO_API_BASE}{endpoint}", headers=h, params=params, timeout=15)  
            if r.status_code == 200:  
                data = r.json()  
                contacts = data.get('users', []) or data.get('items', []) or data  
                if not contacts: break  
                for contact in contacts:  
                    cid = str(contact.get('id',''))  
                    if cid and cid not in processed_ids:  
                        processed_ids.add(cid)  
                        all_contacts.append(contact)  
                        log.info(f"👤 Uniek contact: {contact.get('name')} ({cid})")  
                if len(contacts) < 50: break  
                page += 1  
            elif page == 1 and r.status_code == 404:  # ✅ FIX  
                endpoint = "/Person"  
                page = 1  
            else: break  
        except Exception as e:  
            log.exception(f"❌ Fout tijdens ophalen")  
            break  
    return all_contacts  

def get_main_contacts():  
    now = time.time()  
    if CONTACT_CACHE["contacts"] and (now - CONTACT_CACHE["timestamp"] < CACHE_DURATION):  
        return CONTACT_CACHE["contacts"]  
    CONTACT_CACHE["contacts"] = fetch_all_site_contacts(HALO_CLIENT_ID_NUM, HALO_SITE_ID)  
    CONTACT_CACHE["timestamp"] = now  
    return CONTACT_CACHE["contacts"]  

def get_halo_contact_id(email: str):  
    if not email: return None  
    email = email.strip().lower()  
    for c in get_main_contacts():  
        possible = [str(c.get("EmailAddress") or "").lower(), str(c.get("emailaddress") or "").lower(), str(c.get("PrimaryEmail") or "").lower(), str(c.get("username") or "").lower()]  
        if any(email == p for p in possible if p):  
            log.info(f"✅ Email match voor {email}: ID={c.get('id')}")  
            return c.get("id")  
    return None  

def get_contact_name(contact_id):  
    for c in get_main_contacts():  
        if str(c.get("id")) == str(contact_id):  
            name = c.get("name","Onbekend")  
            log.info(f"👤 Naam gevonden: {name}")  
            return name  
    return "Onbekend"  

# **------------------------------------------------------------------------------**
# **Tickets (FIX)**
# **------------------------------------------------------------------------------**
def create_halo_ticket(omschrijving, email, sindswanneer, watwerktniet, zelfgeprobeerd, impacttoelichting, impact_id, urgency_id, room_id=None):  
    log.info(f"🎫 Ticket aanmaken voor {email}")  
    h = get_halo_headers()  
    contact_id = get_halo_contact_id(email)  
    if not contact_id:  
        log.error("❌ Geen contact ID")  
        return None  
    contact_name = get_contact_name(contact_id)  

    body = {  
        "summary": str(omschrijving)[:100],  
        "details": str(omschrijving),  
        "typeId": int(HALO_TICKET_TYPE_ID),  
        "clientId": int(HALO_CLIENT_ID_NUM),  
        "siteId": int(HALO_SITE_ID),  
        "teamId": int(HALO_TEAM_ID),  
        "impactId": int(impact_id),  
        "urgencyId": int(urgency_id),  
        "requesterId": int(contact_id),  
        "requesterEmail": email  
    }  
    try:  
        # ✅ Belangrijk: Halo verwacht array van tickets  
        r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[body], timeout=15)  
        log.info(f"⬅️ Halo status {r.status_code}")  
        if r.status_code in (200, 201):  
            response = r.json()  
            ticket = response[0] if isinstance(response, list) else response  
            ticket_id = ticket.get("id") or ticket.get("ID")  
            log.info(f"✅ Ticket aangemaakt ID={ticket_id}")  

            note = (f"**Naam:** {contact_name}\n"  
                    f"**E-mail:** {email}\n"  
                    f"**Probleemomschrijving:** {omschrijving}\n"  
                    f"**Sinds:** {sindswanneer}\n"  
                    f"**Wat werkt niet:** {watwerktniet}\n"  
                    f"**Zelf geprobeerd:** {zelfgeprobeerd}\n"  
                    f"**Impact toelichting:** {impacttoelichting}")  
            add_note_to_ticket(ticket_id, note, contact_name, email, room_id, contact_id)  
            return {"ID": ticket_id, "Ref": f"BC-{ticket_id}", "contact_id": contact_id}  
        else:  
            log.error(f"❌ Ticket request error {r.text}")  
            return None  
    except Exception as e:  
        log.exception("❌ Ticket exception")  
        return None  

# **------------------------------------------------------------------------------**
# **Notes**
# **------------------------------------------------------------------------------**
def add_note_to_ticket(ticket_id, public_output, sender, email=None, room_id=None, contact_id=None):  
    log.info(f"📎 Note toevoegen aan ticket {ticket_id}")  
    h = get_halo_headers()  
    body = {"details": str(public_output), "actionTypeId": int(HALO_ACTIONTYPE_PUBLIC), "isPrivate": False, "timeSpent": "00:00:00", "userId": int(contact_id)}  
    r = requests.post(f"{HALO_API_BASE}/Tickets/{ticket_id}/Actions", headers=h, json=body, timeout=10)  
    return r.status_code in (200, 201)  

# ... (je Webex handlers, /initialize, /cache, etc. blijven exact gelijk; geen aanpassing daar) ...

# **------------------------------------------------------------------------------**
# **Start app**
# **------------------------------------------------------------------------------**
if __name__ == "__main__":   # ✅ FIXED  
    port = int(os.getenv("PORT", 5000))  
    log.info("🚀 Starting Bossers & Cnossen Webex Ticket Bot...")  
    app.run(host="0.0.0.0", port=port, debug=False)
