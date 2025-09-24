import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - Maximaal duidelijk voor jouw probleem
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - Nu met FORCED correcties voor jouw probleem
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials (VERPLICHT: vul deze in je .env in)
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# ✅ FORCEER de JUISTE AUTH URL (geen discussie mogelijk!)
HALO_AUTH_URL      = "https://bncuat.halopsa.com/oauth2/token"  # GEEN /auth/token!
HALO_API_BASE      = os.getenv("HALO_API_BASE", "https://bncuat.halopsa.com/api").strip()

# Jouw specifieke IDs
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))   # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))         # Main site

# Controleer of .env correct is ingesteld
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAAL: HALO_CLIENT_ID of HALO_CLIENT_SECRET ontbreekt in .env!")
    log.critical("👉 Maak een .env bestand met:")
    log.critical("HALO_CLIENT_ID=jouw_id")
    log.critical("HALO_CLIENT_SECRET=jouw_secret")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - Nu met REAL-TIME DEBUGGING
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Haal token op met de ENIGE werkbare methode"""
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    
    try:
        log.info("🔐 Probeer authenticatie (LET OP: Gebruikt FORCEERDE URL)")
        log.info(f"  → Gebruikte URL: {HALO_AUTH_URL}")
        log.info(f"  → Client ID: {HALO_CLIENT_ID[:5]}{'*' * (len(HALO_CLIENT_ID)-5)}")
        
        r = requests.post(
            HALO_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(payload),
            timeout=10
        )
        
        if r.status_code != 200:
            log.critical(f"❌ AUTH MISLUKT ({r.status_code}): {r.text}")
            log.critical("👉 OPLOSSING:")
            log.critical("1. GA NAAR: Instellingen → API-toegang in Halo")
            log.critical("2. ZORG DAT 'Teams' AANGEVINKT IS")
            log.critical("3. HERSTART DE APP NA WIJZIGINGEN")
            raise Exception("Authenticatie mislukt - zie logs voor details")
        
        token = r.json()["access_token"]
        log.info("✅ Authenticatie GELUKT! Token verkregen.")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        raise

def fetch_main_users(client_id: int, site_id: int):
    """HAAL ALLE GEBRUIKERS OP EN ANALYSEER STRUCTUUR"""
    log.info(f"🔍 Start proces voor client {client_id}, site {site_id}")
    
    try:
        # Stap 1: Haal ALLE gebruikers op
        all_users_url = f"{HALO_API_BASE}/Users"
        log.info(f"➡️ API-aanvraag: {all_users_url}")
        
        headers = get_halo_headers()
        r = requests.get(all_users_url, headers=headers, timeout=30)
        
        if r.status_code != 200:
            log.critical(f"❌ API FOUT ({r.status_code}): {r.text}")
            log.critical("👉 OPLOSSING:")
            log.critical("1. GA NAAR: Instellingen → API-toegang in Halo")
            log.critical("2. ZORG DAT 'Teams' AANGEVINKT IS")
            log.critical("3. HERSTART DE APP NA WIJZIGINGEN")
            return []
        
        # Parse response
        data = r.json()
        if isinstance(data, list):
            users = data
        else:
            users = data.get("users", []) or data.get("Users", []) or []
        
        log.info(f"✅ {len(users)} gebruikers opgehaald - ANALYSEER STRUCTUUR")
        
        # Stap 2: Analyseer de EERSTE gebruiker voor debugging
        if users:
            first_user = users[0]
            log.info("🔍 STRUCTUUR ANALYSE - Eerste gebruiker:")
            
            # Toon alle mogelijke velden gerelateerd aan site/client
            site_fields = [k for k in first_user.keys() if "site" in k.lower()]
            client_fields = [k for k in first_user.keys() if "client" in k.lower()]
            
            log.info(f"  → Site-gerelateerde velden: {site_fields}")
            log.info(f"  → Client-gerelateerde velden: {client_fields}")
            
            # Toon waarden van deze velden
            for field in site_fields + client_fields:
                log.info(f"    - {field}: {first_user.get(field)}")
        
        # Stap 3: Filter CORRECT op basis van actuele structuur
        main_users = []
        for u in users:
            # Halo slaat site/client NIET direct op gebruiker op!
            # We moeten de 'site' en 'client' objecten checken
            
            site_match = False
            client_match = False
            
            # Check site relatie
            if "site" in u and isinstance(u["site"], dict):
                if str(u["site"].get("id", "")) == str(site_id):
                    site_match = True
            
            # Check client relatie
            if "client" in u and isinstance(u["client"], dict):
                if str(u["client"].get("id", "")) == str(client_id):
                    client_match = True
            
            # Sommige versies gebruiken 'site_id' direct
            if not site_match:
                site_id_val = str(
                    u.get("site_id") or 
                    u.get("SiteId") or 
                    u.get("siteId") or 
                    ""
                ).strip()
                if site_id_val == str(site_id):
                    site_match = True
            
            # Sommige versies gebruiken 'client_id' direct
            if not client_match:
                client_id_val = str(
                    u.get("client_id") or 
                    u.get("ClientId") or 
                    u.get("clientId") or 
                    ""
                ).strip()
                if client_id_val == str(client_id):
                    client_match = True
            
            if site_match and client_match:
                main_users.append(u)
        
        # Resultaat rapporteren
        if main_users:
            log.info(f"✅ {len(main_users)} JUISTE Main-site gebruikers gevonden!")
            if users:
                example = main_users[0]
                log.info(f"  → Voorbeeldgebruiker: ID={example.get('id')}, Naam='{example.get('name')}'")
        else:
            log.error("❌ Geen Main-site gebruikers gevonden - ANALYSEER API RESPONSE")
            log.error("👉 Volg deze stappen:")
            log.error("1. Bezoek /debug-api om de RAW API response te zien")
            log.error("2. Zoek naar 'site' en 'client' velden in de response")
            log.error("3. Pas de filtering aan op basis van echte datastructuur")
        
        return main_users
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - Nu met EXTRA DEBUGGING
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "next_steps": [
            "1. Bezoek /debug voor configuratie details",
            "2. Bezoek /debug-api voor RAW API response",
            "3. Controleer logs voor STRUCTUUR ANALYSE"
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
                "2. ZORG DAT 'Teams' AANGEVINKT IS (niet alleen 'Algemeen')",
                "3. SLA DE WIJZIGINGEN OP",
                "4. HERSTART DEZE APP VOLLEDIG"
            ],
            "debug_info": "Bezoek /debug-api voor de exacte API response"
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
    """Toon essentiële debug informatie"""
    return {
        "status": "debug-info",
        "critical_checks": [
            "1. HALO_AUTH_URL MOET ZIJN: https://bncuat.halopsa.com/oauth2/token (GEEN /auth/token!)",
            "2. 'Teams' MOET AANGEVINKT ZIJN IN API-TOEGANG (Instellingen → API-toegang)",
            "3. Geen nested endpoints gebruiken (/Sites/18/Users werkt NIET)"
        ],
        "current_config": {
            "halo_auth_url": HALO_AUTH_URL,  # Moet correct zijn geforceerd
            "halo_api_base": HALO_API_BASE,
            "client_id": HALO_CLIENT_ID_NUM,
            "site_id": HALO_SITE_ID
        },
        "api_flow": [
            "1. Authenticatie naar /oauth2/token (scope=all)",
            "2. Haal ALLE gebruikers op via /Users",
            "3. Filter LOKAAL op site/client relaties"
        ],
        "halo_api_must_know": [
            "Gebruikers hebben GEEN directe site_id/client_id velden!",
            "In plaats daarvan hebben ze 'site' en 'client' OBJECTEN",
            "Voorbeeld structuur: {\"id\": 123, \"name\": \"Jan\", \"site\": {\"id\": 18}, \"client\": {\"id\": 12}}"
        ]
    }

@app.route("/debug-api", methods=["GET"])
def debug_api():
    """Toon de RAW API response voor perfecte debugging"""
    try:
        headers = get_halo_headers()
        r = requests.get(f"{HALO_API_BASE}/Users", headers=headers, timeout=30)
        
        if r.status_code != 200:
            return {
                "error": "API fout",
                "status": r.status_code,
                "response": r.text[:500],
                "solution": [
                    "1. Zorg dat 'Teams' is aangevinkt in API-toegang",
                    "2. Controleer of je .env correct is ingesteld",
                    "3. Herstart de app na API-permissie wijzigingen"
                ]
            }, 500
        
        # Toon alleen de eerste gebruiker voor overzicht
        data = r.json()
        if isinstance(data, list) and data:
            sample = data[0]
            return {
                "status": "success",
                "total_users": len(data),
                "sample_user": sample,
                "note": "Dit is de REAL-TIME API response - kijk naar 'site' en 'client' velden"
            }
        return {"error": "Lege API response", "raw_data": data}, 500
    
    except Exception as e:
        return {"error": str(e)}, 500

# ------------------------------------------------------------------------------
# App Start - Nu Met Forceer-Modus
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # BELANGRIJK: Forceer de juiste auth URL (geen discussie)
    os.environ["HALO_AUTH_URL"] = "https://bncuat.halopsa.com/oauth2/token"
    
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS FIXER - ULTIME SOLUTION")
    log.info("-"*70)
    log.info("🔥 BELANGRIJK: Deze app FORCEERT de juiste auth URL!")
    log.info("   → Gebruikt: https://bncuat.halopsa.com/oauth2/token (GEEN /auth/token)")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN ALS HET NOG STEEDS NIET WERKT:")
    log.info("1. GA NAAR: Halo PSA → Instellingen → API-toegang")
    log.info("2. ZOEK JOUW API KEY EN KLIK BEWERKEN")
    log.info("3. VINK EXPLICIET 'Teams' AAN (niet alleen 'Algemeen')")
    log.info("4. DRUK OP 'OPSLAAN'")
    log.info("5. HERSTART DEZE APP VOLLEDIG (niet alleen wijzigingen opslaan)")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
