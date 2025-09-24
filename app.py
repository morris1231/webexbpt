import os, urllib.parse, logging, sys, time
from flask import Flask, jsonify
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# Correcte URL voor UAT
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Authenticatie met 'all' scope"""
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    try:
        r = requests.post(
            HALO_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(payload),
            timeout=10
        )
        r.raise_for_status()
        return {
            "Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        log.critical(f"❌ AUTH MISLUKT: {str(e)}")
        if 'r' in locals():
            log.critical(f"➡️ Response: {r.text}")
            log.critical(f"➡️ Status code: {r.status_code}")
        return None

def fetch_all_clients():
    """Haal alle klanten op"""
    log.info("🔍 Haal alle klanten op via /Clients")
    clients = []
    page = 1
    max_pages = 10
    
    while page <= max_pages:
        clients_url = f"{HALO_API_BASE}/Clients?page={page}&pageSize=50"
        log.info(f"➡️ API-aanvraag klanten (pagina {page}): {clients_url}")
        
        try:
            headers = get_halo_headers()
            if not headers:
                return []
                
            r = requests.get(clients_url, headers=headers, timeout=30)
            
            if r.status_code != 200:
                log.error(f"❌ API FOUT ({r.status_code}) bij ophalen klanten: {r.text}")
                if r.status_code in [429, 500, 502, 503, 504]:
                    time.sleep(2)
                    continue
                break
                
            data = r.json()
            
            # Verwerk 'data' wrapper
            if "data" in data and isinstance(data["data"], dict):
                clients_data = data["data"]
            else:
                clients_data = data
            
            # Haal de clients lijst op
            page_clients = clients_data.get("clients", [])
            if not page_clients:
                page_clients = clients_data.get("Clients", [])
            
            if not page_clients:
                break
                
            clients.extend(page_clients)
            log.info(f"✅ Pagina {page}: {len(page_clients)} klanten opgehaald (totaal: {len(clients)})")
            
            if len(page_clients) < 50:
                break
                
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            log.error(f"⚠️ Fout bij ophalen klanten pagina {page}: {str(e)}")
            break
    
    log.info(f"✅ Totaal klanten opgehaald: {len(clients)}")
    return clients

def fetch_sites_for_client(client_id):
    """Haal alle sites op voor een specifieke klant"""
    log.info(f"🔍 Haal sites op voor klant {client_id}")
    sites = []
    page = 1
    max_pages = 5
    
    while page <= max_pages:
        sites_url = f"{HALO_API_BASE}/Sites?client_id={client_id}&page={page}&pageSize=50"
        log.info(f"➡️ API-aanvraag sites (pagina {page}): {sites主席}")
        
        try:
            headers = get_halo_headers()
            if not headers:
                return []
                
            r = requests.get(sites_url, headers=headers, timeout=30)
            
            if r.status_code != 200:
                log.error(f"❌ API FOUT ({r.status_code}) bij ophalen sites: {r.text}")
                if r.status_code in [429, 500, 502, 503, 504]:
                    time.sleep(2)
                    continue
                break
                
            data = r.json()
            
            # Verwerk 'data' wrapper
            if "data" in data and isinstance(data["data"], dict):
                sites_data = data["data"]
            else:
                sites_data = data
            
            # Haal de sites lijst op
            page_sites = sites_data.get("sites", [])
            if not page_sites:
                page_sites = sites_data.get("Sites", [])
            
            if not page_sites:
                break
                
            sites.extend(page_sites)
            log.info(f"✅ Pagina {page}: {len(page_sites)} sites opgehaald (totaal: {len(sites)})")
            
            if len(page_sites) < 50:
                break
                
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            log.error(f"⚠️ Fout bij ophalen sites voor klant {client_id}: {str(e)}")
            break
    
    log.info(f"✅ Totaal sites opgehaald voor klant {client_id}: {len(sites)}")
    return sites

def fetch_users_for_site(site_id):
    """Haal alle gebruikers op voor een specifieke site"""
    log.info(f"🔍 Haal gebruikers op voor site {site_id}")
    users = []
    page = 1
    max_pages = 10
    
    while page <= max_pages:
        users_url = f"{HALO_API_BASE}/Users?site_id={site_id}&page={page}&pageSize=50"
        log.info(f"➡️ API-aanvraag gebruikers (pagina {page}): {users_url}")
        
        try:
            headers = get_halo_headers()
            if not headers:
                return []
                
            r = requests.get(users_url, headers=headers, timeout=30)
            
            if r.status_code != 200:
                log.error(f"❌ API FOUT ({r.status_code}) bij ophalen gebruikers: {r.text}")
                if r.status_code in [429, 500, 502, 503, 504]:
                    time.sleep(2)
                    continue
                break
                
            data = r.json()
            
            # Verwerk 'data' wrapper
            if "data" in data and isinstance(data["data"], dict):
                users_data = data["data"]
            else:
                users_data = data
            
            # Haal de users lijst op
            page_users = users_data.get("users", [])
            if not page_users:
                page_users = users_data.get("Users", [])
            
            if not page_users:
                break
                
            users.extend(page_users)
            log.info(f"✅ Pagina {page}: {len(page_users)} gebruikers opgehaald (totaal: {len(users)})")
            
            if len(page_users) < 50:
                break
                
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            log.error(f"⚠️ Fout bij ophalen gebruikers voor site {site_id}: {str(e)}")
            break
    
    log.info(f"✅ Totaal gebruikers opgehaald voor site {site_id}: {len(users)}")
    return users

def fetch_all_bnc_users():
    """HAAL ALLE @bnc GEBRUIKERS OP VIA DE JUISTE KLANT/SITE HIERARCHIE"""
    log.info("🔍 Start met het ophalen van alle @bnc gebruikers via correcte hiërarchie")
    
    # Stap 1: Haal alle klanten op
    clients = fetch_all_clients()
    if not clients:
        log.error("❌ Geen klanten opgehaald - kan geen gebruikers ophalen")
        return []
    
    bnc_users = []
    total_users = 0
    bnc_count = 0
    
    # Stap 2: Voor elke klant, haal sites op
    for client in clients:
        client_id = client.get("id") or client.get("ClientId") or client.get("client_id")
        if not client_id:
            continue
            
        client_name = client.get("name", "Onbekend")
        log.info(f"🏢 Verwerk klant: {client_name} (ID: {client_id})")
        
        sites = fetch_sites_for_client(client_id)
        
        # Stap 3: Voor elke site, haal gebruikers op
        for site in sites:
            site_id = site.get("id") or site.get("SiteId") or site.get("site_id")
            if not site_id:
                continue
                
            site_name = site.get("name", "Onbekend")
            log.info(f"📍 Verwerk site: {site_name} (ID: {site_id}) voor klant {client_name}")
            
            users = fetch_users_for_site(site_id)
            total_users += len(users)
            
            # Stap 4: Filter op @bnc en bewaar klant/site info
            for user in users:
                email = str(user.get("emailaddress", "") or user.get("email", "")).strip().lower()
                
                # Bewaar klant en site info in de gebruikersdata
                user["client_id"] = client_id
                user["client_name"] = client_name
                user["site_id"] = site_id
                user["site_name"] = site_name
                
                # Filter op @bnc
                if "@bnc" in email:
                    bnc_users.append(user)
                    bnc_count += 1
                    log.info(f"📧 GEVONDEN @bnc gebruiker: {user.get('name', 'Onbekend')} - {email} (klant: {client_name}, site: {site_name})")
    
    log.info(f"✅ Totaal verwerkte gebruikers: {total_users}")
    log.info(f"✅ Totaal @bnc gebruikers gevonden: {len(bnc_users)}")
    
    return bnc_users

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "endpoints": [
            "/users - Toon alle @bnc gebruikers",
            "/debug - Technische debug informatie"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLE @bnc gebruikers met klant/site info"""
    try:
        bnc_users = fetch_all_bnc_users()
        
        if not bnc_users:
            log.error("❌ Geen @bnc gebruikers gevonden in Halo")
            return jsonify({
                "error": "Geen @bnc gebruikers gevonden",
                "solution": [
                    "1. Controleer of de API key toegang heeft tot alle klanten, sites en gebruikers",
                    "2. Zorg dat 'Clients', 'Sites' en 'Teams' zijn aangevinkt in API-toegang",
                    "3. Controleer of er gebruikers met '@bnc' in Halo staan"
                ]
            }), 500
        
        log.info(f"✅ Succesvol {len(bnc_users)} @bnc gebruikers geretourneerd")
        
        simplified = [{
            "id": u.get("id"),
            "name": u.get("name") or "Onbekend",
            "email": u.get("emailaddress") or u.get("email") or "Geen email",
            "client_name": u.get("client_name", "Onbekend"),
            "site_name": u.get("site_name", "Onbekend")
        } for u in bnc_users]
        
        return jsonify({
            "total_users": len(bnc_users),
            "users": simplified
        })
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT in /users: {str(e)}")
        return jsonify({
            "error": "Interne serverfout",
            "details": str(e)
        }), 500

@app.route("/debug", methods=["GET"])
def debug():
    """Toon technische debug informatie"""
    try:
        bnc_users = fetch_all_bnc_users()
        
        # Verzamel voorbeeldgegevens
        sample_users = []
        for i, u in enumerate(bnc_users[:5], 1):
            email = u.get("emailaddress") or u.get("email") or "Geen email"
            name = u.get("name") or "Onbekend"
            
            sample_users.append({
                "volgorde": i,
                "name": name,
                "email": email,
                "client": u.get("client_name", "Onbekend"),
                "site": u.get("site_name", "Onbekend"),
                "user_id": u.get("id", "Onbekend"),
                "client_id": u.get("client_id", "Onbekend"),
                "site_id": u.get("site_id", "Onbekend")
            })
        
        return {
            "status": "debug-info",
            "api_flow": [
                "1. Authenticatie naar /auth/token (scope=all)",
                "2. Haal ALLE klanten op via /Clients",
                "3. Voor elke klant, haal SITES op via /Sites?client_id={id}",
                "4. Voor elke site, haal GEBRUIKERS op via /Users?site_id={id}",
                "5. FILTER OP '@bnc' IN EMAIL"
            ],
            "current_counts": {
                "total_clients": len(fetch_all_clients()),
                "total_bnc_users_found": len(bnc_users)
            },
            "sample_users": sample_users,
            "safety_mechanisms": [
                "• Correcte hiërarchie volgen: Klant → Site → Gebruiker",
                "• 0.3s delay tussen aanvragen om rate limiting te voorkomen",
                "• Herkansingen bij tijdelijke netwerkfouten",
                "• Bewaart klant/site informatie met de gebruikersdata"
            ],
            "note": "Deze app volgt de officiële Halo API hiërarchie, dus elke gebruiker is correct gekoppeld aan zijn klant en site"
        }
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT in /debug: {str(e)}")
        return jsonify({
            "error": "Interne serverfout",
            "details": str(e)
        }), 500

# ------------------------------------------------------------------------------
# App Start
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO BNC USERS - CORRECTE KLANT/SITE HIERARCHIE")
    log.info("-"*70)
    log.info("✅ Volgt de officiële Halo API hiërarchie (Klant → Site → Gebruiker)")
    log.info("✅ Bewaart klant- en site-informatie met elke gebruiker")
    log.info("✅ Filtert correct op '@bnc' in de email")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Controleer of klant- en site-informatie correct wordt geretourneerd")
    log.info("3. Bezoek /users voor ALLE @bnc gebruikers met hun klant/sitedetails")
    log.info("="*70)
    
    # Gebruik de poort zoals ingesteld in de omgeving
    app.run(host="0.0.0.0", port=port, debug=False)
