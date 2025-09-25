import os, logging, sys
from flask import Flask, jsonify
from dotenv import load_dotenv
import requests
# ------------------------------------------------------------------------------
# Basisconfiguratie - KLAAR VOOR RENDER
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-custom-integration")
app = Flask(__name__)
load_dotenv()
# Halo API credentials (UIT .env)
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
# HALO OMGEVING (UAT - niet aanpassen)
HALO_AUTH_URL = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE = "https://bncuat.halopsa.com/api"
# Bekende ID's voor Bossers & Cnossen en Main-site
BOSSERS_CLIENT_ID = 986
MAIN_SITE_ID = 992

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# NIEUWE HELPER FUNCTIES VOOR ID NORMALISATIE
# ------------------------------------------------------------------------------
def normalize_id(value):
    """Converteer willekeurige ID-waarden naar integers"""
    if value is None:
        return None
    try:
        # Handelt zowel strings als floats af (bijv. "992.0" → 992)
        return int(float(value))
    except (TypeError, ValueError, AttributeError):
        return None

def get_normalized_id(user, field_name):
    """Haal en normaliseer een ID-veld uit de gebruikersdata"""
    # Directe velden controleren
    if field_name in user:
        return normalize_id(user[field_name])
    
    # Geneste objecten controleren (bijv. site.id)
    if field_name[:-3] in user and isinstance(user[field_name[:-3]], dict):
        return normalize_id(user[field_name[:-3]].get("id"))
    
    return None

# ------------------------------------------------------------------------------
# GEUPDATE INTEGRATIE LOGICA
# ------------------------------------------------------------------------------
def get_halo_token():
    """Haal token op met ALLE benodigde scopes"""
    try:
        response = requests.post(
            HALO_AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": HALO_CLIENT_ID,
                "client_secret": HALO_CLIENT_SECRET,
                "scope": "all"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        log.critical(f"❌ AUTH MISLUKT: {str(e)}")
        if 'response' in locals():
            log.critical(f"➡️ Response: {response.text}")
        raise

def get_users_by_site_id(site_id, client_id):
    """Haal gebruikers op voor specifieke locatie met UAT-specifieke normalisatie"""
    log.info(f"🔍 Haal gebruikers op voor locatie {site_id} (Main-site)...")
    token = get_halo_token()
    users = []
    
    try:
        # UAT-specifieke aanvraag (geen /Site/{id}/Users endpoint)
        response = requests.get(
            f"{HALO_API_BASE}/Users",
            params={
                "include": "site,client",
                "site_id": site_id
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        all_users = data.get("users", [])
        
        if not all_users:
            log.error(f"❌ Geen gebruikers gevonden in de API-response voor site {site_id}")
            return []
        
        # Log API response structuur voor debugging
        first_user = all_users[0]
        log.info("🔍 API RESPONSE STRUCTUUR (EERSTE GEBRUIKER):")
        log.info(f" - Directe velden: {list(first_user.keys())}")
        log.info(f" - Voorbeeld site_id: {first_user.get('site_id', 'Niet aanwezig')}")
        log.info(f" - Voorbeeld client_id: {first_user.get('client_id', 'Niet aanwezig')}")
        
        # Normaliseer verwachte waarden
        expected_client_id = normalize_id(client_id)
        expected_site_id = normalize_id(site_id)
        
        log.info(f"🔧 Normalisatie doelstellingen:")
        log.info(f" - Verwachte klant ID: {expected_client_id} (gebaseerd op {client_id})")
        log.info(f" - Verwachte locatie ID: {expected_site_id} (gebaseerd op {site_id})")
        
        # Filter gebruikers met UAT-specifieke normalisatie
        for user in all_users:
            try:
                # Haal en normaliseer IDs
                user_client_id = get_normalized_id(user, "client_id")
                user_site_id = get_normalized_id(user, "site_id")
                
                # Debug log voor elke gebruiker
                debug_info = {
                    "raw_client_id": user.get("client_id"),
                    "raw_site_id": user.get("site_id"),
                    "normalized_client_id": user_client_id,
                    "normalized_site_id": user_site_id,
                    "client_match": user_client_id == expected_client_id,
                    "site_match": user_site_id == expected_site_id
                }
                
                # Log alleen als er een mismatch is voor debugging
                if debug_info["client_match"] and debug_info["site_match"]:
                    log.debug(f"✅ Gebruiker '{user['name']}' GEVONDEN (ID: {user['id']})")
                    users.append({
                        "id": user["id"],
                        "name": user["name"],
                        "email": user.get("emailaddress") or user.get("email") or "Geen email",
                        "debug": debug_info
                    })
                else:
                    mismatch_reasons = []
                    if not debug_info["client_match"]:
                        mismatch_reasons.append(f"Klant ID mismatch (gevonden: {user_client_id}, verwacht: {expected_client_id})")
                    if not debug_info["site_match"]:
                        mismatch_reasons.append(f"Locatie ID mismatch (gevonden: {user_site_id}, verwacht: {expected_site_id})")
                    
                    log.debug(f"❌ Gebruiker '{user.get('name', 'Onbekend')}' (ID: {user.get('id', 'Onbekend')}) overgeslagen - Reden: {', '.join(mismatch_reasons)}")
            
            except Exception as e:
                log.warning(f"⚠️ Gebruiker overslaan bij verwerking: {str(e)} | Gegevens: {user.get('id', 'Onbekend')} - {user.get('name', 'Onbekend')}")
                continue
        
        log.info(f"✅ {len(users)}/{len(all_users)} gebruikers GEVALIDEERD voor locatie {site_id}")
        return users
    
    except Exception as e:
        log.error(f"❌ Fout bij ophalen site gebruikers: {str(e)}")
        return []

def get_main_users():
    """Haal Main-site gebruikers op voor Bossers & Cnossen met HARDCODED ID's"""
    log.info(f"🔍 Start proces voor Bossers & Cnossen (Klant ID: {BOSSERS_CLIENT_ID}, Locatie ID: {MAIN_SITE_ID})")
    
    # Stap 1: Valideer klant ID (extra veiligheid)
    bossers_client = get_client_by_id(BOSSERS_CLIENT_ID)
    if not bossers_client:
        log.error(f"❌ Klant met ID {BOSSERS_CLIENT_ID} NIET GEVONDEN in Halo")
        return []
    
    # Stap 2: Valideer locatie ID (extra veiligheid)
    main_site = get_site_by_id(MAIN_SITE_ID)
    if not main_site:
        log.error(f"❌ Locatie met ID {MAIN_SITE_ID} NIET GEVONDEN in Halo")
        return []
    
    # Stap 3: Haal gebruikers op met UAT-specifieke logica
    main_users = get_users_by_site_id(MAIN_SITE_ID, BOSSERS_CLIENT_ID)
    
    if not main_users:
        log.error("❌ Geen Main-site gebruikers gevonden - Controleer:")
        log.error("1. Of de gebruikers ZOWEL aan de klant ALS aan de locatie zijn gekoppeld")
        log.error("2. Of de locatie ID correct is (UAT gebruikt vaak floats als strings)")
        log.error("3. De debug-gegevens in /debug voor exacte ID-waarden")
        return []
    
    log.info(f"🎉 SUCCES: {len(main_users)} Main-site gebruikers GEVONDEN voor Bossers & Cnossen")
    return main_users

# ------------------------------------------------------------------------------
# API Endpoints - ULTRA-DEBUGGABLE
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health_check():
    return {
        "status": "custom_integration_ready",
        "message": "Halo Custom Integration API - Bezoek /users voor data",
        "environment": "UAT",
        "instructions": [
            "1. Zorg dat .env correct is ingesteld",
            "2. Bezoek /debug voor technische validatie",
            "3. Bezoek /users voor Main-site gebruikers"
        ]
    }

@app.route("/users", methods=["GET"])
def get_users():
    """Eindpunt voor jouw applicatie - MET HARDCODED ID'S"""
    try:
        log.info("🔄 /users endpoint aangeroepen - start verwerking")
        main_users = get_main_users()
        
        if not main_users:
            log.error("❌ Geen Main-site gebruikers gevonden")
            return jsonify({
                "error": "Geen Main-site gebruikers gevonden",
                "solution": [
                    "1. Zorg dat gebruikers ZOWEL aan de klant ALS aan de locatie zijn gekoppeld in Halo",
                    "2. Controleer of de locatie ID correct is (soms als float geretourneerd)",
                    "3. Bezoek /debug voor gedetailleerde technische informatie",
                    "4. In Halo: Ga naar de locatie > Gebruikers om te controleren welke gebruikers gekoppeld zijn"
                ],
                "debug_hint": "Deze integratie logt nu de EXACTE ID-waarden zoals ontvangen van de API"
            }), 500
        
        # Haal klant- en locatiegegevens op voor respons
        bossers_client = get_client_by_id(BOSSERS_CLIENT_ID)
        main_site = get_site_by_id(MAIN_SITE_ID)
        
        log.info(f"🎉 Succesvol {len(main_users)} Main-site gebruikers geretourneerd")
        return jsonify({
            "client_id": BOSSERS_CLIENT_ID,
            "client_name": bossers_client.get("name", "Onbekend") if bossers_client else "Niet gevonden",
            "site_id": MAIN_SITE_ID,
            "site_name": main_site.get("name", "Onbekend") if main_site else "Niet gevonden",
            "total_users": len(main_users),
            "users": main_users,
            "environment": "UAT"
        })
    except Exception as e:
        log.error(f"🔥 Fout in /users: {str(e)}")
        return jsonify({
            "error": str(e),
            "hint": "Controleer de Render logs voor 'API RESPONSE STRUCTUUR' en 'Normalisatie doelstellingen'"
        }), 500

@app.route("/debug", methods=["GET"])
def debug_info():
    """Technische debug informatie met UAT-specifieke validatie"""
    try:
        log.info("🔍 /debug endpoint aangeroepen - start UAT-specifieke validatie")
        
        # Haal klantgegevens op
        bossers_client = get_client_by_id(BOSSERS_CLIENT_ID)
        client_valid = bossers_client is not None
        
        # Haal locatiegegevens op
        main_site = get_site_by_id(MAIN_SITE_ID)
        site_valid = main_site is not None
        
        # Haal gebruikers op met UAT-specifieke logica
        site_users = get_users_by_site_id(MAIN_SITE_ID, BOSSERS_CLIENT_ID)
        
        # Analyseer API response voor problemen
        problem_analysis = []
        if not site_valid:
            problem_analysis.append("Locatie niet gevonden - Controleer of ID 992 bestaat in UAT")
        if not client_valid:
            problem_analysis.append("Klant niet gevonden - Controleer of ID 986 bestaat in UAT")
        if site_users:
            problem_analysis.append("Gebruikers gevonden - Integratie werkt correct!")
        else:
            problem_analysis.append("GEEN gebruikers gevonden - Mogelijke oorzaken:")
            problem_analysis.append("• Gebruikers zijn alleen aan de klant gekoppeld, niet aan de locatie")
            problem_analysis.append("• ID-type mismatch (float vs integer) in UAT omgeving")
            problem_analysis.append("• Onvoldoende API-permissies voor gebruikersgegevens")
        
        log.info("✅ /debug data verzameld - UAT-specifieke analyse klaar")
        return jsonify({
            "status": "debug_info",
            "environment": "UAT",
            "integration_version": "3.1",
            "hardcoded_ids": {
                "bossers_client_id": BOSSERS_CLIENT_ID,
                "client_name": bossers_client.get("name", "Niet gevonden") if client_valid else "Niet gevonden",
                "client_exists": client_valid,
                "main_site_id": MAIN_SITE_ID,
                "site_name": main_site.get("name", "Niet gevonden") if site_valid else "Niet gevonden",
                "site_exists": site_valid
            },
            "api_validation": {
                "total_users_found": len(site_users),
                "api_endpoint_used": f"{HALO_API_BASE}/Users",
                "request_parameters": {
                    "include": "site,client",
                    "site_id": MAIN_SITE_ID
                },
                "problem_analysis": problem_analysis
            },
            "user_sample": site_users[:3] if site_users else [],
            "troubleshooting": [
                "1. In Halo: Ga naar de locatie > Gebruikers (NIET de klant > Gebruikers)",
                "2. Zorg dat gebruikers ZOWEL aan de klant ALS aan de locatie zijn gekoppeld",
                "3. Controleer de Render logs op 'API RESPONSE STRUCTUUR' voor exacte ID-formaten",
                "4. UAT retourneert vaak floats als strings (bijv. '992.0' i.p.v. 992)",
                "5. Gebruik /debug om de exacte ID-waarden te zien die de API retourneert"
            ]
        })
    except Exception as e:
        log.error(f"❌ Fout in /debug: {str(e)}")
        return jsonify({
            "error": str(e),
            "critical_hint": "Controleer de Render logs voor 'API RESPONSE STRUCTUUR'"
        }), 500

# ------------------------------------------------------------------------------
# Render.com Deployment - KLAAR VOOR DIRECTE DEPLOY
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO CUSTOM INTEGRATION API - VOLLEDIG ZELFSTANDIG")
    log.info("-"*70)
    log.info(f"✅ Gebruikt KLANT ID: {BOSSERS_CLIENT_ID} (Bossers & Cnossen B.V.)")
    log.info(f"✅ Gebruikt SITE ID: {MAIN_SITE_ID} (Main)")
    log.info("✅ UAT-SPECIFIEKE NORMALISATIE INGEBOUWD VOOR ID TYPES")
    log.info("✅ DIRECTE VERWERKING VAN API RESPONSE ZONDER TYPE-AFNHANKELIJKHEID")
    log.info("-"*70)
    log.info("👉 VOLG DEZE 2 STAPPEN:")
    log.info("1. Herdeploy deze code naar Render")
    log.info("2. Bezoek EERST /debug en controleer de 'API RESPONSE STRUCTUUR' in de logs")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
