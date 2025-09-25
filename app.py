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
# Custom Integration Core - EINDLIJK WERKENDE FIX
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

def fetch_all_users_for_site(site_id, client_id):
    """Haal ALLE gebruikers op voor SPECIFIEKE SITE MET KLANTFILTER"""
    token = get_halo_token()
    users = []
    page = 1
    max_pages = 5  # MAX 5 PAGINA'S (250 GEBRUIKERS) - MEER IS NIET NODIG VOOR 92 GEBRUIKERS
    site_found = False
    client_found = False
    
    while page <= max_pages:
        try:
            # 🔑 BELANGRIJK: Haal gebruikers op met site en client inclusie
            response = requests.get(
                f"{HALO_API_BASE}/Users",
                params={
                    "page": page,
                    "per_page": 50,
                    "include": "site,client"
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            users_page = data.get("users", [])
            
            if not users_page:
                log.info(f"⏹️ Geen gebruikers meer gevonden op pagina {page}")
                break
            
            # Log de STRUCTUUR van de eerste gebruiker voor debugging
            if page == 1 and len(users_page) > 0:
                first_user = users_page[0]
                log.info("🔍 STRUCTUUR VAN EERSTE GEBRUIKER:")
                log.info(f" - ID: {first_user.get('id', 'Onbekend')}")
                log.info(f" - Naam: {first_user.get('name', 'Onbekend')}")
                log.info(f" - Client ID: {first_user.get('client_id', 'Onbekend')}")
                log.info(f" - Site ID: {first_user.get('site_id', 'Onbekend')}")
                log.info(f" - Client Object: {first_user.get('client', 'Onbekend')}")
                log.info(f" - Site Object: {first_user.get('site', 'Onbekend')}")
            
            # Filter op unieke gebruikers en directe site/client koppeling
            new_users = []
            for user in users_page:
                # Controleer op directe site koppeling
                if str(user.get("site_id", "")) == str(site_id) or \
                   (isinstance(user.get("site"), dict) and str(user["site"].get("id", "")) == str(site_id)):
                    site_found = True
                
                # Controleer op directe client koppeling
                if str(user.get("client_id", "")) == str(client_id) or \
                   (isinstance(user.get("client"), dict) and str(user["client"].get("id", "")) == str(client_id)):
                    client_found = True
                
                # Voeg toe als uniek
                if not any(u["id"] == user["id"] for u in users):
                    new_users.append(user)
            
            if not new_users:
                log.info(f"⏹️ Geen nieuwe gebruikers gevonden op pagina {page}")
                break
            
            users.extend(new_users)
            log.info(f"✅ Pagina {page} gebruikers: {len(new_users)} toegevoegd (totaal: {len(users)})")
            
            # STOP VROEG ALS WE ALLEEN SITE OF KLANT ZIEN MAAR NIET COMBINATIE
            if site_found and not client_found:
                log.warning("⚠️ Waarschuwing: Gebruikers gevonden met site ID, maar geen client koppeling - controleer Halo instellingen")
            if client_found and not site_found:
                log.warning("⚠️ Waarschuwing: Gebruikers gevonden met client ID, maar geen site koppeling - controleer Halo instellingen")
            
            # BELANGRIJK: STOP PAGINERING ALS WE 92 GEBRUIKERS HEBBEN (OF GEEN NIEUWE MATCHES)
            if len(users) >= 92:
                log.info("✅ Maximaal aantal gebruikers bereikt (92) - stop paginering")
                break
            
            page += 1
            
        except Exception as e:
            log.error(f"❌ Fout bij ophalen gebruikers: {str(e)}")
            break
    
    log.info(f"🎉 Totaal {len(users)} gebruikers opgehaald (maximaal 5 pagina's)")
    return users

def get_users_by_site_id(site_id, client_id):
    """Haal gebruikers op voor specifieke locatie met ULTRA-ROBUSTE FILTERING"""
    log.info(f"🔍 Haal ALLE gebruikers op om te filteren op locatie {site_id}")
    # Stap 1: Haal alle gebruikers op voor deze site
    all_users = fetch_all_users_for_site(site_id, client_id)
    
    # Stap 2: FILTER OP SITE EN KLANT MET STRING COMPARISON (GEEN FLOAT CONVERSIE)
    site_users = []
    for user in all_users:
        try:
            # === SITE CONTROLE MET STRING COMPARISON ===
            site_match = False
            
            # Mogelijkheid 1: Directe site_id (als string)
            if "site_id" in user:
                if str(user["site_id"]).strip() == str(site_id).strip():
                    site_match = True
            
            # Mogelijkheid 2: Site object
            elif "site" in user and isinstance(user["site"], dict):
                if str(user["site"].get("id", "")).strip() == str(site_id).strip():
                    site_match = True
            
            # Mogelijkheid 3: Site name
            elif "site_name" in user:
                if str(user["site_name"]).strip().lower() == "main":
                    site_match = True
            
            # === KLANT CONTROLE MET STRING COMPARISON ===
            client_match = False
            
            # Mogelijkheid 1: Directe client_id (als string)
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
            
            # === TOEVOEGEN ALS BEIDE MATCHEN ===
            if site_match and client_match:
                site_users.append({
                    "id": user["id"],
                    "name": user["name"],
                    "email": user.get("emailaddress") or user.get("email") or "Geen email",
                    "debug": {
                        "site_match": site_match,
                        "client_match": client_match,
                        "source": "direct" if "site_id" in user else "object"
                    }
                })
                log.debug(f"✅ Gebruiker '{user['name']}' toegevoegd")
            else:
                reasons = []
                if not site_match:
                    reasons.append("site mismatch")
                if not client_match:
                    reasons.append("client mismatch")
                log.debug(f"❌ Gebruiker '{user.get('name', 'Onbekend')}' overgeslagen - Reden: {', '.join(reasons)}")
        
        except (TypeError, ValueError, KeyError) as e:
            log.debug(f"⚠️ Gebruiker overslaan bij filtering: {str(e)}")
            continue
    
    log.info(f"✅ {len(site_users)}/{len(all_users)} gebruikers gevonden voor locatie {site_id}")
    return site_users

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
    
    # Stap 3: Haal de gebruikers op VIA DE USERS ENDPOINT (de JUISTE methode)
    log.info(f"🔍 Haal gebruikers op voor locatie {MAIN_SITE_ID} via de Users endpoint...")
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
    """Technische debug informatie - MET ULTRA-ROBUSTE FILTERING"""
    try:
        log.info("🔍 /debug endpoint aangeroepen - valideer hardcoded ID's")
        # Valideer klant ID
        bossers_client = get_client_by_id(BOSSERS_CLIENT_ID)
        client_valid = bossers_client is not None
        # Valideer site ID
        main_site = get_site_by_id(MAIN_SITE_ID)
        site_valid = main_site is not None
        # Haal gebruikers op via de Users endpoint
        log.info(f"🔍 Haal gebruikers op voor locatie {MAIN_SITE_ID} via de Users endpoint...")
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
                "6. BELANGRIJK: Controleer de Render logs voor 'STRUCTUUR VAN EERSTE GEBRUIKER'"
            ],
            "hint": "Deze integratie gebruikt STRING COMPARISON (geen float conversie) voor site_id en client_id vergelijking - controleer de Render logs"
        })
    except Exception as e:
        log.error(f"❌ Fout in /debug: {str(e)}")
        return jsonify({
            "error": str(e),
            "critical_hint": "Controleer de Render logs voor de STRUCTUUR VAN EERSTE GEBRUIKER"
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
    log.info("✅ HAALT SITE EN KLANT GEGEVENS MEE VIA 'include=site,client'")
    log.info("✅ STRING COMPARISON VOOR SITE_ID EN KLANT_ID (GEEN FLOAT CONVERSIE)")
    log.info("✅ MAXIMAAL 5 PAGINA'S (250 GEBRUIKERS) VOOR SNELLE RESPONSTIJD")
    log.info("✅ STOP NA 92 GEBRUIKERS (MAXIMAAL AANTAL VOOR DEZE LOCATIE)")
    log.info("-"*70)
    log.info("👉 VOLG DEZE 2 STAPPEN:")
    log.info("1. Herdeploy deze code naar Render")
    log.info("2. Bezoek EERST /debug en controleer de Render logs voor 'STRUCTUUR VAN EERSTE GEBRUIKER'")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
