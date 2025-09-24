import os, urllib.parse, logging, sys, io, csv, time
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET JUISTE PAGINERING EN FILTERING
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - MET JUISTE PAGINERING EN FILTERING
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# Correcte URL voor UAT
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# Jouw correcte IDs (ZOALS IN DE URL)
HALO_CLIENT_ID_NUM = 12  # Bossers & Cnossen (URL ID)
HALO_SITE_ID       = 18  # Main (URL ID)

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - MET JUISTE PAGINERING EN FILTERING
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Authenticatie met alleen 'Teams' rechten"""
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
    """HAAL ALLE GEBRUIKERS OP MET JUISTE PAGINERING EN FILTERING"""
    log.info("🔍 Haal ALLE gebruikers op met correcte paginering")
    all_users = []
    page = 1
    max_pages = 100  # Veilige limiet om oneindige lus te voorkomen
    consecutive_empty = 0  # Houdt lege pagina's bij
    
    try:
        while page <= max_pages:
            # CORRECTE PAGINERING VOOR JOUW OMGEVING
            users_url = f"{HALO_API_BASE}/Users?page={page}&pageSize=50"
            log.info(f"➡️ API-aanvraag (pagina {page}): {users_url}")
            
            try:
                headers = get_halo_headers()
                r = requests.get(users_url, headers=headers, timeout=30)
                
                if r.status_code != 200:
                    log.error(f"❌ API FOUT ({r.status_code}): {r.text}")
                    # Probeer opnieuw bij tijdelijke fouten
                    if r.status_code in [429, 500, 502, 503, 504]:
                        time.sleep(2)
                        continue
                    break
                    
                # Parse response
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
                
                # Controleer op lege response
                if not users:
                    consecutive_empty += 1
                    log.warning(f"⚠️ Lege response (pagina {page}) - {consecutive_empty} opeenvolgend")
                    
                    # Stop na 3 lege pagina's
                    if consecutive_empty >= 3:
                        log.info("✅ Stoppen met ophalen na 3 lege pagina's")
                        break
                    page += 1
                    time.sleep(0.5)  # Kleine delay voor API
                    continue
                
                # Reset lege teller bij succesvolle response
                consecutive_empty = 0
                
                # Voeg gebruikers toe aan de complete lijst
                all_users.extend(users)
                log.info(f"✅ Pagina {page}: {len(users)} gebruikers opgehaald (totaal: {len(all_users)})")
                
                # Stop als we minder dan 50 gebruikers krijgen OF lege response
                if len(users) < 50:
                    log.info("✅ Laatste pagina bereikt (minder dan 50 gebruikers)")
                    break
                
                page += 1
                time.sleep(0.3)  # Rate limiting delay (cruciaal!)
                
            except requests.exceptions.RequestException as e:
                log.error(f"⚠️ Netwerkfout: {str(e)}")
                time.sleep(2)  # Exponentiële backoff zou beter zijn
                continue
            except Exception as e:
                log.error(f"⚠️ Onverwachte fout: {str(e)}")
                break
        
        log.info(f"✅ Totaal opgehaald: {len(all_users)} gebruikers over {page-1} pagina{'s' if page > 2 else ''}")
        
        # Filter Main-site gebruikers MET JUISTE LOGICA
        main_users = []
        for u in all_users:
            # 1. Eerst probeer ID-koppeling (JOUW OMGEVING GEBRUIKT DIT)
            site_match = False
            client_match = False
            
            # Site ID check (alle varianten)
            for key in ["site_id", "SiteId", "siteId", "siteid", "SiteID", "site_id_int"]:
                if key in u and u[key] is not None:
                    try:
                        if float(u[key]) == float(HALO_SITE_ID):
                            site_match = True
                            break
                    except (TypeError, ValueError):
                        pass
            
            # Client ID check (alle varianten)
            for key in ["client_id", "ClientId", "clientId", "clientid", "ClientID", "client_id_int"]:
                if key in u and u[key] is not None:
                    try:
                        if float(u[key]) == float(HALO_CLIENT_ID_NUM):
                            client_match = True
                            break
                    except (TypeError, ValueError):
                        pass
            
            # 2. Als ID-koppeling faalt, probeer dan NAAM-koppeling
            if not site_match and "site_name" in u:
                site_name = str(u["site_name"]).strip().lower()
                if "main" in site_name or "hoofdkantoor" in site_name:
                    site_match = True
            
            if not client_match and "client_name" in u:
                client_name = str(u["client_name"]).strip().lower()
                if "bossers" in client_name and "cnossen" in client_name:
                    client_match = True
            
            # Bepaal of dit een Main-site gebruiker is
            if site_match and client_match:
                main_users.append(u)
        
        log.info(f"📊 Totaal Main-site gebruikers: {len(main_users)}/{len(all_users)}")
        return main_users
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - MET JUISTE PAGINERING EN FILTERING
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_notes": [
            "1. Werkt MET JUISTE PAGINERING (50 gebruikers per pagina)",
            "2. Gebruikt EERST ID-KOPPELING, dan NAAM-KOPPELING",
            "3. Bezoek /debug voor technische details"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLEEN de Main-site gebruikers MET JUISTE LOGICA"""
    main_users = fetch_all_users()
    if not main_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                "1. Controleer of 'Teams' is aangevinkt in API-toegang",
                "2. Zorg dat de API key 'all' scope heeft",
                "3. Bezoek /debug voor technische details"
            ]
        }), 500
    
    simplified = [{
        "id": u.get("id"),
        "name": u.get("name") or "Onbekend",
        "email": u.get("emailaddress") or u.get("email") or "Geen email"
    } for u in main_users]
    
    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "client_name": "Bossers & Cnossen",
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
        "total_users": len(main_users),
        "users": simplified
    })

@app.route("/debug", methods=["GET"])
def debug():
    """Toon technische details voor debugging"""
    main_users = fetch_all_users()
    return {
        "status": "debug-info",
        "config": {
            "halo_auth_url": HALO_AUTH_URL,
            "halo_api_base": HALO_API_BASE,
            "client_id": HALO_CLIENT_ID_NUM,
            "site_id": HALO_SITE_ID
        },
        "api_flow": [
            "1. Authenticatie naar /auth/token (scope=all)",
            "2. Haal ALLE gebruikers op via /Users met JUISTE paginering (50 per pagina)",
            "3. Filter eerst op ID, dan op NAAM (cruciaal voor jouw omgeving)"
        ],
        "halo_notes": [
            "1. Jouw omgeving gebruikt PRIMAIR ID-KOPPELING (niet alleen naam!)",
            "2. Paginering gebruikt 'pageSize=50' (maximaal toegestaan)",
            "3. Gebruik fallback naar naam-koppeling als ID-koppeling faalt"
        ],
        "current_counts": {
            "total_users_found": len(main_users),
            "expected_users": "135+ (volgens jouw Halo omgeving)"
        },
        "test_curl": (
                f"curl -X GET '{HALO_API_BASE}/Users?page=1&pageSize=50' \\\n"
                "-H 'Authorization: Bearer $(curl -X POST \\\"{HALO_AUTH_URL}\\\" \\\n"
                "-d \\\"grant_type=client_credentials&client_id={HALO_CLIENT_ID}&client_secret=******&scope=all\\\" \\\n"
                "| jq -r '.access_token')'"
            ),
        "safety_mechanisms": [
            "• Maximaal 100 pagina's om oneindige lus te voorkomen",
            "• 0.3s delay tussen aanvragen om rate limiting te voorkomen",
            "• 3 opeenvolgende lege pagina's stoppen de lus",
            "• Herkansingen bij tijdelijke netwerkfouten"
        ]
    }

# ------------------------------------------------------------------------------
# App Start - MET JUISTE PAGINERING EN FILTERING
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - MET JUISTE PAGINERING EN FILTERING")
    log.info("-"*70)
    log.info("✅ Haalt ALLE gebruikers op via JUISTE paginering (50 per pagina)")
    log.info("✅ Gebruikt EERST ID-KOPPELING, dan NAAM-KOPPELING (cruciaal voor jouw omgeving)")
    log.info("✅ Werkt met jouw specifieke Halo UAT omgeving")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Bezoek DAN /users voor ALLE Main-site gebruikers")
    log.info("3. Gebruik de curl command in /debug voor API testen")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port, debug=True)
