import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET JUISTE URL VALIDATIE
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - VOLLEDIG AFGESTEMD OP JOUW UAT
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# ✅ DE ENIGE CORRECTE URL VOOR JOUW UAT OMGEVING
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"  # GEEN /oauth2/token!
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# Jouw IDs (kan in .env of hardcoded)
HALO_CLIENT_ID_NUM = 12
HALO_SITE_ID       = 18

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    log.critical("👉 Voorbeeld .env:")
    log.critical("HALO_CLIENT_ID=jouw_id")
    log.critical("HALO_CLIENT_SECRET=jouw_secret")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - MET UAT SPECIFIEKE AUTH
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Authenticatie MET DE ENIGE WERKENDE SCOPE VOOR UAT"""
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"  # ✅ ENIGE geldige scope voor UAT
    }
    
    log.info(f"🔐 Authenticatie aanvraag naar: {HALO_AUTH_URL}")
    log.info("💡 Belangrijk: Gebruikt specifieke UAT endpoint /auth/token (GEEN /oauth2/token!)")
    
    try:
        r = requests.post(
            HALO_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(payload),
            timeout=10
        )
        
        if r.status_code != 200:
            log.error(f"❌ AUTH MISLUKT ({r.status_code}): {r.text}")
            log.error("👉 PROBEER DEZE CURL COMMAND IN TERMINAL:")
            log.error(f"curl -X POST '{HALO_AUTH_URL}' \\")
            log.error(f"-d 'grant_type=client_credentials&client_id={HALO_CLIENT_ID}&client_secret=******&scope=all'")
            raise Exception("Authenticatie mislukt - controleer logs voor curl command")
        
        log.info("✅ Authenticatie GELUKT! Token verkregen.")
        return {
            "Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"
        }
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        log.critical("🚨 OPLOSSING:")
        log.critical("1. Zorg dat 'Teams' is aangevinkt in API-toegang (Instellingen → API-toegang)")
        log.critical("2. Gebruik EXACT deze .env instellingen:")
        log.critical("   HALO_AUTH_URL=https://bncuat.halopsa.com/auth/token")
        log.critical("   scope=all (GEEN all.teams!)")
        raise

def fetch_main_users():
    """HAAL MAIN-SITE GEBRUIKERS OP MET UAT SPECIFIEKE FILTERING"""
    log.info("🔍 Start proces voor Main-site gebruikers")
    
    try:
        # Stap 1: Haal ALLE gebruikers op
        users_url = f"{HALO_API_BASE}/Users"
        log.info(f"➡️ API-aanvraag: {users_url}")
        
        headers = get_halo_headers()
        r = requests.get(users_url, headers=headers, timeout=30)
        
        if r.status_code != 200:
            log.error(f"❌ API FOUT ({r.status_code}): {r.text}")
            log.error("👉 OPLOSSING:")
            log.error("1. GA NAAR: Instellingen → API-toegang")
            log.error("2. VINK 'Teams' EXPLICIET AAN (niet alleen 'Algemeen')")
            log.error("3. DRUK OP 'OPSLAAN'")
            return []
        
        # Parse response
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or data.get("Users", [])
        log.info(f"✅ {len(users)} gebruikers opgehaald - start UAT-specifieke filtering")
        
        # Stap 2: Filter voor UAT specifieke structuur
        main_users = []
        for u in users:
            # Halo UAT gebruikt specifieke veldnamen
            site_id_val = str(
                u.get("siteid") or  # 👈 Let op: GEEN underscore in UAT!
                u.get("site_id") or 
                ""
            ).strip().lower()
            
            client_id_val = str(
                u.get("clientid") or  # 👈 Let op: GEEN underscore in UAT!
                u.get("client_id") or 
                ""
            ).strip().lower()
            
            # Valideer of dit een Main-site gebruiker is
            if site_id_val == "18" and client_id_val == "12":
                main_users.append(u)
        
        # Rapporteer resultaat
        if main_users:
            log.info(f"✅ {len(main_users)} JUISTE Main-site gebruikers gevonden!")
            log.info(f"  → Voorbeeld: {main_users[0].get('name', 'Onbekend')}")
            return main_users
        
        log.error("❌ Geen Main-site gebruikers gevonden - UAT SPECIFIEKE DEBUG")
        log.error("👉 VOLG DEZE STAPPEN:")
        log.error("1. Bezoek /debug-structure voor UAT-specifieke data")
        log.error("2. Let op: UAT gebruikt 'siteid' i.p.v. 'site_id' (GEEN underscore!)")
        
        return []
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - MET UAT SPECIFIEKE DEBUGGING
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "uat_notes": [
            "1. Auth URL MOET ZIJN: /auth/token (GEEN /oauth2/token!)",
            "2. Scope MOET ZIJN: 'all' (GEEN all.teams!)",
            "3. UAT gebruikt 'siteid' i.p.v. 'site_id' (GEEN underscore!)"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    site_users = fetch_main_users()
    
    if not site_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "uat_solution": [
                "1. ZORG DAT: HALO_AUTH_URL=https://bncuat.halopsa.com/auth/token",
                "2. GEBRUIK SCOPE: 'all' (GEEN all.teams!)",
                "3. ONTHOUD: UAT gebruikt 'siteid' i.p.v. 'site_id' (GEEN underscore!)",
                "4. VINK 'Teams' EXPLICIET AAN in API-toegang"
            ],
            "debug_route": "/debug-structure voor UAT-specifieke datastructuur"
        }), 500
    
    simplified = [{
        "id": u.get("id"),
        "name": u.get("name") or "Onbekend",
        "email": u.get("EmailAddress") or u.get("email") or "Geen email"
    } for u in site_users]
    
    return jsonify({
        "client_id": 12,
        "client_name": "Bossers & Cnossen",
        "site_id": 18,
        "site_name": "Main",
        "total_users": len(site_users),
        "users": simplified
    })

@app.route("/debug-structure", methods=["GET"])
def debug_structure():
    """Toon UAT-specifieke datastructuur"""
    try:
        headers = get_halo_headers()
        r = requests.get(f"{HALO_API_BASE}/Users", headers=headers, timeout=30)
        
        if r.status_code != 200:
            return {
                "error": "API fout",
                "status": r.status_code,
                "response": r.text[:500],
                "solution": [
                    "1. Controleer of 'Teams' is aangevinkt in API-toegang",
                    "2. Gebruik HALO_AUTH_URL=https://bncuat.halopsa.com/auth/token"
                ]
            }, 500
        
        # Analyseer de eerste gebruiker
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or []
        
        if not users:
            return {"error": "Lege API response"}, 500
        
        sample = users[0]
        return {
            "status": "success",
            "total_users": len(users),
            "sample_user_id": sample.get("id"),
            "sample_user_name": sample.get("name"),
            "site_fields": {
                "siteid": sample.get("siteid"),
                "site_id": sample.get("site_id"),
                "SiteId": sample.get("SiteId"),
                "siteId": sample.get("siteId")
            },
            "client_fields": {
                "clientid": sample.get("clientid"),
                "client_id": sample.get("client_id"),
                "ClientId": sample.get("ClientId"),
                "clientId": sample.get("clientId")
            },
            "uat_note": "BELANGRIJK: UAT gebruikt velden ZONDER underscore (siteid i.p.v. site_id)!"
        }
    
    except Exception as e:
        return {"error": str(e)}, 500

# ------------------------------------------------------------------------------
# App Start - VOLLEDIG AFGESTEMD OP UAT
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO UAT MAIN USERS FIXER - SPECIFIEK VOOR JOUW OMGEVING")
    log.info("-"*70)
    log.info("✅ DEZE APP IS VOLLEDIG AFGESTEMD OP UAT:")
    log.info("   → Auth URL: /auth/token (GEEN /oauth2/token!)")
    log.info("   → Scope: 'all' (GEEN all.teams!)")
    log.info("   → UAT gebruikt velden ZONDER underscore (siteid i.p.v. site_id)")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN ALS HET NOG NIET WERKT:")
    log.info("1. ZORG DAT: HALO_AUTH_URL=https://bncuat.halopsa.com/auth/token")
    log.info("2. GEBRUIK SCOPE: 'all' (NIET 'all.teams')")
    log.info("3. VINK 'Teams' EXPLICIET AAN in API-toegang")
    log.info("4. HERSTART DE APP VOLLEDIG")
    log.info("5. BEZOEK EERST /debug-structure")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
