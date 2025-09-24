import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - Nu met REAL-TIME STRUCTUURANALYSE
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - GEEN RUIMTE VOOR FOUTEN
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# ✅ FORCEER correcte AUTH URL (GEEN discussie)
HALO_AUTH_URL      = "https://bncuat.halopsa.com/oauth2/token"
HALO_API_BASE      = os.getenv("HALO_API_BASE", "https://bncuat.halopsa.com/api").strip()

# Jouw IDs
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))   # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))         # Main site

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAAL: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - MET REAL-TIME DEBUGGING
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Authenticatie met geforceerde URL"""
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
        log.critical("👉 OPLOSSING:")
        log.critical("1. GA NAAR: Instellingen → API-toegang")
        log.critical("2. VINK 'Teams' EXPLICIET AAN (niet alleen 'Algemeen')")
        log.critical("3. DRUK OP 'OPSLAAN'")
        log.critical("4. HERSTART DE APP VOLLEDIG")
        raise

def fetch_main_users(client_id: int, site_id: int):
    """HAAL GEBRUIKERS OP MET JUISTE NESTED FILTERING"""
    log.info(f"🔍 Start proces voor client {client_id}, site {site_id}")
    
    try:
        # Stap 1: Haal ALLE gebruikers op
        users_url = f"{HALO_API_BASE}/Users"
        log.info(f"➡️ API-aanvraag: {users_url}")
        
        headers = get_halo_headers()
        r = requests.get(users_url, headers=headers, timeout=30)
        r.raise_for_status()
        
        # Parse response
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or data.get("Users", [])
        log.info(f"✅ {len(users)} gebruikers opgehaald - start filtering")
        
        # Stap 2: Analyseer EERSTE gebruiker voor structuur
        if users:
            first_user = users[0]
            log.info("🔍 STRUCTUUR ANALYSE - Eerste gebruiker:")
            
            # Toon alle relevante velden
            site_fields = [k for k in first_user.keys() if "site" in k.lower()]
            client_fields = [k for k in first_user.keys() if "client" in k.lower()]
            
            log.info(f"  → Mogelijke site-velden: {site_fields}")
            log.info(f"  → Mogelijke client-velden: {client_fields}")
            
            # Toon waarden voor debugging
            for field in site_fields + client_fields:
                value = first_user.get(field)
                log.info(f"    - {field}: {value} ({type(value).__name__})")
        
        # Stap 3: Filter MET NESTED OBJECTEN (de echte oplossing)
        main_users = []
        for u in users:
            # Check voor directe site_id velden
            site_id_val = str(
                u.get("site_id") or 
                u.get("SiteId") or 
                u.get("siteId") or 
                ""
            ).strip()
            
            # Check voor NESTED site object
            if not site_id_val and "site" in u and isinstance(u["site"], dict):
                site_id_val = str(u["site"].get("id", "")).strip()
            
            # Check voor directe client_id velden
            client_id_val = str(
                u.get("client_id") or 
                u.get("ClientId") or 
                u.get("clientId") or 
                ""
            ).strip()
            
            # Check voor NESTED client object
            if not client_id_val and "client" in u and isinstance(u["client"], dict):
                client_id_val = str(u["client"].get("id", "")).strip()
            
            # Valideer of dit een Main-site gebruiker is
            if site_id_val == str(site_id) and client_id_val == str(client_id):
                main_users.append(u)
        
        # Rapporteer resultaat
        if main_users:
            log.info(f"✅ {len(main_users)} JUISTE Main-site gebruikers gevonden!")
            if users:
                example = main_users[0]
                log.info(f"  → Voorbeeldgebruiker: ID={example.get('id')}, Naam='{example.get('name')}'")
                log.info(f"    Site: {example.get('site', {}).get('id')}, Client: {example.get('client', {}).get('id')}")
        else:
            log.error("❌ Geen Main-site gebruikers gevonden - STRUCTUUR KLOPT NIET")
            log.error("👉 OPLOSSING:")
            log.error("1. Bezoek /debug-structure om de echte API structuur te zien")
            log.error("2. Pas de filtering aan op basis van ECHTE veldnamen")
        
        return main_users
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - MET LIVE STRUCTUUR DEBUGGING
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "debug_routes": [
            "/debug - Basis configuratie",
            "/debug-structure - Echte API structuur",
            "/debug-api - Raw API response"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    
    if not site_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "critical_steps": [
                "1. GA NAAR: Halo PSA → Instellingen → API-toegang",
                "2. ZOEK JOUW API KEY EN KLIK BEWERKEN",
                "3. VINK EXPLICIET 'Teams' AAN (niet alleen 'Algemeen')",
                "4. DRUK OP 'OPSLAAN'",
                "5. HERSTART DE APP VOLLEDIG"
            ],
            "next_steps": [
                "Bezoek /debug-structure om te zien hoe jouw API data eruit ziet",
                "Kijk naar 'site' en 'client' velden in de logs"
            ]
        }), 500
    
    simplified = [{
        "id": u.get("id"),
        "name": u.get("name") or "Onbekend",
        "email": u.get("EmailAddress") or u.get("email") or "Geen email"
    } for u in site_users]
    
    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "site_id": HALO_SITE_ID,
        "total_users": len(site_users),
        "users": simplified
    })

@app.route("/debug", methods=["GET"])
def debug():
    """Basis debug informatie"""
    return {
        "status": "debug-info",
        "config": {
            "halo_auth_url": HALO_AUTH_URL,
            "halo_api_base": HALO_API_BASE,
            "client_id": HALO_CLIENT_ID_NUM,
            "site_id": HALO_SITE_ID
        },
        "critical_notes": [
            "1. HALO_AUTH_URL MOET ZIJN: /oauth2/token (GEEN /auth/token!)",
            "2. 'Teams' MOET EXPLICIET AANGEVINKT ZIJN IN API-TOEGANG",
            "3. Gebruik NIET /Sites/18/Users - dit endpoint bestaat NIET"
        ],
        "api_flow": [
            "1. Authenticatie naar /oauth2/token",
            "2. Haal ALLE gebruikers op via /Users",
            "3. Filter LOKAAL op site/client objecten"
        ]
    }

@app.route("/debug-structure", methods=["GET"])
def debug_structure():
    """Toon de ECHTE structuur van gebruikersdata"""
    try:
        headers = get_halo_headers()
        r = requests.get(f"{HALO_API_BASE}/Users", headers=headers, timeout=30)
        r.raise_for_status()
        
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or []
        
        if not users:
            return {"error": "Geen gebruikers gevonden in API response"}, 500
        
        # Analyseer de EERSTE gebruiker
        sample = users[0]
        structure = {
            "total_users": len(users),
            "sample_user_id": sample.get("id"),
            "sample_user_name": sample.get("name"),
            "site_fields": {},
            "client_fields": {}
        }
        
        # Verzamel site-gerelateerde velden
        for key in sample.keys():
            if "site" in key.lower():
                structure["site_fields"][key] = {
                    "value": sample[key],
                    "type": type(sample[key]).__name__
                }
        
        # Verzamel client-gerelateerde velden
        for key in sample.keys():
            if "client" in key.lower():
                structure["client_fields"][key] = {
                    "value": sample[key],
                    "type": type(sample[key]).__name__
                }
        
        # Controleer op geneste objecten
        if "site" in sample and isinstance(sample["site"], dict):
            structure["site_object"] = {
                "id": sample["site"].get("id"),
                "name": sample["site"].get("name")
            }
        
        if "client" in sample and isinstance(sample["client"], dict):
            structure["client_object"] = {
                "id": sample["client"].get("id"),
                "name": sample["client"].get("name")
            }
        
        return {
            "status": "success",
            "message": "Dit is de ECHTE structuur van jouw API response",
            "data": structure,
            "note": "Gebruik deze veldnamen in je filtering"
        }
    
    except Exception as e:
        return {"error": str(e)}, 500

# ------------------------------------------------------------------------------
# App Start - MET FORCEERDE FIXES
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Forceer correcte auth URL (geen discussie)
    os.environ["HALO_AUTH_URL"] = "https://bncuat.halopsa.com/oauth2/token"
    
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS FIXER - DEFINTIEVE OPLOSSING")
    log.info("-"*70)
    log.info("🔥 BELANGRIJK: Deze code werkt ALLEEN als:")
    log.info("1. Je 'Teams' hebt aangevinkt in API-toegang")
    log.info("2. Je de app VOLLEDIG herstart na API-wijzigingen")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN ALS HET NOG NIET WERKT:")
    log.info("1. GA NAAR: Instellingen → API-toegang")
    log.info("2. KLIK OP JOUW API KEY → BEWERKEN")
    log.info("3. VINK EXPLICIET 'Teams' AAN (niet alleen 'Algemeen')")
    log.info("4. DRUK OP 'OPSLAAN'")
    log.info("5. SLUIT DE APP VOLLEDIG AF")
    log.info("6. HERSTART DE APP")
    log.info("7. BEZOEK EERST /debug-structure")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
