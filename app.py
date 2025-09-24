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

# Jouw correcte IDs (als fallback)
HALO_CLIENT_ID_NUM = 12  # Bossers & Cnossen (URL ID)
HALO_SITE_ID       = 18  # Main (URL ID)

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
    """HAAL ALLE GEBRUIKERS OP MET DYNAMISCHE GROEPFILTERING OP BASIS VAN DANIEL BERLO"""
    log.info("🔍 Start met het ophalen van alle gebruikers met dynamische groepfiltering")
    all_users = []
    page = 1
    max_pages = 100
    consecutive_empty = 0
    danja_user = None
    dynamic_site_id = None
    dynamic_client_id = None

    try:
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
                
                if len(users) < 50:
                    log.info("✅ Laatste pagina bereikt (minder dan 50 gebruikers)")
                    break
                
                page += 1
                time.sleep(0.3)
                
            except Exception as e:
                log.error(f"⚠️ Fout bij ophalen pagina {page}: {str(e)}")
                break

        log.info(f"✅ Totaal opgehaald: {len(all_users)} gebruikers")

        # Stap 2: Zoek Daniel Berlo om de juiste groep te identificeren
        log.info("🔍 Zoeken naar Daniel Berlo om de juiste groep te identificeren...")
        berlo_email = "danja.berlo@bnc.nl"
        for u in all_users:
            email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
            name = str(u.get("name", "")).strip().lower()
            
            # Check op Daniel Berlo (case-insensitive en domein check)
            if berlo_email in email or ("berlo" in name and "bnc" in email):
                danja_user = u
                log.info(f"✅ GEVONDEN: Daniel Berlo - ID: {u.get('id')}, Email: {email}")
                break

        # Stap 3: Bepaal de juiste groep ID's op basis van Daniel Berlo
        if danja_user:
            # Haal site_id op uit Daniel Berlo's record
            site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
            for key in site_id_keys:
                if key in danja_user and danja_user[key] is not None:
                    try:
                        dynamic_site_id = str(danja_user[key]).strip()
                        log.info(f"✅ Gebruik site_id van Daniel Berlo: {dynamic_site_id} (gevonden via '{key}')")
                        break
                    except:
                        continue
            
            # Haal client_id op uit Daniel Berlo's record
            client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
            for key in client_id_keys:
                if key in danja_user and danja_user[key] is not None:
                    try:
                        dynamic_client_id = str(danja_user[key]).strip()
                        log.info(f"✅ Gebruik client_id van Daniel Berlo: {dynamic_client_id} (gevonden via '{key}')")
                        break
                    except:
                        continue
            
            # Valideer of we bruikbare ID's hebben gevonden
            if not dynamic_site_id or not dynamic_client_id:
                log.warning("⚠️ Kon geen volledige groepinformatie vinden in Daniel Berlo's record")
                log.warning("➡️ Gebruik fallback naar hardcoded waarden (mogelijk niet de juiste gebruikers)")
                dynamic_site_id = str(HALO_SITE_ID)
                dynamic_client_id = str(HALO_CLIENT_ID_NUM)
        else:
            log.error("❌ FATAAL: Daniel Berlo niet gevonden in gebruikerslijst!")
            log.error("➡️ Zorg dat:")
            log.error("   1. De API key toegang heeft tot alle gebruikers")
            log.error("   2. Daniel Berlo correct is ingesteld in Halo")
            log.error("➡️ Gebruik hardcoded waarden als noodoplossing (risico op verkeerde gebruikers)")
            dynamic_site_id = str(HALO_SITE_ID)
            dynamic_client_id = str(HALO_CLIENT_ID_NUM)

        # Stap 4: Filter alle gebruikers op basis van de dynamisch gevonden groep
        log.info(f"🔍 Filter gebruikers op site_id={dynamic_site_id} en client_id={dynamic_client_id}")
        main_users = []
        for u in all_users:
            # Site ID check
            site_match = False
            for key in ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]:
                if key in u and u[key] is not None:
                    try:
                        if str(u[key]).strip() == dynamic_site_id:
                            site_match = True
                            break
                    except:
                        pass
            
            # Client ID check
            client_match = False
            for key in ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]:
                if key in u and u[key] is not None:
                    try:
                        if str(u[key]).strip() == dynamic_client_id:
                            client_match = True
                            break
                    except:
                        pass
            
            # Site naam check als fallback
            if not site_match and "site_name" in u:
                site_name = str(u["site_name"]).strip().lower()
                if "main" in site_name or "hoofd" in site_name:
                    site_match = True
            
            # Client naam check als fallback
            if not client_match and "client_name" in u:
                client_name = str(u["client_name"]).strip().lower()
                if "bossers" in client_name and "cnossen" in client_name:
                    client_match = True
            
            # Email domein check (cruciaal voor BNC)
            email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
            email_match = "bnc.nl" in email or "bossers" in email or "cnossen" in email
            
            # Bepaal of dit een Main-site gebruiker is
            if (site_match and client_match) or (email_match and (site_match or client_match)):
                main_users.append(u)

        # Stap 5: Extra controle - zorg dat Daniel Berlo in de resultaten zit
        berlo_found = False
        for u in main_users:
            email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
            if "danja.berlo@bnc.nl" in email:
                berlo_found = True
                break
        
        if not berlo_found:
            log.warning("⚠️ WAARSCHUWING: Daniel Berlo niet gevonden in gefilterde resultaten!")
            log.warning("➡️ Mogelijke oorzaken:")
            log.warning("   1. Verkeerde site/client ID's gebruikt")
            log.warning("   2. API geeft geen volledige gebruikersdata terug")
            log.warning("   3. Daniel Berlo heeft een andere email in Halo")
        else:
            log.info("✅ BEVESTIGING: Daniel Berlo zit in de gefilterde resultaten")

        log.info(f"📊 Totaal Main-site gebruikers: {len(main_users)}/{len(all_users)}")
        return main_users
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_notes": [
            "1. Werkt MET DYNAMISCHE GROEPFILTERING (gebaseerd op Daniel Berlo)",
            "2. Gebruikt EERST ID-KOPPELING, dan NAAM-KOPPELING",
            "3. Bezoek /debug voor technische details"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLEEN de Main-site gebruikers MET DYNAMISCHE FILTERING"""
    main_users = fetch_all_users()
    if not main_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                "1. Controleer of 'Teams' is aangevinkt in API-toegang",
                "2. Zorg dat Daniel Berlo@bnc.nl bestaat in Halo",
                "3. Bezoek /debug voor technische details"
            ]
        }), 500
    
    simplified = [{
        "id": u.get("id"),
        "name": u.get("name") or "Onbekend",
        "email": u.get("emailaddress") or u.get("email") or "Geen email"
    } for u in main_users]
    
    return jsonify({
        "client_id": dynamic_client_id if 'dynamic_client_id' in locals() else HALO_CLIENT_ID_NUM,
        "client_name": "Bossers & Cnossen",
        "site_id": dynamic_site_id if 'dynamic_site_id' in locals() else HALO_SITE_ID,
        "site_name": "Main",
        "total_users": len(main_users),
        "users": simplified
    })

@app.route("/debug", methods=["GET"])
def debug():
    """Toon technische details voor debugging"""
    main_users = fetch_all_users()
    
    # Bepaal dynamische waarden voor debug info
    site_id = "N/A"
    client_id = "N/A"
    if 'dynamic_site_id' in globals():
        site_id = dynamic_site_id
    if 'dynamic_client_id' in globals():
        client_id = dynamic_client_id
    
    return {
        "status": "debug-info",
        "config": {
            "halo_auth_url": HALO_AUTH_URL,
            "halo_api_base": HALO_API_BASE,
            "configured_client_id": HALO_CLIENT_ID_NUM,
            "configured_site_id": HALO_SITE_ID,
            "used_client_id": client_id,
            "used_site_id": site_id
        },
        "api_flow": [
            "1. Authenticatie naar /auth/token (scope=all)",
            "2. Haal ALLE gebruikers op via /Users met paginering (50 per pagina)",
            "3. IDENTIFICEER GROEP VIA DANIEL BERLO",
            "4. Filter gebruikers op basis van gevonden groep"
        ],
        "halo_notes": [
            "1. Werkt met dynamische groepidentificatie (geen hardcoded waarden)",
            "2. Paginering gebruikt 'pageSize=50' (maximaal toegestaan)",
            "3. Controleert expliciet op Daniel Berlo@bnc.nl"
        ],
        "current_counts": {
            "total_users_found": len(main_users),
            "expected_users": "Alle gebruikers van Daniel Berlo's groep"
        },
        "safety_mechanisms": [
            "• Maximaal 100 pagina's om oneindige lus te voorkomen",
            "• 0.3s delay tussen aanvragen om rate limiting te voorkomen",
            "• 3 opeenvolgende lege pagina's stoppen de lus",
            "• Herkansingen bij tijdelijke netwerkfouten",
            "• Fallback naar hardcoded waarden als Daniel Berlo niet wordt gevonden"
        ],
        "test_curl": (
                f"curl -X GET '{HALO_API_BASE}/Users?page=1&pageSize=50' \\\n"
                "-H 'Authorization: Bearer $(curl -X POST \\\"{HALO_AUTH_URL}\\\" \\\n"
                "-d \\\"grant_type=client_credentials&client_id={HALO_CLIENT_ID}&client_secret=******&scope=all\\\" \\\n"
                "| jq -r '.access_token')'"
            )
    }

# ------------------------------------------------------------------------------
# App Start
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - DYNAMISCHE GROEPFILTERING")
    log.info("-"*70)
    log.info("✅ Identificeert groep automatisch via Daniel Berlo@bnc.nl")
    log.info("✅ Gebruikt dynamische ID's i.p.v. hardcoded waarden")
    log.info("✅ Werkt met jouw specifieke Halo UAT omgeving")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Controleer of Daniel Berlo wordt GEVONDEN in logs")
    log.info("3. Bezoek /users voor de correcte gebruikerslijst")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port, debug=True)
