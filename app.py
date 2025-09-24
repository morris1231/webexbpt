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

# Doel-emails - Haal ze uit .env of gebruik standaardwaarden
TARGET_EMAILS = os.getenv("TARGET_EMAILS", "Edwin.Nieborg@bnc.nl,danja.berlo@bnc.nl")
TARGET_EMAILS = [email.strip().lower() for email in TARGET_EMAILS.split(",")]

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
    """HAAL EERST ALLE GEBRUIKERS OP, ZOEK DAN DE SPECIFIEKE EMAILS"""
    log.info("🔍 Start met het ophalen van alle gebruikers")
    all_users = []
    page = 1
    max_pages = 100
    consecutive_empty = 0
    target_user = None
    sample_emails = []  # Bewaar voorbeeld-emails voor debug

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
            
            # Stap 2: Zoek de specifieke doel-emails terwijl we de gebruikers ophalen
            if not target_user:
                for u in users:
                    # Verzamel voorbeeld-emails voor debug
                    if len(sample_emails) < 5:
                        email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
                        if email:
                            sample_emails.append(email)
                    
                    # Haal email op (case-insensitive)
                    email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
                    
                    # Check of dit een van de doel-emails is
                    for target_email in TARGET_EMAILS:
                        if email == target_email:
                            target_user = u
                            log.info(f"✅ GEVONDEN: {target_email} - ID: {u.get('id')}")
                            log.info(f"   Volledige email: {email}")
                            log.info(f"   Naam: {u.get('name', 'Onbekend')}")
                            break
                    if target_user:
                        break
            
            # Als we de doelgebruiker hebben gevonden, stop met ophalen
            if target_user:
                log.info("✅ Doelgebruiker gevonden, stop met ophalen van verdere pagina's")
                break
            
            if len(users) < 50:
                log.info("✅ Laatste pagina bereikt (minder dan 50 gebruikers)")
                break
            
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            log.error(f"⚠️ Fout bij ophalen pagina {page}: {str(e)}")
            break

    log.info(f"✅ Totaal opgehaald: {len(all_users)} gebruikers")

    # Als we de doelgebruiker niet hebben gevonden, geef een gedetailleerde error
    if not target_user:
        log.error("❌ FATAAL: Geen van de doel-emails gevonden in gebruikerslijst!")
        log.error(f"➡️ Gezochte email(s): {', '.join(TARGET_EMAILS)}")
        
        # Toon voorbeeld-emails voor debug
        if sample_emails:
            log.error("➡️ Voorbeeld-emails uit API response:")
            for i, email in enumerate(sample_emails, 1):
                log.error(f"   {i}. {email}")
        
        log.error("➡️ Mogelijke oorzaken:")
        log.error("   1. De API key heeft geen toegang tot alle gebruikers")
        log.error("   2. De emailadressen staan niet letterlijk zo in Halo")
        log.error("   3. De emailvelden in de API response hebben een andere naam")
        log.error("➡️ Oplossing:")
        log.error("   1. Controleer de voorbeeld-emails bovenaan")
        log.error("   2. Pas de TARGET_EMAILS aan in .env naar de exacte spelling")
        log.error("   3. Bezoek /debug voor meer technische details")
        
        return []
    
    # Stap 3: Haal de client_id en site_id van de doelgebruiker op
    log.info("🔍 Bepaal de groep van de doelgebruiker via zijn gebruikersgegevens...")
    
    # Haal client_id op
    client_id = None
    client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
    for key in client_id_keys:
        if key in target_user and target_user[key] is not None:
            try:
                client_id = str(target_user[key]).strip()
                log.info(f"✅ Gebruik client_id van doelgebruiker: {client_id} (gevonden via '{key}')")
                break
            except:
                pass
    
    # Haal site_id op
    site_id = None
    site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
    for key in site_id_keys:
        if key in target_user and target_user[key] is not None:
            try:
                site_id = str(target_user[key]).strip()
                log.info(f"✅ Gebruik site_id van doelgebruiker: {site_id} (gevonden via '{key}')")
                break
            except:
                pass
    
    # Controleer of we bruikbare ID's hebben gevonden
    if not client_id or not site_id:
        log.warning("⚠️ Kon geen volledige groepinformatie vinden in doelgebruiker record")
        
        # Probeer via client/site namen
        client_name = str(target_user.get("client_name", "")).strip().lower()
        site_name = str(target_user.get("site_name", "")).strip().lower()
        
        if client_name:
            log.info(f"ℹ️ Gebruik client_name: {client_name}")
        if site_name:
            log.info(f"ℹ️ Gebruik site_name: {site_name}")
    
    # Stap 4: Filter alle gebruikers op basis van de doelgebruiker groep
    log.info("🔍 Filter alle gebruikers op basis van de doelgebruiker groep...")
    main_users = []
    
    for u in all_users:
        # Controleer client ID
        client_match = False
        if client_id:
            for key in client_id_keys:
                if key in u and u[key] is not None:
                    try:
                        if str(u[key]).strip() == client_id:
                            client_match = True
                            break
                    except:
                        pass
        elif client_name:  # Fallback op client naam
            u_client_name = str(u.get("client_name", "")).strip().lower()
            if client_name in u_client_name:
                client_match = True
        
        # Controleer site ID
        site_match = False
        if site_id:
            for key in site_id_keys:
                if key in u and u[key] is not None:
                    try:
                        if str(u[key]).strip() == site_id:
                            site_match = True
                            break
                    except:
                        pass
        elif site_name:  # Fallback op site naam
            u_site_name = str(u.get("site_name", "")).strip().lower()
            if site_name in u_site_name:
                site_match = True
        
        # Bepaal of dit een gebruiker is uit dezelfde groep
        if client_match and site_match:
            main_users.append(u)
    
    # Stap 5: Validatie - zorg dat de doelgebruiker in de resultaten zit
    target_found = False
    for u in main_users:
        email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
        if email in TARGET_EMAILS:
            target_found = True
            break
    
    if not target_found:
        log.warning("⚠️ WAARSCHUWING: Doelgebruiker niet gevonden in gefilterde resultaten!")
        log.warning("➡️ Mogelijke oorzaken:")
        log.warning("   1. Verkeerde client/site ID's gebruikt")
        log.warning("   2. API geeft geen volledige gebruikersdata terug")
        log.warning("   3. Doelgebruiker heeft een andere groep in Halo")
    else:
        log.info("✅ BEVESTIGING: Doelgebruiker zit in de gefilterde resultaten")
    
    log.info(f"📊 Totaal gebruikers in dezelfde groep: {len(main_users)}/{len(all_users)}")
    return main_users

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_notes": [
            "1. Haalt EERST alle gebruikers op",
            "2. ZOEKT DAN de exacte email(s) uit .env",
            "3. FILTERT vervolgens op basis van DEZE GROEP",
            "4. Bezoek /debug voor technische details"
        ],
        "config": {
            "target_emails": TARGET_EMAILS
        }
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLEEN de gebruikers uit dezelfde groep als de doelgebruiker"""
    main_users = fetch_all_users()
    
    if not main_users:
        return jsonify({
            "error": "Geen gebruikers gevonden in de doelgroep",
            "solution": [
                "1. Controleer de logs voor voorbeeld-emails",
                "2. Pas de TARGET_EMAILS aan in .env naar de exacte spelling",
                "3. Zorg dat de API key toegang heeft tot alle gebruikers"
            ],
            "current_target_emails": TARGET_EMAILS
        }), 500
    
    simplified = [{
        "id": u.get("id"),
        "name": u.get("name") or "Onbekend",
        "email": u.get("emailaddress") or u.get("email") or "Geen email"
    } for u in main_users]
    
    # Bepaal client en site namen voor de response
    client_name = "Onbekend"
    site_name = "Onbekend"
    
    if main_users:
        first_user = main_users[0]
        client_name = first_user.get("client_name") or "Bossers & Cnossen"
        site_name = first_user.get("site_name") or "Main"
    
    return jsonify({
        "client_name": client_name,
        "site_name": site_name,
        "total_users": len(main_users),
        "users": simplified
    })

@app.route("/debug", methods=["GET"])
def debug():
    """Toon technische details voor debugging"""
    main_users = fetch_all_users()
    
    # Haal voorbeeldgegevens op voor debug
    sample_user = main_users[0] if main_users else {}
    client_id = None
    site_id = None
    
    for key in ["client_id", "ClientId", "clientId", "ClientID", "clientid"]:
        if key in sample_user:
            client_id = sample_user[key]
            break
    
    for key in ["site_id", "SiteId", "siteId", "SiteID", "siteid"]:
        if key in sample_user:
            site_id = sample_user[key]
            break
    
    return {
        "status": "debug-info",
        "api_flow": [
            "1. Authenticatie naar /auth/token (scope=all)",
            "2. Haal ALLE gebruikers op via /Users met paginering (50 per pagina)",
            "3. ZOEK EXACTE EMAIL(S) UIT .env",
            "4. FILTER OP BASIS VAN GROEP VAN DEZE GEBRUIKER"
        ],
        "configuration": {
            "target_emails": TARGET_EMAILS,
            "halo_client_id": HALO_CLIENT_ID,
            "halo_api_base": HALO_API_BASE
        },
        "halo_notes": [
            "1. Eerst ALLE gebruikers ophalen, DAN filteren",
            "2. Gebruikt EXACTE EMAIL MATCHING (geen varianten)",
            "3. Case-insensitive matching (email is niet hoofdlettergevoelig)"
        ],
        "current_counts": {
            "total_users_found": len(main_users),
            "total_users_fetched": len(fetch_all_users.cache) if hasattr(fetch_all_users, 'cache') else "N/A"
        },
        "sample_user_data": {
            "id": sample_user.get("id"),
            "name": sample_user.get("name"),
            "email": sample_user.get("emailaddress") or sample_user.get("email"),
            "client_id_field": client_id,
            "site_id_field": site_id,
            "client_name": sample_user.get("client_name"),
            "site_name": sample_user.get("site_name")
        },
        "safety_mechanisms": [
            "• Maximaal 100 pagina's om oneindige lus te voorkomen",
            "• 0.3s delay tussen aanvragen om rate limiting te voorkomen",
            "• 3 opeenvolgende lege pagina's stoppen de lus",
            "• Herkansingen bij tijdelijke netwerkfouten",
            "• Fallback op client/site namen als ID's ontbreken"
        ],
        "troubleshooting": [
            "Als de doelgebruiker niet wordt gevonden:",
            "1. Check de logs voor 'Voorbeeld-emails uit API response'",
            "2. Pas de TARGET_EMAILS aan in .env naar de EXACTE spelling",
            "3. Gebruik /debug om te zien hoe de email in Halo staat"
        ]
    }

# ------------------------------------------------------------------------------
# App Start
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - EXACTE EMAIL MATCHING")
    log.info("-"*70)
    log.info(f"✅ Gebruikt EXACTE EMAILS: {', '.join(TARGET_EMAILS)}")
    log.info("✅ Case-insensitive matching (email is niet hoofdlettergevoelig)")
    log.info("✅ Werkt met jouw specifieke Halo UAT omgeving")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Controleer of je doel-email wordt GEVONDEN in logs")
    log.info("3. Bezoek /users voor de correcte gebruikerslijst")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port, debug=True)
