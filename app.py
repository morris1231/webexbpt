import os, urllib.parse, logging, sys
from flask import Flask, jsonify
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET DEBUGGING VOOR HALO API
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - VOLLEDIG AANPASSEN VOOR JOUW OMGEVING
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials (NIET AANPASSEN - dit komt uit .env)
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# UAT OMGEVING (NIET AANPASSEN - dit is correct voor jou)
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# JOUW SPECIFIEKE ID'S (CONTROLEER DEZE!)
HALO_CLIENT_ID_NUM = 12  # Bossers & Cnossen (controleer in Halo: Clients > ID kolom)
HALO_SITE_ID       = 18  # Main (controleer in Halo: Sites > ID kolom)

# Controleer of .env bestaat
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - CORRECTE IMPLEMENTATIE VOOR UAT
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Authenticatie met ALLE benodigde scopes"""
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"  # Cruciaal voor client/site data
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
    """HAAL ALLE GEBRUIKERS OP MET CORRECTE KOPPELINGEN"""
    log.info("🔍 Start volledige gebruikersophaal met Halo UAT API")
    try:
        headers = get_halo_headers()
        all_users = []
        page = 1
        total_users = 0

        while True:
            # CORRECTE API AANROEP MET PAGINERING + INCLUDES
            params = {
                "page": page,
                "pageSize": 100,  # Maximaal toegestaan
                "include": "client,site"  # Cruciaal voor koppelingen
            }
            
            log.info(f"➡️ Ophalen pagina {page} met parameters: {params}")
            r = requests.get(
                f"{HALO_API_BASE}/User",  # LET OP: Enkelvoud (User i.p.v. Users)
                headers=headers,
                params=params,
                timeout=30
            )
            
            if r.status_code != 200:
                log.error(f"❌ API FOUT ({r.status_code}): {r.text}")
                break
                
            data = r.json()
            
            # HALO SPECIFIEK: Gebruikers zitten in 'users' array
            users_page = data.get("users", [])
            
            if not users_page:
                log.warning("⚠️ Geen gebruikers gevonden op deze pagina")
                break
                
            all_users.extend(users_page)
            total_users += len(users_page)
            log.info(f"✅ Pagina {page}: {len(users_page)} gebruikers ontvangen (totaal: {total_users})")
            
            # Stop als we de laatste pagina hebben
            if len(users_page) < 100:
                break
                
            page += 1

        log.info(f"🎉 VOLLEDIGE OPHAAL GEREED: {total_users} gebruikers ontvangen")

        # FILTER LOGICA - MET CORRECTE KOPPELINGEN
        main_users = []
        for user in all_users:
            # 1. CONTROLEER CLIENT KOPPELING (via include=client)
            client_match = False
            if "client" in user and isinstance(user["client"], dict):
                try:
                    client_id = int(user["client"].get("id", 0))
                    if client_id == HALO_CLIENT_ID_NUM:
                        client_match = True
                except (TypeError, ValueError):
                    pass

            # 2. CONTROLEER SITE KOPPELING (via include=site)
            site_match = False
            if "site" in user and isinstance(user["site"], dict):
                try:
                    site_id = int(user["site"].get("id", 0))
                    if site_id == HALO_SITE_ID:
                        site_match = True
                except (TypeError, ValueError):
                    pass

            if client_match and site_match:
                main_users.append({
                    "id": user.get("id"),
                    "name": user.get("name") or "Onbekend",
                    "email": user.get("emailaddress") or user.get("email") or "Geen email",
                    "client_name": user["client"].get("name", "Onbekend") if "client" in user else "N/A",
                    "site_name": user["site"].get("name", "Onbekend") if "site" in user else "N/A",
                    "debug": {
                        "raw_client_id": user["client"].get("id") if "client" in user else None,
                        "raw_site_id": user["site"].get("id") if "site" in user else None
                    }
                })

        log.info(f"✅ FILTERRESULTAAT: {len(main_users)}/{total_users} Main-site gebruikers gevonden")
        return main_users

    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - MET REAL-TIME DEBUGGING
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main-site gebruikers API (UAT) - Bezoek /users voor data",
        "environment": "UAT",
        "client_id": HALO_CLIENT_ID_NUM,
        "site_id": HALO_SITE_ID
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLEEN de Main-site gebruikers"""
    main_users = fetch_all_users()
    
    if not main_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                "1. Controleer of HALO_CLIENT_ID_NUM=12 en HALO_SITE_ID=18 correct zijn",
                "2. Zorg dat in Halo: API-toegang > 'Teams' is aangevinkt",
                "3. Bezoek /debug voor technische details"
            ],
            "raw_data_sample": "Bezoek /debug voor API-response voorbeeld"
        }), 500
    
    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "client_name": "Bossers & Cnossen",
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
        "total_users": len(main_users),
        "users": main_users
    })

@app.route("/debug", methods=["GET"])
def debug():
    """Technische debug informatie voor probleemoplossing"""
    try:
        # Haal 1 gebruiker op voor debugging
        headers = get_halo_headers()
        r = requests.get(
            f"{HALO_API_BASE}/User?page=1&pageSize=1",
            headers=headers,
            params={"include": "client,site"},
            timeout=10
        )
        
        sample = r.json().get("users", [{}])[0] if r.status_code == 200 else {}
        
        return jsonify({
            "status": "debug_info",
            "api_call_example": {
                "url": f"{HALO_API_BASE}/User?page=1&pageSize=1&include=client,site",
                "headers": {"Authorization": "Bearer [token]"}
            },
            "sample_user_structure": {
                "id": sample.get("id"),
                "name": sample.get("name"),
                "client": sample.get("client", "NIET GEVONDEN - controleer 'include'"),
                "site": sample.get("site", "NIET GEVONDEN - controleer 'include'")
            },
            "troubleshooting": [
                "1. Als 'client' of 'site' NIET GEVONDEN is: scope 'all' ontbreekt in API-toegang",
                "2. Geen gebruikers? Controleer of client_id=12 en site_id=18 correct zijn",
                "3. 401 error? Controleer HALO_CLIENT_ID/HALO_CLIENT_SECRET in .env"
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)})

# ------------------------------------------------------------------------------
# Render.com Deployment - KLAAR VOOR DIRECTE DEPLOY
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO UAT USERS API - VOLLEDIG GEAUTOMATISEERD")
    log.info("-"*70)
    log.info("✅ Werkt met echte UAT omgeving (bncuat.halopsa.com)")
    log.info("✅ Ondersteunt client/site koppelingen via 'include' parameter")
    log.info("✅ Paginering voor 1000+ gebruikers")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN:")
    log.info("1. Maak .env bestand met HALO_CLIENT_ID en HALO_CLIENT_SECRET")
    log.info("2. Deploy direct naar Render.com")
    log.info("3. Bezoek /debug voor configuratiecheck")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
