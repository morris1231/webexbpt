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
# Custom Integration Core - SPECIAAL VOOR UAT OMGEVING
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

def get_client_by_id(client_id):
    """Haal een specifieke klant op via ID"""
    try:
        token = get_halo_token()
        response = requests.get(
            f"{HALO_API_BASE}/Client/{client_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log.error(f"❌ Fout bij ophalen klant met ID {client_id}: {str(e)}")
        return None

def get_site_by_id(site_id):
    """Haal een specifieke locatie op via ID"""
    try:
        token = get_halo_token()
        response = requests.get(
            f"{HALO_API_BASE}/Site/{site_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log.error(f"❌ Fout bij ophalen locatie met ID {site_id}: {str(e)}")
        return None

def get_users_by_site_id(site_id, client_id):
    """Haal gebruikers op voor specifieke locatie via DE JUISTE ENDPOINT VOOR UAT"""
    log.info(f"🔍 Haal gebruikers op voor locatie {site_id} via de CORRECTE UAT endpoint...")
    
    token = get_halo_token()
    users = []
    
    try:
        # 🔑 BELANGRIJK: Gebruik de JUISTE endpoint voor UAT
        # In UAT werkt /Site/{id}/Users NIET - gebruik /Users met filters
        response = requests.get(
            f"{HALO_API_BASE}/Users",
            params={
                "include": "site,client",
                "site_id": site_id  # Direct filteren op site_id
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        all_users = data.get("users", [])
        
        if not all_users:
            log.error(f"❌ Geen gebruikers gevonden voor site {site_id}")
            return []
        
        # Log de STRUCTUUR van de eerste gebruiker voor debugging
        first_user = all_users[0]
        log.info("🔍 STRUCTUUR VAN EERSTE GEBRUIKER (VIA USERS ENDPOINT):")
        log.info(f" - ID: {first_user.get('id', 'Onbekend')}")
        log.info(f" - Naam: {first_user.get('name', 'Onbekend')}")
        log.info(f" - Client ID: {first_user.get('client_id', 'Onbekend')}")
        log.info(f" - Site ID: {first_user.get('site_id', 'Onbekend')}")
        log.info(f" - Client Object: {first_user.get('client', 'Onbekend')}")
        log.info(f" - Site Object: {first_object = first_user.get('site', 'Onbekend')}")
        
        # EXTRA CONTROLE VOOR UAT SPECIFIEK
        if first_object != "Onbekend" and isinstance(first_object, dict):
            log.info(f"   • Site Object ID: {first_object.get('id', 'Onbekend')}")
            log.info(f"   • Site Object Naam: {first_object.get('name', 'Onbekend')}")
        
        # Filter op de juiste klant
        for user in all_users:
            try:
                # Controleer client koppeling
                client_match = False
                
                # Mogelijkheid 1: Directe client_id
                if "client_id" in user:
                    if str(user["client_id"]).strip() == str(client_id).strip():
                        client_match = True
                
                # Mogelijkheid 2: Client object
                elif "client" in user and isinstance(user["client"], dict):
                    if str(user["client"].get("id", "")).strip() == str(client_id).strip():
                        client_match = True
                
                # Mogelijkheid 3: Client name
                elif "client_name" in user:
                    if "bossers" in str(user["client_name"]).lower():
                        client_match = True
                
                # Controleer site koppeling (speciaal voor UAT)
                site_match = False
                
                # Mogelijkheid 1: Directe site_id
                if "site_id" in user:
                    if str(user["site_id"]).strip() == str(site_id).strip():
                        site_match = True
                
                # Mogelijkheid 2: Site object
                elif "site" in user and isinstance(user["site"], dict):
                    if str(user["site"].get("id", "")).strip() == str(site_id).strip():
                        site_match = True
                
                # Mogelijkheid 3: Site name
                elif "site_name" in user:
                    if "main" in str(user["site_name"]).lower():
                        site_match = True
                
                # Voeg toe als zowel client ALS site matchen
                if client_match and site_match:
                    users.append({
                        "id": user["id"],
                        "name": user["name"],
                        "email": user.get("emailaddress") or user.get("email") or "Geen email",
                        "debug": {
                            "client_match": client_match,
                            "site_match": site_match,
                            "source": "direct" if "site_id" in user else "object"
                        }
                    })
                    log.debug(f"✅ Gebruiker '{user['name']}' toegevoegd (Client & Site match)")
                else:
                    reasons = []
                    if not client_match:
                        reasons.append("client mismatch")
                    if not site_match:
                        reasons.append("site mismatch")
                    log.debug(f"❌ Gebruiker '{user.get('name', 'Onbekend')}' overgeslagen - Reden: {', '.join(reasons)}")
            
            except (TypeError, ValueError, KeyError) as e:
                log.debug(f"⚠️ Gebruiker overslaan bij filtering: {str(e)}")
                continue
        
        log.info(f"✅ {len(users)}/{len(all_users)} gebruikers gevonden voor locatie {site_id}")
        return users
        
    except Exception as e:
        log.error(f"❌ Fout bij ophalen site gebruikers: {str(e)}")
        return []

def get_main_users():
    """Haal Main-site gebruikers op voor Bossers & Cnossen met HARDCODED ID's"""
    global client_id, bossers_client, site_id, main_site
    # Stap 1: Haal de specifieke klant op via ID
    log.info(f"🔍 Haal klant op met ID {BOSSERS_CLIENT_ID} (Bossers & Cnossen B.V.)")
    bossers_client = get_client_by_id(BOSSERS_CLIENT_ID)
    if not bossers_client:
        log.error(f"❌ Klant met ID {BOSSERS_CLIENT_ID} NIET GEVONDEN in Halo")
        return []
    client_id = BOSSERS_CLIENT_ID
    log.info(f"✅ Gebruik klant-ID: {client_id} (Naam: '{bossers_client.get('name', 'Onbekend')}')")
    
    # Stap 2: Haal de specifieke locatie op via ID
    log.info(f"🔍 Haal locatie op met ID {MAIN_SITE_ID} (Main)")
    main_site = get_site_by_id(MAIN_SITE_ID)
    if not main_site:
        log.error(f"❌ Locatie met ID {MAIN_SITE_ID} NIET GEVONDEN in Halo")
        return []
    site_id = MAIN_SITE_ID
    log.info(f"✅ Gebruik locatie-ID: {site_id} (Naam: '{main_site.get('name', 'Onbekend')}')")
    
    # Stap 3: Haal de gebruikers op VIA DE JUISTE ENDPOINT VOOR UAT
    log.info(f"🔍 Haal gebruikers op voor locatie {MAIN_SITE_ID} via de CORRECTE UAT endpoint...")
    main_users = get_users_by_site_id(MAIN_SITE_ID, BOSSERS_CLIENT_ID)
    
    if not main_users:
        log.error("❌ Geen Main-site gebruikers gevonden")
        return []
    
    log.info(f"✅ {len(main_users)} Main-site gebruikers gevonden")
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
                    f"1. Controleer of klant met ID {BOSSERS_CLIENT_ID} bestaat",
                    f"2. Controleer of locatie met ID {MAIN_SITE_ID} bestaat",
                    "3. Zorg dat gebruikers correct zijn gekoppeld aan deze locatie (NIET alleen aan de klant)",
                    "4. Controleer de Render logs voor 'STRUCTUUR VAN EERSTE GEBRUIKER'",
                    "5. In Halo: Ga naar de locatie > Gebruikers om te controleren welke gebruikers gekoppeld zijn"
                ],
                "debug_hint": "Deze integratie logt nu de VOLLEDIGE STRUCTUUR van de eerste gebruiker voor debugging"
            }), 500
        log.info(f"🎉 Succesvol {len(main_users)} Main-site gebruikers geretourneerd")
        return jsonify({
            "client_id": client_id,
            "client_name": bossers_client.get("name", "Onbekend"),
            "site_id": site_id,
            "site_name": main_site.get("name", "Onbekend"),
            "total_users": len(main_users),
            "users": main_users
        })
    except Exception as e:
        log.error(f"🔥 Fout in /users: {str(e)}")
        return jsonify({
            "error": str(e),
            "hint": "Controleer eerst de Render logs voor de STRUCTUUR VAN EERSTE GEBRUIKER"
        }), 500

@app.route("/debug", methods=["GET"])
def debug_info():
    """Technische debug informatie - MET DE JUISTE ENDPOINT VOOR UAT"""
    try:
        log.info("🔍 /debug endpoint aangeroepen - valideer hardcoded ID's")
        # Valideer klant ID
        bossers_client = get_client_by_id(BOSSERS_CLIENT_ID)
        client_valid = bossers_client is not None
        # Valideer site ID
        main_site = get_site_by_id(MAIN_SITE_ID)
        site_valid = main_site is not None
        # Haal gebruikers op via de JUISTE UAT ENDPOINT
        log.info(f"🔍 Haal gebruikers op voor locatie {MAIN_SITE_ID} via de CORRECTE UAT endpoint...")
        site_users = get_users_by_site_id(MAIN_SITE_ID, BOSSERS_CLIENT_ID)
        # Haal een sample van de gebruikers voor debugging
        sample_users = site_users[:3] if site_users else []
        log.info("✅ /debug data verzameld - controleer hardcoded ID's")
        return jsonify({
            "status": "debug_info",
            "hardcoded_ids": {
                "bossers_client_id": BOSSERS_CLIENT_ID,
                "client_name": bossers_client.get("name", "Niet gevonden") if client_valid else "Niet gevonden",
                "client_valid": client_valid,
                "main_site_id": MAIN_SITE_ID,
                "site_name": main_site.get("name", "Niet gevonden") if site_valid else "Niet gevonden",
                "site_valid": site_valid
            },
            "user_data": {
                "total_users_found": len(site_users),
                "sample_users": sample_users,
                "site_data_structure": main_site if site_valid else "Site niet gevonden"
            },
            "troubleshooting": [
                f"1. Controleer of klant met ID {BOSSERS_CLIENT_ID} bestaat in Halo",
                f"2. Controleer of locatie met ID {MAIN_SITE_ID} bestaat in Halo",
                "3. Zorg dat gebruikers correct zijn gekoppeld aan deze locatie (NIET alleen aan de klant)",
                "4. In Halo: Ga naar de locatie > Gebruikers om te controleren welke gebruikers gekoppeld zijn",
                "5. Gebruikers moeten zowel aan de klant ALS aan de locatie zijn gekoppeld",
                "6. BELANGRIJK: Controleer de Render logs voor 'STRUCTUUR VAN EERSTE GEBRUIKER (VIA USERS ENDPOINT)'"
            ],
            "hint": "Deze integratie gebruikt de JUISTE HALO API ENDPOINT VOOR UAT - controleer de Render logs"
        })
    except Exception as e:
        log.error(f"❌ Fout in /debug: {str(e)}")
        return jsonify({
            "error": str(e),
            "critical_hint": "Controleer de Render logs voor de STRUCTUUR VAN EERSTE GEBRUIKER (VIA USERS ENDPOINT)"
        }), 500

# ------------------------------------------------------------------------------
# Render.com Deployment - KLAAR VOOR DIRECTE DEPLOY
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO CUSTOM INTEGRATION API - VOLLEDIG ZELFSTANDIG")
    log.info("-"*70)
    log.info(f"✅ Gebruikt HARDCODED KLANT ID: {BOSSERS_CLIENT_ID} (Bossers & Cnossen B.V.)")
    log.info(f"✅ Gebruikt HARDCODED SITE ID: {MAIN_SITE_ID} (Main)")
    log.info("✅ GEBRUIKT DE JUISTE HALO API ENDPOINT VOOR UAT: /Users met filters")
    log.info("✅ HAALT GEBRUIKERS OP VIA DE ALGEMENE USERS ENDPOINT MET FILTERS")
    log.info("✅ ULTRA-ROBUSTE FILTERING VOOR UAT SPECIFIEKE PROBLEMEN")
    log.info("-"*70)
    log.info("👉 VOLG DEZE 2 STAPPEN:")
    log.info("1. Herdeploy deze code naar Render")
    log.info("2. Bezoek EERST /debug en controleer de Render logs voor 'STRUCTUUR VAN EERSTE GEBRUIKER (VIA USERS ENDPOINT)'")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
