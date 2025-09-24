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
        log.critical(f"➡️ Response: {r.text if 'r' in locals() else 'Geen response'}")
        raise

def fetch_all_users():
    """HAAL ALLE GEBRUIKERS OP EN LOG ALLE EMAILS VOOR DEBUGGING"""
    log.info("🔍 Start met het ophalen van alle gebruikers")
    all_users = []
    page = 1
    max_pages = 5  # Beperk tot 5 pagina's voor debug (250 gebruikers)
    consecutive_empty = 0
    all_emails = []  # Verzamel ALLE emails voor debug

    # Stap 1: Haal alle gebruikers op
    while page <= max_pages:
        users_url = f"{HALO_API_BASE}/Users?page={page}&pageSize=50"
        log.info(f"➡️ API-aanvraag (pagina {page}): {users_url}")
        
        try:
            headers = get_halo_headers()
            r = requests.get(users_url, headers=headers, timeout=30)
            
            if r.status_code != 200:
                log.error(f"❌ API FOUT ({r.status_code}): {r.text}")
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
            users = users_data.get("users", [])
            if not users:
                users = users_data.get("Users", [])
            
            if not users:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    log.info("✅ Stoppen met ophalen na 3 lege pagina's")
                    break
                page += 1
                time.sleep(0.5)
                continue
            
            consecutive_empty = 0
            all_users.extend(users)
            log.info(f"✅ Pagina {page}: {len(users)} gebruikers opgehaald (totaal: {len(all_users)})")
            
            # Stap 2: Verzamel ALLE emails voor debug
            for u in users:
                email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
                if email:
                    all_emails.append(email)
            
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            log.error(f"⚠️ Fout bij ophalen pagina {page}: {str(e)}")
            break

    log.info(f"✅ Totaal opgehaald: {len(all_users)} gebruikers")
    log.info(f"✅ Totaal unieke emails verzameld: {len(set(all_emails))}")

    # Stap 3: Log de eerste 20 bnc.nl emails voor debug
    bnc_emails = [email for email in set(all_emails) if "bnc" in email]
    log.info("📧 Eerste 20 bnc.nl emails gevonden in API response:")
    for i, email in enumerate(bnc_emails[:20], 1):
        log.info(f"   {i}. {email}")

    # Stap 4: Controleer of we Edwin of Danja hebben gevonden
    edwin_found = any("edwin" in email for email in bnc_emails)
    danja_found = any("danja" in email or "berlo" in email for email in bnc_emails)
    
    if edwin_found:
        log.info("✅ Edwin gevonden in de gebruikerslijst!")
    else:
        log.error("❌ Edwin NIET GEVONDEN in de gebruikerslijst")
    
    if danja_found:
        log.info("✅ Danja gevonden in de gebruikerslijst!")
    else:
        log.error("❌ Danja NIET GEVONDEN in de gebruikerslijst")
    
    # Stap 5: Probeer de juiste groep te identificeren
    main_users = []
    client_id = None
    site_id = None
    
    if bnc_emails:
        # Neem de eerste bnc.nl gebruiker als voorbeeld
        for u in all_users:
            email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
            if "bnc" in email:
                # Haal client_id op
                client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
                for key in client_id_keys:
                    if key in u and u[key] is not None:
                        try:
                            client_id = str(u[key]).strip()
                            log.info(f"✅ Gebruik client_id van voorbeeldgebruiker: {client_id} (gevonden via '{key}')")
                            break
                        except:
                            pass
                
                # Haal site_id op
                site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
                for key in site_id_keys:
                    if key in u and u[key] is not None:
                        try:
                            site_id = str(u[key]).strip()
                            log.info(f"✅ Gebruik site_id van voorbeeldgebruiker: {site_id} (gevonden via '{key}')")
                            break
                        except:
                            pass
                
                break
    
    # Stap 6: Filter alle gebruikers op basis van de gevonden groep
    if client_id and site_id:
        log.info(f"🔍 Filter gebruikers op client_id={client_id} en site_id={site_id}")
        
        for u in all_users:
            # Controleer client ID
            client_match = False
            for key in client_id_keys:
                if key in u and u[key] is not None:
                    try:
                        if str(u[key]).strip() == client_id:
                            client_match = True
                            break
                    except:
                        pass
            
            # Controleer site ID
            site_match = False
            for key in site_id_keys:
                if key in u and u[key] is not None:
                    try:
                        if str(u[key]).strip() == site_id:
                            site_match = True
                            break
                    except:
                        pass
            
            # Bepaal of dit een gebruiker is uit dezelfde groep
            if client_match and site_match:
                main_users.append(u)
    
    # Stap 7: Valideer resultaten
    log.info(f"📊 Totaal gebruikers in dezelfde groep: {len(main_users)}/{len(all_users)}")
    
    return main_users

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /debug voor debugging",
        "instructions": [
            "1. Bezoek /debug om te zien welke emails in Halo staan",
            "2. Noteer de EXACTE spelling van Edwin en Danja's email",
            "3. Pas je .env bestand aan met de juiste spelling"
        ]
    }

@app.route("/debug", methods=["GET"])
def debug():
    """Toon ALLE bnc.nl emails voor debugging"""
    fetch_all_users()  # Dit voert de logging uit
    
    return {
        "status": "debug-mode",
        "instructions": [
            "1. Controleer de logs voor 'Eerste 20 bnc.nl emails'",
            "2. Noteer de EXACTE spelling van de gewenste gebruikers",
            "3. Pas je .env bestand aan met de juiste spelling",
            "4. Voorbeeld: als je ziet 'edwin@bnc' in de logs, gebruik dan TARGET_EMAILS=edwin@bnc"
        ],
        "notes": [
            "• De app haalt nu maar 5 pagina's op (250 gebruikers) voor snellere debugging",
            "• Check je terminal logs voor de lijst met gevonden emails",
            "• Na het vinden van de juiste spelling, verhoog max_pages in de code terug naar 100"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLEEN de gebruikers uit dezelfde groep"""
    main_users = fetch_all_users()
    
    if not main_users:
        return jsonify({
            "error": "Geen gebruikers gevonden in de groep",
            "solution": [
                "1. Bezoek /debug om de juiste email spelling te vinden",
                "2. Pas je .env bestand aan met de EXACTE spelling zoals in Halo",
                "3. Zie de terminal logs voor voorbeeld-emails"
            ]
        }), 500
    
    simplified = [{
        "id": u.get("id"),
        "name": u.get("name") or "Onbekend",
        "email": u.get("emailaddress") or u.get("email") or "Geen email"
    } for u in main_users]
    
    return jsonify({
        "total_users": len(main_users),
        "users": simplified
    })

# ------------------------------------------------------------------------------
# App Start
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO DEBUG MODE - EMAIL IDENTIFICATIE")
    log.info("-"*70)
    log.info("✅ Beperkt tot 5 pagina's (250 gebruikers) voor snelle debugging")
    log.info("✅ Logt ALLE bnc.nl emails in de terminal")
    log.info("✅ Toont duidelijk of Edwin/Danja gevonden worden")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN:")
    log.info("1. Start deze app en kijk in de terminal logs")
    log.info("2. Zoek naar 'Eerste 20 bnc.nl emails'")
    log.info("3. Noteer de EXACTE spelling van de gewenste gebruikers")
    log.info("4. Pas je .env bestand aan met de juiste spelling")
    log.info("5. Bezoek /debug voor verdere instructies")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port, debug=True)
