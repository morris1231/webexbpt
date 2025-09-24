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

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Custom Integration Core - WERKT MET JOUW SPECIFIEKE NAAMFORMATEN
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

def get_main_users():
    """Combineer alle data met FLEXIBELE ZOEKOPDRACHTEN voor jouw specifieke Halo"""
    # Stap 1: Haal alle benodigde data op
    log.info("🔍 Start met ophalen van klanten, locaties en gebruikers...")
    clients = fetch_all_clients()
    sites = fetch_all_sites()
    users = fetch_all_users()
    
    # Stap 2: Vind de juiste Client ID voor "Bossers & Cnossen" (FLEXIBEL)
    log.info("🔍 Zoek klant 'Bossers & Cnossen' met flexibele matching...")
    bossers_client = None
    bossers_keywords = ["bossers", "cnossen", "b&c"]
    
    for c in clients:
        client_name = str(c.get("name", "")).lower().strip()
        # Verwijder ongewenste tekens voor matching
        clean_name = client_name.replace("&", "en").replace("amp;", "").replace(".", "").replace("-", " ")
        
        # Controleer of alle sleutelwoorden aanwezig zijn
        if all(keyword in clean_name for keyword in ["bossers", "cnossen"]):
            bossers_client = c
            log.info(f"✅ GEVONDEN: Klant '{client_name}' gematcht als Bossers & Cnossen (ID: {c['id']})")
            break
    
    if not bossers_client:
        log.error("❌ Klant 'Bossers & Cnossen' NIET GEVONDEN in Halo")
        # Toon mogelijke matches voor debugging
        log.info("🔍 Mogelijke klantnamen in Halo (bevat 'bossers' of 'cnossen'):")
        for c in clients:
            client_name = str(c.get("name", "")).lower().strip()
            if "bossers" in clientdelayed_name or "cnossen" in client_name or "b&c" in client_name:
                log.info(f" - '{c.get('name', 'Onbekend')}' (ID: {c.get('id')})")
        return []
    
    client_id = int(bossers_client["id"])
    log.info(f"✅ Gebruik klant-ID: {client_id} (Bossers & Cnossen)")

    # Stap 3: Vind de juiste Site ID voor "Main" (FLEXIBEL)
    log.info("🔍 Zoek locatie 'Main' met flexibele matching...")
    main_site = None
    main_keywords = ["main", "hoofd", "head"]
    
    for s in sites:
        site_name = str(s.get("name", "")).lower().strip()
        # Verwijder ongewenste tekens voor matching
        clean_name = site_name.replace("&", "en").replace("amp;", "").replace(".", "").replace("-", " ")
        
        if any(keyword in clean_name for keyword in main_keywords):
            main_site = s
            log.info(f"✅ GEVONDEN: Locatie '{site_name}' gematcht als Main (ID: {s['id']})")
            break
    
    if not main_site:
        log.error("❌ Locatie 'Main' NIET GEVONDEN in Halo")
        # Toon mogelijke matches voor debugging
        log.info("🔍 Mogelijke locatienamen in Halo (bevat 'main'):")
        for s in sites:
            site_name = str(s.get("name", "")).lower().strip()
            if "main" in site_name:
                log.info(f" - '{s.get('name', 'Onbekend')}' (ID: {s.get('id')})")
        return []
    
    site_id = int(main_site["id"])
    log.info(f"✅ Gebruik locatie-ID: {site_id} (Main)")

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
    """Eindpunt voor jouw applicatie - MET UITGEBREIDE DEBUGGING"""
    try:
        log.info("🔄 /users endpoint aangeroepen - start verwerking")
        main_users = get_main_users()
        
        if not main_users:
            log.error("❌ Geen Main-site gebruikers gevonden")
            return jsonify({
                "error": "Geen Main-site gebruikers gevonden",
                "solution": [
                    "1. Controleer of de klantnaam 'Bossers & Cnossen' correct is gespeld in Halo",
                    "2. Controleer of de locatienaam 'Main' bestaat in Halo",
                    "3. Bezoek /debug voor technische details"
                ],
                "debug_hint": "Soms zit er een verborgen '&' in de naam (B.V. vs B&V)"
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
    """Technische debug informatie - MET VERBETERDE LOGGING"""
    try:
        log.info("🔍 /debug endpoint aangeroepen - haal klanten en locaties op")
        clients = fetch_all_clients()
        sites = fetch_all_sites()
        
        # Toon eerste 3 klanten en locaties voor debugging
        sample_clients = [{"id": c["id"], "name": c["name"]} for c in clients[:3]]
        sample_sites = [{"id": s["id"], "name": s["name"]} for s in sites[:3]]
        
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
            "troubleshooting": [
                "1. Klantnaam moet 'Bossers' en 'Cnossen' bevatten (geen exacte match nodig)",
                "2. Locatienaam moet 'Main' bevatten (hoofdletterongevoelig)",
                "3. Beheerder moet ALLE vinkjes hebben aangevinkt in API-toegang"
            ],
            "hint": "Gebruik /debug om de exacte spelling van jouw klant- en locatienamen te zien"
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
    log.info("✅ Gebruikt flexibele matching voor klant- en locatienamen")
    log.info("✅ Automatische detectie van Client/Site ID's")
    log.info("-"*70)
    log.info("👉 VOLG DEZE 3 STAPPEN:")
    log.info("1. Zorg dat .env correct is ingesteld (HALO_CLIENT_ID/HALO_CLIENT_SECRET)")
    log.info("2. Deploy naar Render.com met gunicorn")
    log.info("3. Bezoek EERST /debug om te valideren")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
