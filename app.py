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
    """HAAL EERST ALLE GEBRUIKERS OP, ZOEK DAN DANIEL BERLO EN FILTER OP ZIJN GROEP"""
    log.info("🔍 Start met het ophalen van alle gebruikers")
    all_users = []
    page = 1
    max_pages = 100
    consecutive_empty = 0
    danja_user = None
    berlo_email_variants = [
        "danja.berlo@bnc.nl",
        "danja.berlo@bnc",
        "danja.berlo@bncnl",
        "daniel.berlo@bnc.nl",
        "d.berlo@bnc.nl",
        "berlo@bnc.nl"
    ]
    berlo_name_variants = [
        "danja berlo",
        "daniel berlo",
        "danja",
        "berlo",
        "danja-berlo",
        "d berlo"
    ]

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
            
            # Stap 2: Zoek Daniel Berlo terwijl we de gebruikers ophalen
            if not danja_user:
                for u in users:
                    email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
                    name = str(u.get("name", "")).strip().lower()
                    
                    # Controleer op varianten van Daniel Berlo's email
                    email_found = False
                    for variant in berlo_email_variants:
                        if variant in email:
                            email_found = True
                            break
                    
                    # Controleer op varianten van Daniel Berlo's naam
                    name_found = False
                    for variant in berlo_name_variants:
                        if variant in name:
                            name_found = True
                            break
                    
                    # Als we Daniel Berlo vinden, stop met zoeken
                    if email_found or name_found:
                        danja_user = u
                        log.info(f"✅ GEVONDEN: Daniel Berlo - ID: {u.get('id')}")
                        log.info(f"   Email: {email}")
                        log.info(f"   Naam: {name}")
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

    # Als we Daniel Berlo niet hebben gevonden, geef een error
    if not danja_user:
        log.error("❌ FATAAL: Daniel Berlo niet gevonden in gebruikerslijst!")
        log.error("➡️ Mogelijke oorzaken:")
        log.error("   1. De API key heeft geen toegang tot alle gebruikers")
        log.error("   2. Daniel Berlo heeft een andere email in Halo")
        log.error("   3. Daniel Berlo zit niet in deze Halo omgeving")
        return []
    
    # Stap 3: Haal de client_id en site_id van Daniel Berlo op
    log.info("🔍 Bepaal de groep van Daniel Berlo via zijn gebruikersgegevens...")
    
    # Haal client_id op uit Daniel Berlo's record
    client_id = None
    client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
    for key in client_id_keys:
        if key in danja_user and danja_user[key] is not None:
            try:
                client_id = str(danja_user[key]).strip()
                log.info(f"✅ Gebruik client_id van Daniel Berlo: {client_id} (gevonden via '{key}')")
                break
            except:
                pass
    
    # Haal site_id op uit Daniel Berlo's record
    site_id = None
    site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
    for key in site_id_keys:
        if key in danja_user and danja_user[key] is not None:
            try:
                site_id = str(danja_user[key]).strip()
                log.info(f"✅ Gebruik site_id van Daniel Berlo: {site_id} (gevonden via '{key}')")
                break
            except:
                pass
    
    # Controleer of we bruikbare ID's hebben gevonden
    if not client_id or not site_id:
        log.warning("⚠️ Kon geen volledige groepinformatie vinden in Daniel Berlo's record")
        log.warning("➡️ Probeer alternatieve benadering via client/site namen...")
        
        # Probeer via client/site namen
        client_name = str(danja_user.get("client_name", "")).strip().lower()
        site_name = str(danja_user.get("site_name", "")).strip().lower()
        
        if client_name:
            log.info(f"ℹ️ Gebruik client_name: {client_name}")
        if site_name:
            log.info(f"ℹ️ Gebruik site_name: {site_name}")
    
    # Stap 4: Filter alle gebruikers op basis van Daniel Berlo's groep
    log.info("🔍 Filter alle gebruikers op basis van Daniel Berlo's groep...")
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
        
        # Bepaal of dit een gebruiker is uit dezelfde groep als Daniel Berlo
        if client_match and site_match:
            main_users.append(u)
    
    # Stap 5: Validatie - zorg dat Daniel Berlo in de resultaten zit
    berlo_found = False
    for u in main_users:
        email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
        name = str(u.get("name", "")).strip().lower()
        
        # Controleer op varianten van Daniel Berlo's email
        email_found = False
        for variant in berlo_email_variants:
            if variant in email:
                email_found = True
                break
        
        # Controleer op varianten van Daniel Berlo's naam
        name_found = False
        for variant in berlo_name_variants:
            if variant in name:
                name_found = True
                break
        
        if email_found or name_found:
            berlo_found = True
            break
    
    if not berlo_found:
        log.warning("⚠️ WAARSCHUWING: Daniel Berlo niet gevonden in gefilterde resultaten!")
        log.warning("➡️ Mogelijke oorzaken:")
        log.warning("   1. Verkeerde client/site ID's gebruikt")
        log.warning("   2. API geeft geen volledige gebruikersdata terug")
        log.warning("   3. Daniel Berlo heeft een andere email in Halo")
    else:
        log.info("✅ BEVESTIGING: Daniel Berlo zit in de gefilterde resultaten")
    
    log.info(f"📊 Totaal gebruikers in dezelfde groep als Daniel Berlo: {len(main_users)}/{len(all_users)}")
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
            "2. ZOEKT DAN Daniel Berlo in de lijst",
            "3. FILTERT vervolgens op basis van ZIJN groep",
            "4. Bezoek /debug voor technische details"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLEEN de gebruikers uit dezelfde groep als Daniel Berlo"""
    main_users = fetch_all_users()
    
    if not main_users:
        return jsonify({
            "error": "Geen gebruikers gevonden in Daniel Berlo's groep",
            "solution": [
                "1. Controleer of Daniel Berlo@bnc.nl bestaat in Halo",
                "2. Zorg dat de API key toegang heeft tot alle gebruikers",
                "3. Bezoek /debug voor technische details"
            ]
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
    
    return {
        "status": "debug-info",
        "api_flow": [
            "1. Authenticatie naar /auth/token (scope=all)",
            "2. Haal ALLE gebruikers op via /Users met paginering (50 per pagina)",
            "3. ZOEK DANIEL BERLO IN DE LIJST",
            "4. FILTER OP BASIS VAN ZIJN CLIENT/SITE ID"
        ],
        "halo_notes": [
            "1. Eerst ALLE gebruikers ophalen, DAN filteren",
            "2. Gebruikt dynamische groepidentificatie via Daniel Berlo",
            "3. Ondersteunt meerdere varianten van Daniel Berlo's email/naam"
        ],
        "current_counts": {
            "total_users_found": len(main_users),
            "expected_users": "Alle gebruikers uit dezelfde groep als Daniel Berlo"
        },
        "safety_mechanisms": [
            "• Maximaal 100 pagina's om oneindige lus te voorkomen",
            "• 0.3s delay tussen aanvragen om rate limiting te voorkomen",
            "• 3 opeenvolgende lege pagina's stoppen de lus",
            "• Herkansingen bij tijdelijke netwerkfouten",
            "• Fallback op client/site namen als ID's ontbreken"
        ],
        "berlo_email_variants": [
            "danja.berlo@bnc.nl",
            "danja.berlo@bnc",
            "daniel.berlo@bnc.nl",
            "d.berlo@bnc.nl",
            "berlo@bnc.nl"
        ],
        "berlo_name_variants": [
            "danja berlo",
            "daniel berlo",
            "berlo",
            "danja"
        ]
    }

# ------------------------------------------------------------------------------
# App Start
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - CORRECTE GROEPFILTERING")
    log.info("-"*70)
    log.info("✅ EERST ALLE gebruikers ophalen")
    log.info("✅ DAN ZOEKEN naar Daniel Berlo")
    log.info("✅ TENSLUITEN FILTEREN op basis van ZIJN groep")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Controleer of Daniel Berlo wordt GEVONDEN in logs")
    log.info("3. Bezoek /users voor de correcte gebruikerslijst")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port, debug=True)
