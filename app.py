import os, logging, sys
import re
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

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Custom Integration Core - SPECIAAL VOOR JOUW "BOSSERS & CNOSSEN"
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
        log.critical(f"➡️ Response: {response.text if 'response' in locals() else 'Geen response'}")
        raise

def fetch_all_clients():
    """Haal ALLE klanten op met verbeterde foutafhandeling"""
    token = get_halo_token()
    clients = []
    page = 1
    
    while True:
        try:
            response = requests.get(
                f"{HALO_API_BASE}/Client",
                params={"page": page, "pageSize": 100},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            clients_page = data.get("clients", [])
            
            if not clients_page:
                break
                
            clients.extend(clients_page)
            log.info(f"✅ Pagina {page} klanten: {len(clients_page)} toegevoegd (totaal: {len(clients)})")
            
            if len(clients_page) < 100:
                break
                
            page += 1
        except Exception as e:
            log.error(f"❌ Fout bij ophalen klanten: {str(e)}")
            break
    
    log.info(f"🎉 Totaal {len(clients)} klanten opgehaald")
    return clients

def fetch_all_sites():
    """Haal ALLE locaties op met verbeterde foutafhandeling"""
    token = get_halo_token()
    sites = []
    page = 1
    
    while True:
        try:
            response = requests.get(
                f"{HALO_API_BASE}/Site",
                params={"page": page, "pageSize": 100},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            sites_page = data.get("sites", [])
            
            if not sites_page:
                break
                
            sites.extend(sites_page)
            log.info(f"✅ Pagina {page} locaties: {len(sites_page)} toegevoegd (totaal: {len(sites)})")
            
            if len(sites_page) < 100:
                break
                
            page += 1
        except Exception as e:
            log.error(f"❌ Fout bij ophalen locaties: {str(e)}")
            break
    
    log.info(f"🎉 Totaal {len(sites)} locaties opgehaald")
    return sites

def fetch_all_users():
    """Haal ALLE gebruikers op met verbeterde foutafhandeling"""
    token = get_halo_token()
    users = []
    page = 1
    
    while True:
        try:
            response = requests.get(
                f"{HALO_API_BASE}/User",
                params={"page": page, "pageSize": 100},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            users_page = data.get("users", [])
            
            if not users_page:
                break
                
            users.extend(users_page)
            log.info(f"✅ Pagina {page} gebruikers: {len(users_page)} toegevoegd (totaal: {len(users)})")
            
            if len(users_page) < 100:
                break
                
            page += 1
        except Exception as e:
            log.error(f"❌ Fout bij ophalen gebruikers: {str(e)}")
            break
    
    log.info(f"🎉 Totaal {len(users)} gebruikers opgehaald")
    return users

def normalize_name(name):
    """Normaliseer namen voor betere matching (speciaal voor jouw Halo UAT)"""
    if not name:
        return ""
    
    # Stap 1: Naar kleine letters en verwijder voor/achtervoegsel spaties
    name = name.lower().strip()
    
    # Stap 2: Vervang veelvoorkomende varianten
    name = name.replace("&amp;", "en")
    name = name.replace("&", "en")
    name = name.replace("b.v.", "bv")
    name = name.replace("b v", "bv")
    name = name.replace(".", "")
    name = name.replace(",", "")
    name = name.replace("-", " ")
    name = name.replace("*", "")
    name = name.replace("(", "")
    name = name.replace(")", "")
    
    # Stap 3: Verwijder alle niet-alphanumerieke tekens behalve spaties
    name = re.sub(r'[^a-z0-9 ]', ' ', name)
    
    # Stap 4: Vervang meervoudige spaties door enkele spatie
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def get_main_users():
    """Combineer alle data met ULTRA-FLEXIBELE ZOEKOPDRACHTEN voor jouw specifieke Halo"""
    # Stap 1: Haal alle benodigde data op
    log.info("🔍 Start met ophalen van klanten, locaties en gebruikers...")
    clients = fetch_all_clients()
    sites = fetch_all_sites()
    users = fetch_all_users()
    
    # Stap 2: Vind de juiste Client ID voor "Bossers & Cnossen" (ULTRA-FLEXIBEL)
    log.info("🔍 Zoek klant 'Bossers & Cnossen' met geavanceerde matching...")
    bossers_client = None
    bossers_keywords = ["bossers", "cnossen", "b", "c"]
    
    # Log alle potentiële matches voor debugging
    potential_matches = []
    
    for c in clients:
        original_name = c.get("name", "Onbekend")
        normalized_name = normalize_name(original_name)
        
        # Controleer of alle sleutelwoorden aanwezig zijn
        has_all_keywords = all(
            keyword in normalized_name 
            for keyword in ["bossers", "cnossen"]
        )
        
        # Controleer of minimaal 2 sleutelwoorden aanwezig zijn (fallback)
        keyword_count = sum(
            1 for keyword in bossers_keywords 
            if keyword in normalized_name
        )
        
        # Log alle matches voor debugging
        if has_all_keywords or keyword_count >= 2:
            match_type = "✅ Exact match" if has_all_keywords else "⚠️ Partial match"
            log.info(f"{match_type}: '{original_name}' → Normalized: '{normalized_name}'")
            potential_matches.append({
                "id": c["id"],
                "original_name": original_name,
                "normalized_name": normalized_name,
                "match_type": "exact" if has_all_keywords else "partial"
            })
            
            if not bossers_client and has_all_keywords:
                bossers_client = c
    
    # Als we geen exacte match vonden, gebruik dan de beste partial match
    if not bossers_client and potential_matches:
        bossers_client = next((c for c in clients if c["id"] == potential_matches[0]["id"]), None)
        if bossers_client:
            log.warning(f"⚠️ Gebruik PARTIËLE MATCH voor klant: {bossers_client['name']}")

    if not bossers_client:
        log.error("❌ Klant 'Bossers & Cnossen' NIET GEVONDEN in Halo")
        # Toon alle potentiële matches voor debugging
        if potential_matches:
            log.info("🔍 Potentiële klantnamen gevonden:")
            for match in potential_matches:
                log.info(f" - ID {match['id']}: '{match['original_name']}' (Normalized: '{match['normalized_name']}')")
        else:
            log.info("🔍 Geen potentiële klantnamen gevonden met 'bossers' of 'cnossen'")
        return []
    
    client_id = int(bossers_client["id"])
    log.info(f"✅ Gebruik klant-ID: {client_id} (Naam: '{bossers_client['name']}')")

    # Stap 3: Vind de juiste Site ID voor "Main" (FLEXIBEL)
    log.info("🔍 Zoek locatie 'Main' met flexibele matching...")
    main_site = None
    
    for s in sites:
        site_name = str(s.get("name", "")).lower().strip()
        normalized_site = normalize_name(site_name)
        
        if "main" in normalized_site or "hoofd" in normalized_site:
            main_site = s
            log.info(f"✅ GEVONDEN: Locatie '{site_name}' gematcht als Main (ID: {s['id']})")
            break
    
    if not main_site:
        log.error("❌ Locatie 'Main' NIET GEVONDEN in Halo")
        # Toon mogelijke matches voor debugging
        log.info("🔍 Mogelijke locatienamen in Halo (bevat 'main'):")
        for s in sites:
            site_name = str(s.get("name", "")).lower().strip()
            if "main" in site_name or "hoofd" in site_name:
                log.info(f" - '{s.get('name', 'Onbekend')}' (ID: {s.get('id')})")
        return []
    
    site_id = int(main_site["id"])
    log.info(f"✅ Gebruik locatie-ID: {site_id} (Naam: '{main_site['name']}')")

    # Stap 4: Filter gebruikers die aan Main-site gekoppeld zijn
    log.info("🔍 Filter Main-site gebruikers...")
    main_users = []
    for user in users:
        try:
            # Controleer client koppeling
            user_client_id = int(user.get("client_id", 0))
            if user_client_id != client_id:
                continue
                
            # Controleer site koppeling
            user_site_id = int(user.get("site_id", 0))
            if user_site_id != site_id:
                continue
                
            main_users.append({
                "id": user["id"],
                "name": user["name"],
                "email": user.get("emailaddress") or user.get("email") or "Geen email",
                "client_name": bossers_client["name"],
                "site_name": main_site["name"],
                "debug": {
                    "raw_client_id": user.get("client_id"),
                    "raw_site_id": user.get("site_id")
                }
            })
        except (TypeError, ValueError, KeyError) as e:
            log.debug(f"⚠️ Gebruiker overslaan: {str(e)}")
            continue
    
    log.info(f"✅ {len(main_users)}/{len(users)} Main-site gebruikers gevonden")
    return main_users

# ------------------------------------------------------------------------------
# API Endpoints - KLAAR VOOR RENDER DEPLOY
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
    """Eindpunt voor jouw applicatie - MET ULTRA-DETAILRIJKE DEBUGGING"""
    try:
        log.info("🔄 /users endpoint aangeroepen - start verwerking")
        main_users = get_main_users()
        
        if not main_users:
            log.error("❌ Geen Main-site gebruikers gevonden")
            return jsonify({
                "error": "Geen Main-site gebruikers gevonden",
                "solution": [
                    "1. Controleer de /debug output voor mogelijke klantnamen",
                    "2. Zorg dat de klant 'Bossers & Cnossen' bestaat in Halo UAT",
                    "3. Controleer de Render logs voor match-details"
                ],
                "debug_hint": "Deze integratie probeert automatisch alle varianten van 'Bossers & Cnossen' te matchen"
            }), 500
        
        log.info(f"🎉 Succesvol {len(main_users)} Main-site gebruikers geretourneerd")
        return jsonify({
            "client_id": client_id,
            "client_name": bossers_client["name"],
            "site_id": site_id,
            "site_name": main_site["name"],
            "total_users": len(main_users),
            "users": main_users
        })
    except Exception as e:
        log.error(f"🔥 Fout in /users: {str(e)}")
        return jsonify({
            "error": str(e),
            "hint": "Controleer eerst /debug endpoint voor basisvalidatie"
        }), 500

@app.route("/debug", methods=["GET"])
def debug_info():
    """Technische debug informatie - MET ULTRA-DETAILRIJKE LOGGING"""
    try:
        log.info("🔍 /debug endpoint aangeroepen - haal klanten en locaties op")
        clients = fetch_all_clients()
        sites = fetch_all_sites()
        
        # Toon eerste 3 klanten en locaties voor debugging
        sample_clients = [{"id": c["id"], "name": c["name"]} for c in clients[:3]]
        sample_sites = [{"id": s["id"], "name": s["name"]} for s in sites[:3]]
        
        # Zoek naar potentiële Bossers & Cnossen varianten
        bossers_variants = []
        for c in clients:
            normalized = normalize_name(c.get("name", ""))
            if "bossers" in normalized or "cnossen" in normalized or "b" in normalized or "c" in normalized:
                bossers_variants.append({
                    "id": c["id"],
                    "original_name": c["name"],
                    "normalized_name": normalized
                })
        
        log.info("✅ /debug data verzameld - controleer op Bossers & Main")
        return jsonify({
            "status": "debug_info",
            "halo_data": {
                "total_clients": len(clients),
                "example_clients": sample_clients,
                "total_sites": len(sites),
                "example_sites": sample_sites,
                "note": "Controleer of 'Bossers & Cnossen' en 'Main' in deze lijsten staan"
            },
            "bossers_variants_found": bossers_variants,
            "troubleshooting": [
                "1. Klantnaam kan variëren: 'Bossers & Cnossen', 'B&C', 'Bossers en Cnossen'",
                "2. Gebruik de /debug output om de EXACTE spelling te zien",
                "3. Beheerder moet ALLE vinkjes hebben aangevinkt in API-toegang"
            ],
            "hint": "Deze integratie normaliseert namen automatisch voor betere matching"
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
    log.info("✅ Werkt ZONDER 'include' parameter (omzeilt Halo UAT bugs)")
    log.info("✅ Gebruikt ULTRA-FLEXIBELE matching voor klantnamen")
    log.info("✅ Normaliseert namen automatisch voor betere matching")
    log.info("-"*70)
    log.info("👉 VOLG DEZE 2 STAPPEN:")
    log.info("1. Herdeploy deze code naar Render")
    log.info("2. Bezoek EERST /debug om te zien welke klantnamen worden gevonden")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
