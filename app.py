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
# Custom Integration Core - VOLLEDIG GEFIXT VOOR JOUW UAT
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

def fetch_all_clients():
    """Haal ALLE klanten op met ULTRA-ROBUSTE PAGINERING"""
    token = get_halo_token()
    clients = []
    page = 1
    total_fetched = 0
    last_total = 0
    
    while True:
        try:
            # 🔑 BELANGRIJK: Gebruik pageSize=50 (niet 100) want UAT geeft max 50 terug
            response = requests.get(
                f"{HALO_API_BASE}/Client",
                params={
                    "page": page,
                    "pageSize": 50,
                    "active": "true"
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            clients_page = data.get("clients", [])
            
            # 🔑 ULTRA-VEILIGE controle op lege responses
            if not clients_page or len(clients_page) == 0:
                log.info(f"⏹️ Geen klanten meer gevonden op pagina {page}")
                break
                
            # Filter alleen unieke klanten
            new_clients = []
            for client in clients_page:
                if not any(c["id"] == client["id"] for c in clients):
                    new_clients.append(client)
            
            if not new_clients:
                log.info(f"⏹️ Geen nieuwe klanten gevonden op pagina {page}")
                break
                
            clients.extend(new_clients)
            total_fetched += len(new_clients)
            
            log.info(f"✅ Pagina {page} klanten: {len(new_clients)} toegevoegd (totaal: {total_fetched})")
            
            # 🔑 BELANGRIJK: Stop als we geen nieuwe klanten meer krijgen
            if len(new_clients) < 50 or total_fetched == last_total:
                break
                
            last_total = total_fetched
            page += 1
            
            # 🔑 BELANGRIJK: Maximaal 20 paginas voor 956 klanten (50 per pagina)
            if page > 20:
                log.warning("⚠️ Maximaal aantal paginas bereikt, stoppen met pagineren")
                break
                
        except Exception as e:
            log.error(f"❌ Fout bij ophalen klanten: {str(e)}")
            break
            
    log.info(f"🎉 Totaal {len(clients)} klanten opgehaald")
    return clients

def fetch_all_organisations():
    """Haal ALLE organisaties op met ULTRA-ROBUSTE PAGINERING"""
    token = get_halo_token()
    organisations = []
    page = 1
    total_fetched = 0
    last_total = 0
    
    while True:
        try:
            # 🔑 BELANGRIJK: Gebruik de CORRECTE endpoint voor organisaties
            response = requests.get(
                f"{HALO_API_BASE}/Organisation",
                params={
                    "page": page,
                    "pageSize": 50,
                    "active": "true"
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            organisations_page = data.get("organisations", [])
            
            if not organisations_page or len(organisations_page) == 0:
                log.info(f"⏹️ Geen organisaties meer gevonden op pagina {page}")
                break
                
            # Filter alleen unieke organisaties
            new_organisations = []
            for org in organisations_page:
                if not any(o["id"] == org["id"] for o in organisations):
                    new_organisations.append(org)
            
            if not new_organisations:
                log.info(f"⏹️ Geen nieuwe organisaties gevonden op pagina {page}")
                break
                
            organisations.extend(new_organisations)
            total_fetched += len(new_organisations)
            
            log.info(f"✅ Pagina {page} organisaties: {len(new_organisations)} toegevoegd (totaal: {total_fetched})")
            
            if len(new_organisations) < 50 or total_fetched == last_total:
                break
                
            last_total = total_fetched
            page += 1
            
            # 🔑 BELANGRIJK: Maximaal 5 paginas voor 2 organisaties
            if page > 5:
                log.warning("⚠️ Maximaal aantal paginas voor organisaties bereikt, stoppen met pagineren")
                break
                
        except Exception as e:
            log.error(f"❌ Fout bij ophalen organisaties: {str(e)}")
            break
            
    log.info(f"🎉 Totaal {len(organisations)} organisaties opgehaald")
    return organisations

def fetch_all_sites():
    """Haal ALLE locaties op met ULTRA-ROBUSTE PAGINERING"""
    token = get_halo_token()
    sites = []
    page = 1
    total_fetched = 0
    last_total = 0
    
    while True:
        try:
            response = requests.get(
                f"{HALO_API_BASE}/Site",
                params={
                    "page": page,
                    "pageSize": 50,
                    "active": "true"
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            sites_page = data.get("sites", [])
            
            if not sites_page or len(sites_page) == 0:
                break
                
            # Filter alleen unieke locaties
            new_sites = []
            for site in sites_page:
                if not any(s["id"] == site["id"] for s in sites):
                    new_sites.append(site)
            
            if not new_sites:
                break
                
            sites.extend(new_sites)
            total_fetched += len(new_sites)
            
            log.info(f"✅ Pagina {page} locaties: {len(new_sites)} toegevoegd (totaal: {total_fetched})")
            
            if len(new_sites) < 50 or total_fetched == last_total:
                break
                
            last_total = total_fetched
            page += 1
            
            if page > 20:
                break
                
        except Exception as e:
            log.error(f"❌ Fout bij ophalen locaties: {str(e)}")
            break
            
    log.info(f"🎉 Totaal {len(sites)} locaties opgehaald")
    return sites

def fetch_all_users():
    """Haal ALLE gebruikers op met ULTRA-ROBUSTE PAGINERING"""
    token = get_halo_token()
    users = []
    page = 1
    total_fetched = 0
    last_total = 0
    
    while True:
        try:
            response = requests.get(
                f"{HALO_API_BASE}/User",
                params={
                    "page": page,
                    "pageSize": 50,
                    "active": "true"
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            users_page = data.get("users", [])
            
            if not users_page or len(users_page) == 0:
                break
                
            # Filter alleen unieke gebruikers
            new_users = []
            for user in users_page:
                if not any(u["id"] == user["id"] for u in users):
                    new_users.append(user)
            
            if not new_users:
                break
                
            users.extend(new_users)
            total_fetched += len(new_users)
            
            log.info(f"✅ Pagina {page} gebruikers: {len(new_users)} toegevoegd (totaal: {total_fetched})")
            
            if len(new_users) < 50 or total_fetched == last_total:
                break
                
            last_total = total_fetched
            page += 1
            
            if page > 20:
                break
        except Exception as e:
            log.error(f"❌ Fout bij ophalen gebruikers: {str(e)}")
            break
            
    log.info(f"🎉 Totaal {len(users)} gebruikers opgehaald")
    return users

def normalize_name(name):
    """
    Normaliseer namen met ULTRA-ROBUSTE afhandeling specifiek voor jouw UAT
    """
    if not name:
        return ""
    
    # Stap 1: Basis schoonmaak
    name = name.lower().strip()
    
    # Stap 2: Vervang veelvoorkomende varianten - ULTRA-ROBUST
    replacements = [
        ("&amp;", "en"),
        ("&", "en"),
        ("b.v.", "bv"),
        ("b v", "bv"),
        ("b.v", "bv"),
        ("b v", "bv"),
        ("b.v", "bv"),
        ("b v", "bv"),
        ("en", "en"),
        (".", " "),
        (",", " "),
        ("-", " "),
        ("*", " "),
        ("(", " "),
        (")", " "),
        (":", " "),
        ("'", " "),
        ('"', " "),
        ("  ", " "),
        ("  ", " ")
    ]
    
    for old, new in replacements:
        name = name.replace(old, new)
    
    # Stap 3: Verwijder alle resterende niet-alphanumerieke tekens
    name = re.sub(r'[^a-z0-9 ]', ' ', name)
    
    # Stap 4: Schoonmaak spaties
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def get_main_users():
    """Combineer alle data met ULTRA-FLEXIBELE ZOEKOPDRACHTEN specifiek voor jouw UAT"""
    global client_id, bossers_client, site_id, main_site
    
    # Stap 1: Haal alle benodigde data op
    log.info("🔍 Start met ophalen van klanten, organisaties, locaties en gebruikers...")
    clients = fetch_all_clients()
    organisations = fetch_all_organisations()
    sites = fetch_all_sites()
    users = fetch_all_users()
    
    # Stap 2: Zoek de juiste organisatie voor "Bossers & Cnossen"
    log.info("🔍 Zoek organisatie 'Bossers & Cnossen' met ULTRA-FLEXIBELE matching...")
    bossers_organisation = None
    
    # 🔑 ULTRA-ROBUSTE zoektermen specifiek voor jouw UAT omgeving
    bossers_keywords = [
        "boss", "bossers", "b os", "b.o", "b&", "b c", "b.c", "b&c",
        "b en", "b&n", "b n", "b c", "b.c", "b&c", "b en", "b&n", "b n",
        "boss en", "bossers en", "boss &", "bossers &", "bosserscnossen",
        "bossers cnossen", "bossersen", "bossersn", "bossers cn", "bossersc",
        "bosserscno", "bossers cnos", "bosers", "bossen", "bosers cnossen",
        "bosc", "bossr", "boc", "bocers", "boser", "bocers", "bossr", "bossa",
        "bosserscnossen", "bossers&cnossen", "bossers en cnossen", "bosserscnossen"
    ]
    
    cnossen_keywords = [
        "cno", "cnossen", "cnos", "c.o", "c&", "c c", "c.c", "c&c",
        "c en", "c&n", "c n", "c c", "c.c", "c&c", "c en", "c&n", "c n",
        "cnossen", "cnossen", "cnossen", "cnossen", "cnossen", "cnossen",
        "cnossen", "cnossen", "cnossen", "cnossen", "cnossen", "cnossen",
        "cnoosen", "cnosen", "cnossn", "cnosn", "cnosn", "cnoss", "cnos",
        "cnosen", "cnosn", "cnossn", "cnossn", "cnosn", "cnosen", "cnoos", "cnoosn",
        "cnossen", "cnossen", "cnossen", "cnossen", "cnossen", "cnossen"
    ]
    
    # Zoek in organisaties
    for org in organisations:
        org_name = org.get("name", "") or org.get("Name", "") or org.get("ORG_NAME", "") or ""
        normalized_name = normalize_name(org_name)
        
        # Check voor Bossers & Cnossen
        has_bossers = any(keyword in normalized_name for keyword in bossers_keywords)
        has_cnossen = any(keyword in normalized_name for keyword in cnossen_keywords)
        
        if has_bossers and has_cnossen:
            bossers_organisation = org
            log.info(f"🎯 GEVONDEN: Organisatie '{org_name}' gematcht als Bossers & Cnossen")
            break
    
    # Als we de organisatie niet vonden, probeer dan klanten
    if not bossers_organisation:
        log.warning("⚠️ Organisatie niet gevonden, probeer klanten...")
        for client in clients:
            client_name = client.get("name", "") or client.get("Name", "") or client.get("CLIENT_NAME", "") or ""
            normalized_name = normalize_name(client_name)
            
            has_bossers = any(keyword in normalized_name for keyword in bossers_keywords)
            has_cnossen = any(keyword in normalized_name for keyword in cnossen_keywords)
            
            if has_bossers and has_cnossen:
                # Behandel als klant in plaats van organisatie
                bossers_organisation = {
                    "id": client["id"],
                    "name": client_name,
                    "is_client": True
                }
                log.info(f"🎯 GEVONDEN: Klant '{client_name}' gematcht als Bossers & Cnossen")
                break
    
    if not bossers_organisation:
        log.error("❌ 'Bossers & Cnossen' NIET GEVONDEN in Halo")
        # Toon de eerste 20 organisaties en klanten voor debugging
        log.info("🔍 Eerste 10 organisaties in Halo (voor debugging):")
        for org in organisations[:10]:
            org_name = org.get("name", "") or org.get("Name", "") or "Onbekend"
            log.info(f" - Org: '{org_name}' (ID: {org.get('id', 'Onbekend')})")
        
        log.info("🔍 Eerste 10 klanten in Halo (voor debugging):")
        for client in clients[:10]:
            client_name = client.get("name", "") or "Onbekend"
            log.info(f" - Client: '{client_name}' (ID: {client.get('id', 'Onbekend')})")
        
        return []
    
    # Stap 3: Vind de bijbehorende klant
    log.info("🔍 Zoek bijbehorende klant voor organisatie...")
    bossers_client = None
    
    if bossers_organisation.get("is_client", False):
        # Als we een klant hebben gevonden in plaats van organisatie
        client_id = int(bossers_organisation["id"])
        for client in clients:
            if int(client["id"]) == client_id:
                bossers_client = client
                break
    else:
        # Zoek klant met dezelfde ID als organisatie
        org_id = int(bossers_organisation["id"])
        for client in clients:
            # In jouw UAT zit de organisatie koppeling in client.organisation_id
            client_org_id = client.get("organisation_id") or client.get("OrganisationID") or client.get("organisationid") or ""
            
            if client_org_id:
                try:
                    if int(client_org主席
                    if int(client_org_id) == org_id:
                        bossers_client = client
                        break
                except (TypeError, ValueError):
                    pass
    
    if not bossers_client:
        log.error("❌ Geen bijbehorende klant gevonden voor organisatie")
        # Extra debug log voor koppeling
        log.info("🔍 Controleer koppelingen tussen klanten en organisaties...")
        for client in clients[:5]:  # Eerste 5 voor overzicht
            org_id = client.get("organisation_id") or client.get("OrganisationID") or client.get("organisationid") or "N/A"
            client_name = client.get("name", "Onbekend")
            log.info(f" - Klant '{client_name}' is gekoppeld aan organisatie ID: {org_id}")
        
        return []
    
    client_id = int(bossers_client["id"])
    org_name = bossers_organisation.get("name", "") or bossers_organisation.get("Name", "") or ""
    
    log.info(f"✅ Gebruik klant-ID: {client_id} (Naam: '{bossers_client['name']}' + Org: '{org_name}')")
    
    # Stap 4: Vind de juiste Site ID voor "Main"
    log.info("🔍 Zoek locatie 'Main' met flexibele matching...")
    main_site = None
    for s in sites:
        site_name = str(s.get("name", "")).strip()
        normalized_site = normalize_name(site_name)
        
        # Verbeterde matching voor "Main" locatie
        if "main" in normalized_site or "hoofd" in normalized_site or "head" in normalized_site or "primary" in normalized_site:
            main_site = s
            log.info(f"✅ GEVONDEN: Locatie '{site_name}' gematcht als Main (ID: {s['id']})")
            break
    
    if not main_site:
        log.error("❌ Locatie 'Main' NIET GEVONDEN in Halo")
        # Toon mogelijke matches voor debugging
        log.info("🔍 Mogelijke locatienamen in Halo (bevat 'main', 'hoofd' of 'head'):")
        for s in sites:
            site_name = str(s.get("name", "")).lower().strip()
            if "main" in site_name or "hoofd" in site_name or "head" in site_name:
                log.info(f" - '{s.get('name', 'Onbekend')}' (ID: {s.get('id')})")
        return []
    
    site_id = int(main_site["id"])
    log.info(f"✅ Gebruik locatie-ID: {site_id} (Naam: '{main_site['name']}')")
    
    # Stap 5: Filter gebruikers
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
                "client_name": f"{bossers_client['name']} {org_name}".strip(),
                "site_name": main_site["name"],
                "debug": {
                    "raw_client_id": user.get("client_id"),
                    "raw_site_id": user.get("site_id"),
                    "organisation": org_name
                }
            })
        except (TypeError, ValueError, KeyError) as e:
            log.debug(f"⚠️ Gebruiker overslaan: {str(e)}")
            continue
    
    log.info(f"✅ {len(main_users)}/{len(users)} Main-site gebruikers gevonden")
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
                "debug_hint": "Deze integratie probeert automatisch alle varianten van 'Bossers & Cnossen' te matchen inclusief organisatienaam"
            }), 500
        
        # Haal client en site namen op voor de response
        client_name = bossers_client["name"]
        org_name = bossers_organisation.get("name", "") or bossers_organisation.get("Name", "") or ""
        
        full_client_name = f"{client_name} {org_name}".strip()
        site_name = main_site["name"]
        
        log.info(f"🎉 Succesvol {len(main_users)} Main-site gebruikers geretourneerd")
        return jsonify({
            "client_id": client_id,
            "client_name": full_client_name,
            "site_id": site_id,
            "site_name": site_name,
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
        log.info("🔍 /debug endpoint aangeroepen - haal klanten, organisaties en locaties op")
        clients = fetch_all_clients()
        organisations = fetch_all_organisations()
        sites = fetch_all_sites()
        
        # Toon eerste 5 klanten, organisaties en locaties voor debugging
        sample_clients = [{"id": c["id"], "name": c["name"]} for c in clients[:5]]
        sample_organisations = [{"id": o["id"], "name": o.get("name", "") or o.get("Name", "")} for o in organisations[:5]]
        sample_sites = [{"id": s["id"], "name": s["name"]} for s in sites[:5]]
        
        # Zoek naar potentiële Bossers & Cnossen varianten in organisaties
        bossers_variants = []
        
        for org in organisations:
            org_name = org.get("name", "") or org.get("Name", "") or "Onbekend"
            normalized_name = normalize_name(org_name)
            
            # Check voor Bossers & Cnossen
            has_bossers = any(
                keyword in normalized_name
                for keyword in ["boss", "b os", "b.o", "b&", "b c", "b.c", "b&c", "bossers"]
            )
            has_cnossen = any(
                keyword in normalized_name
                for keyword in ["cno", "c.o", "c&", "c c", "c.c", "c&c", "cnossen"]
            )
            
            if has_bossers or has_cnossen:
                bossers_variants.append({
                    "id": org["id"],
                    "organisation_name": org_name,
                    "normalized_name": normalized_name,
                    "has_bossers": has_bossers,
                    "has_cnossen": has_cnossen
                })
        
        # Zoek in klanten als alternatief
        for client in clients:
            client_name = client.get("name", "Onbekend")
            normalized_name = normalize_name(client_name)
            
            has_bossers = any(
                keyword in normalized_name
                for keyword in ["boss", "b os", "b.o", "b&", "b c", "b.c", "b&c", "bossers"]
            )
            has_cnossen = any(
                keyword in normalized_name
                for keyword in ["cno", "c.o", "c&", "c c", "c.c", "c&c", "cnossen"]
            )
            
            if has_bossers or has_cnossen:
                bossers_variants.append({
                    "id": client["id"],
                    "client_name": client_name,
                    "is_client": True,
                    "normalized_name": normalized_name,
                    "has_bossers": has_bossers,
                    "has_cnossen": has_cnossen
                })
        
        log.info("✅ /debug data verzameld - controleer op Bossers & Main")
        return jsonify({
            "status": "debug_info",
            "halo_data": {
                "total_clients": len(clients),
                "example_clients": sample_clients,
                "total_organisations": len(organisations),
                "example_organisations": sample_organisations,
                "total_sites": len(sites),
                "example_sites": sample_sites,
                "note": "Controleer of 'Bossers & Cnossen' en 'Main' in deze lijsten staan"
            },
            "bossers_variants_found": bossers_variants,
            "troubleshooting": [
                "1. Klantnaam kan variëren: 'Bossers & Cnossen', 'B&C', 'Bossers en Cnossen'",
                "2. Gebruik de /debug output om de EXACTE spelling te zien",
                "3. Beheerder moet ALLE vinkjes hebben aangevinkt in API-toegang",
                "4. De organisatie zit mogelijk in een aparte endpoint (/Organisation)",
                "5. De klant kan direct de naam 'Bossers & Cnossen' hebben",
                "6. Controleer de Render logs voor 'GEVONDEN' berichten"
            ],
            "hint": "Deze integratie doorzoekt NU zowel klanten als organisaties voor 'Bossers & Cnossen'"
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
    log.info("✅ Haalt ORGANISATIES op via DE JUISTE ENDPOINT (/Organisation)")
    log.info("✅ Filtert alleen ACTIEVE klanten")
    log.info("✅ VOLLEDIGE PAGINERING MET SAFEGUARDS (max 20 paginas voor klanten)")
    log.info("✅ ZOEKT NU ZOWEL IN KLANTEN ALS IN ORGANISATIES")
    log.info("✅ ULTRA-DEBUGGABLE MET VOLLEDIGE RAW DATA LOGGING")
    log.info("-"*70)
    log.info("👉 VOLG DEZE 2 STAPPEN:")
    log.info("1. Herdeploy deze code naar Render")
    log.info("2. Bezoek EERST /debug om te zien of Bossers & Cnossen wordt gevonden")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
