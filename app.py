import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET JUISTE PAGINERING (50 per pagina)
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
# Halo API helpers - MET JUISTE PAGINERING (50 per pagina)
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
    """HAAL ALLE GEBRUIKERS OP MET JUISTE PAGINERING (50 per pagina)"""
    log.info("🔍 Haal ALLE gebruikers op met correcte paginering (50 per pagina)")
    
    all_users = []
    page = 1
    total_records = 0
    pages_fetched = 0
    
    try:
        while True:
            # JUISTE PAGINERING VOOR JOUW OMGEVING (50 per pagina)
            users_url = f"{HALO_API_BASE}/Users?page={page}&pageSize=50"
            log.info(f"➡️ API-aanvraag (pagina {page}): {users_url}")
            
            headers = get_halo_headers()
            r = requests.get(users_url, headers=headers, timeout=30)
            
            if r.status_code != 200:
                log.error(f"❌ API FOUT ({r.status_code}): {r.text}")
                break
            
            # Parse response
            data = r.json()
            log.info(f"🔍 RESPONSE STRUCTUUR: {type(data).__name__}")
            
            # Verwerk 'data' wrapper
            if "data" in data and isinstance(data["data"], dict):
                log.info("✅ Response heeft 'data' wrapper")
                users_data = data["data"]
            else:
                users_data = data
            
            # Haal de users lijst op
            users = users_data.get("users", [])
            if not users:
                users = users_data.get("Users", [])
            
            if not users:
                log.warning("⚠️ Geen gebruikers gevonden in API response")
                break
            
            # Voeg gebruikers toe aan de complete lijst
            all_users.extend(users)
            pages_fetched += 1
            
            # Bepaal totalen
            if "record_count" in users_data:
                total_records = users_data["record_count"]
            elif "total" in users_data:
                total_records = users_data["total"]
            elif "Total" in users_data:
                total_records = users_data["Total"]
            else:
                # Probeer de eerste pagina om het totaal aantal te bepalen
                if page == 1:
                    # Haal de eerste pagina op zonder paginering om het totaal aantal te zien
                    first_page_url = f"{HALO_API_BASE}/Users"
                    r_first = requests.get(first_page_url, headers=headers, timeout=30)
                    
                    if r_first.status_code == 200:
                        first_data = r_first.json()
                        if "data" in first_data and isinstance(first_data["data"], dict):
                            total_records = first_data["data"].get("record_count", len(all_users))
                        else:
                            total_records = first_data.get("record_count", len(all_users))
            
            log.info(f"✅ Pagina {page}: {len(users)} gebruikers opgehaald (totaal: {len(all_users)}/{total_records})")
            
            # Stop als we alle pagina's hebben
            if total_records <= len(all_users) or len(users) < 50:
                break
            
            page += 1
        
        log.info(f"✅ Totaal opgehaald: {len(all_users)} gebruikers over {pages_fetched} pagina{'s' if pages_fetched > 1 else ''}")
        
        # Filter Main-site gebruikers MET NAAMGEBASEERDE MATCHING
        main_users = []
        for u in all_users:
            # 1. Naamgebaseerde matching (JOUW OMGEVING GEBRUIKT DIT)
            site_match = False
            client_match = False
            
            # Site naam check (case-insensitive)
            site_name = str(u.get("site_name", "")).strip().lower()
            if site_name == "main" or site_name == "hoofdkantoor":
                site_match = True
            
            # Client naam check (case-insensitive, met variaties)
            client_name = str(u.get("client_name", "")).strip().lower()
            if "bossers" in client_name and "cnossen" in client_name:
                client_match = True
            
            # 2. Integer ID koppeling (als fallback)
            if not site_match:
                for key in ["site_id", "SiteId", "siteId", "siteid", "SiteID"]:
                    if key in u and u[key] is not None:
                        try:
                            if float(u[key]) == float(HALO_SITE_ID):
                                site_match = True
                                break
                        except (TypeError, ValueError):
                            pass
            
            if not client_match:
                for key in ["client_id", "ClientId", "clientId", "clientid", "ClientID"]:
                    if key in u and u[key] is not None:
                        try:
                            if float(u[key]) == float(HALO_CLIENT_ID_NUM):
                                client_match = True
                                break
                        except (TypeError, ValueError):
                            pass
            
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
            "2. Gebruikt NAAMGEBASEERDE MATCHING (cruciaal voor jouw omgeving)",
            "3. Bezoek /debug voor technische details"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLEEN de Main-site gebruikers MET NAAMGEBASEERDE MATCHING"""
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
            "3. Filter op NAAM (cruciaal voor jouw omgeving)"
        ],
        "halo_notes": [
            "1. Jouw omgeving gebruikt NAAMGEBASEERDE koppeling (niet ID koppeling!)",
            "2. Paginering gebruikt 'pageSize=50' (maximaal toegestaan)",
            "3. Gebruik case-insensitive matching voor namen"
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
            )
    }

# ------------------------------------------------------------------------------
# App Start - MET JUISTE PAGINERING EN FILTERING
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - MET JUISTE PAGINERING (50 per pagina)")
    log.info("-"*70)
    log.info("✅ Haalt ALLE gebruikers op via JUISTE paginering (50 per pagina)")
    log.info("✅ Gebruikt NAAMGEBASEERDE MATCHING (cruciaal voor jouw omgeving)")
    log.info("✅ Werkt met jouw specifieke Halo UAT omgeving")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Bezoek DAN /users voor ALLE Main-site gebruikers")
    log.info("3. Gebruik de curl command in /debug voor API testen")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
