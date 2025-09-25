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
# Custom Integration Core - CORRECTE GEBRUIKERSOPHAAL
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

def get_users_by_site_id(site_id):
    """Haal gebruikers op voor specifieke locatie via DE JUISTE METHODE"""
    try:
        token = get_halo_token()
        
        # 🔑 BELANGRIJK: Gebruik de locatie endpoint met includeusers=true
        response = requests.get(
            f"{HALO_API_BASE}/Site/{site_id}",
            params={
                "includeusers": "true"  # Dit is de JUISTE parameter voor gebruikers
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        response.raise_for_status()
        site_data = response.json()
        
        # Haal de gebruikers uit de locatie data
        users = []
        if "users" in site_data and site_data["users"]:
            for user in site_data["users"]:
                try:
                    users.append({
                        "id": user["id"],
                        "name": user["name"],
                        "email": user.get("emailaddress") or user.get("email") or "Geen email"
                    })
                except (TypeError, ValueError, KeyError) as e:
                    log.debug(f"⚠️ Gebruiker overslaan bij verwerking: {str(e)}")
                    continue
        
        log.info(f"✅ {len(users)} gebruikers gevonden voor locatie {site_id}")
        return users
    except Exception as e:
        log.error(f"❌ Fout bij ophalen gebruikers via locatie: {str(e)}")
        
        # Fallback: probeer via de klant endpoint als de locatie methode faalt
        try:
            log.info("⚠️ Probeer fallback: haal gebruikers op via klant endpoint...")
            token = get_halo_token()
            response = requests.get(
                f"{HALO_API_BASE}/Client/{BOSSERS_CLIENT_ID}",
                params={
                    "includeusers": "true"
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            client_data = response.json()
            
            users = []
            if "users" in client_data and client_data["users"]:
                for user in client_data["users"]:
                    try:
                        if int(user.get("site_id", 0)) == site_id:
                            users.append({
                                "id": user["id"],
                                "name": user["name"],
                                "email": user.get("emailaddress") or user.get("email") or "Geen email"
                            })
                    except (TypeError, ValueError, KeyError):
                        continue
            
            log.info(f"✅ Fallback succesvol: {len(users)} gebruikers gevonden voor locatie {site_id}")
            return users
        except Exception as fallback_error:
            log.error(f"❌ Fallback mislukt: {str(fallback_error)}")
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
    
    # Stap 3: Haal de gebruikers op VIA DE LOCATIE ENDPOINT (de JUISTE methode)
    log.info(f"🔍 Haal gebruikers op voor locatie {MAIN_SITE_ID} via de locatie endpoint...")
    main_users = get_users_by_site_id(MAIN_SITE_ID)
    
    if not main_users:
        log.warning("⚠️ Geen gebruikers gevonden via de locatie endpoint, probeer klant endpoint...")
        main_users = get_users_by_client_and_site(BOSSERS_CLIENT_ID, MAIN_SITE_ID)
    
    log.info(f"✅ {len(main_users)} Main-site gebruikers gevonden")
    return main_users

# Helper functie voor compatibiliteit
def get_users_by_client_and_site(client_id, site_id):
    """Haal gebruikers op voor specifieke klant en locatie (fallback methode)"""
    try:
        token = get_halo_token()
        response = requests.get(
            f"{HALO_API_BASE}/Client/{client_id}",
            params={
                "includeusers": "true"
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        response.raise_for_status()
        client_data = response.json()
        
        users = []
        if "users" in client_data and client_data["users"]:
            for user in client_data["users"]:
                try:
                    if int(user.get("site_id", 0)) == site_id:
                        users.append({
                            "id": user["id"],
                            "name": user["name"],
                            "email": user.get("emailaddress") or user.get("email") or "Geen email"
                        })
                except (TypeError, ValueError, KeyError):
                    continue
        
        return users
    except Exception as e:
        log.error(f"❌ Fout bij ophalen gebruikers via klant: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# API Endpoints - ULTRA-ROBUST EN SNEL
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
                    "3. Zorg dat gebruikers correct zijn gekoppeld aan deze locatie",
                    "4. Controleer in Halo of de locatie gebruikers bevat"
                ],
                "debug_hint": "Deze integratie haalt gebruikers nu via de locatie endpoint"
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
            "hint": "Controleer eerst of de hardcoded ID's correct zijn"
        }), 500

@app.route("/debug", methods=["GET"])
def debug_info():
    """Technische debug informatie - MET HARDCODED ID VALIDATIE"""
    try:
        log.info("🔍 /debug endpoint aangeroepen - valideer hardcoded ID's")
        
        # Valideer klant ID
        bossers_client = get_client_by_id(BOSSERS_CLIENT_ID)
        client_valid = bossers_client is not None
        
        # Valideer site ID
        main_site = get_site_by_id(MAIN_SITE_ID)
        site_valid = main_site is not None
        
        # Haal gebruikers op via de locatie endpoint
        log.info(f"🔍 Haal gebruikers op voor locatie {MAIN_SITE_ID} via de locatie endpoint...")
        site_users = get_users_by_site_id(MAIN_SITE_ID)
        
        # Haal gebruikers op via de klant endpoint (voor vergelijking)
        client_users = get_users_by_client_and_site(BOSSERS_CLIENT_ID, MAIN_SITE_ID)
        
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
                "users_via_site_endpoint": len(site_users),
                "users_via_client_endpoint": len(client_users),
                "sample_users": site_users[:3] if site_users else client_users[:3]
            },
            "troubleshooting": [
                f"1. Controleer of klant met ID {BOSSERS_CLIENT_ID} bestaat in Halo",
                f"2. Controleer of locatie met ID {MAIN_SITE_ID} bestaat in Halo",
                "3. Zorg dat gebruikers correct zijn gekoppeld aan deze locatie (NIET alleen aan de klant)",
                "4. In Halo: Ga naar de locatie > Gebruikers om te controleren welke gebruikers gekoppeld zijn",
                "5. Gebruikers moeten zowel aan de klant ALS aan de locatie zijn gekoppeld"
            ],
            "hint": "Deze integratie haalt gebruikers nu EERST via de locatie endpoint (de meest betrouwbare methode)"
        })
    except Exception as e:
        log.error(f"❌ Fout in /debug: {str(e)}")
        return jsonify({
            "error": str(e),
            "critical_hint": "Controleer eerst of API-toegang correct is ingesteld in Halo"
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
    log.info("✅ HAALT GEBRUIKERS NU EERST VIA LOCATIE ENDPOINT (DE JUISTE METHODE)")
    log.info("✅ INCLUSIEF FALLBACK NAAR KLANT ENDPOINT ALS NODIG")
    log.info("✅ ULTRA-DEBUGGABLE MET VERSCHILLENDE USER DATA SOURCES")
    log.info("-"*70)
    log.info("👉 VOLG DEZE 2 STAPPEN:")
    log.info("1. Herdeploy deze code naar Render")
    log.info("2. Bezoek EERST /debug om te zien of gebruikers worden gevonden")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
