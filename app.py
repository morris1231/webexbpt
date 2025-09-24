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
# Custom Integration Core - MET VOLLEDIGE ORGANISATIE ONDERSTEUNING
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
    """Haal ALLE klanten + ORGANISATIES op (met verbeterde organisatie-ondersteuning)"""
    token = get_halo_token()
    clients = []
    page = 1
    while True:
        try:
            # 🔑 BELANGRIJK: includeorganisations=true zorgt dat organisaties worden meegenomen
            response = requests.get(
                f"{HALO_API_BASE}/Client",
                params={
                    "page": page,
                    "pageSize": 100,
                    "includeorganisations": "true",  # DEZE REGEL IS HET GEHEIM
                    "active": "true"                # Alleen actieve klanten
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            clients_page = data.get("clients", [])
            
            # Verwerk organisatiegegevens
            for client in clients_page:
                if "organisation" in client:
                    # Zorg dat organisatie altijd een dict is
                    if isinstance(client["organisation"], list) and len(client["organisation"]) > 0:
                        client["organisation"] = client["organisation"][0]
                    elif not isinstance(client["organisation"], dict):
                        client["organisation"] = {}
            
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
    log.info(f"🎉 Totaal {len(clients)} klanten + organisaties opgehaald")
    return clients

def fetch_all_sites():
    """Haal ALLE locaties op (geen aanpassingen nodig)"""
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
    """Haal ALLE gebruikers op (geen aanpassingen nodig)"""
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

def normalize_name(name, organisation_name=None):
    """
    Normaliseer namen inclusief organisatiegegevens
    Combineert client-naam en organisatie-naam voor betere matching
    """
    if not name:
        name = ""
    
    # Voeg organisatie toe als beschikbaar
    full_name = name
    if organisation_name and organisation_name != "None":
        full_name += " " + organisation_name
    
    # Stap 1: Naar kleine letters en verwijder voor/achtervoegsel spaties
    full_name = full_name.lower().strip()
    
    # Stap 2: Vervang veelvoorkomende varianten
    full_name = full_name.replace("&amp;", "en")
    full_name = full_name.replace("&", "en")
    full_name = full_name.replace("b.v.", "bv")
    full_name = full_name.replace("b v", "bv")
    full_name = full_name.replace("b.v", "bv")
    full_name = full_name.replace("bv", "bv")
    full_name = full_name.replace("b v", "bv")
    full_name = full_name.replace("b.v", "bv")
    full_name = full_name.replace("b v", "bv")
    full_name = full_name.replace(".", "")
    full_name = full_name.replace(",", "")
    full_name = full_name.replace("-", " ")
    full_name = full_name.replace("*", "")
    full_name = full_name.replace("(", "")
    full_name = full_name.replace(")", "")
    full_name = full_name.replace(":", " ")
    full_name = full_name.replace("  ", " ")
    
    # Stap 3: Verwijder alle niet-alphanumerieke tekens behalve spaties
    full_name = re.sub(r'[^a-z0-9 ]', ' ', full_name)
    
    # Stap 4: Vervang meervoudige spaties door enkele spatie
    full_name = re.sub(r'\s+', ' ', full_name).strip()
    
    return full_name

def get_main_users():
    """Combineer alle data met ULTRA-FLEXIBELE ZOEKOPDRACHTEN voor jouw specifieke Halo"""
    global client_id, bossers_client, site_id, main_site  # Voor gebruik in /users response
    
    # Stap 1: Haal alle benodigde data op
    log.info("🔍 Start met ophalen van klanten, locaties en gebruikers...")
    clients = fetch_all_clients()  # Bevat nu ook organisaties!
    sites = fetch_all_sites()
    users = fetch_all_users()
    
    # Stap 2: Vind de juiste Client ID voor "Bossers & Cnossen" (ULTRA-FLEXIBEL)
    log.info("🔍 Zoek klant 'Bossers & Cnossen' met geavanceerde matching...")
    bossers_client = None
    
    # 🔑 SPECIAAL VOOR JOUW GEVAL: Meer flexibele zoektermen
    bossers_keywords = [
        "boss", "bossers", "b os", "b.o", "b&", "b c", "b.c", "b&c",
        "b en", "b&n", "b n", "b c", "b.c", "b&c", "b en", "b&n", "b n",
        "boss en", "bossers en", "boss &", "bossers &", "bosserscnossen",
        "bossers cnossen", "bossersen", "bossersn", "bossers cn", "bossersc"
    ]
    
    cnossen_keywords = [
        "cno", "cnossen", "cnos", "c.o", "c&", "c c", "c.c", "c&c",
        "c en", "c&n", "c n", "c c", "c.c", "c&c", "c en", "c&n", "c n",
        "cnossen", "cnossen", "cnossen", "cnossen", "cnossen", "cnossen",
        "cnossen", "cnossen", "cnossen", "cnossen", "cnossen", "cnossen"
    ]
    
    # Log alle potentiële matches voor debugging
    potential_matches = []
    for c in clients:
        # Haal organisatie naam op als beschikbaar
        organisation_name = ""
        if "organisation" in c and isinstance(c["organisation"], dict):
            org_name = c["organisation"].get("name", "")
            if org_name and org_name != "None":
                organisation_name = org_name
        
        original_name = c.get("name", "Onbekend")
        normalized_name = normalize_name(original_name, organisation_name)
        
        # 🔑 Verbeterde matching: Controleer op afzonderlijke sleutelwoorden
        has_bossers = any(
            keyword in normalized_name
            for keyword in bossers_keywords
        )
        has_cnossen = any(
            keyword in normalized_name
            for keyword in cnossen_keywords
        )
        
        # Log alle matches voor debugging
        if has_bossers or has_cnossen:
            match_type = []
            if has_bossers: match_type.append("✅ Bossers-match")
            if has_cnossen: match_type.append("✅ Cnossen-match")
            log.info(f"{' '.join(match_type)}: '{original_name}' + Org: '{organisation_name}' → Normalized: '{normalized_name}'")
            
            potential_matches.append({
                "id": c["id"],
                "original_name": original_name,
                "organisation_name": organisation_name,
                "normalized_name": normalized_name,
                "has_bossers": has_bossers,
                "has_cnossen": has_cnossen,
                "full_normalized": normalized_name
            })
            
            # Sla op als potentiële match (alleen als BEIDE delen aanwezig zijn)
            if has_bossers and has_cnossen and not bossers_client:
                bossers_client = c
                log.info(f"🎯 GEVONDEN: Klant '{original_name}' + Org: '{organisation_name}' gematcht als Bossers & Cnossen")
    
    # Als we geen perfecte match vonden, gebruik dan de beste potentiële match
    if not bossers_client and potential_matches:
        # Sorteer op meeste matches (hoogste score)
        potential_matches.sort(key=lambda x: (x["has_bossers"] + x["has_cnossen"]), reverse=True)
        best_match_id = potential_matches[0]["id"]
        
        bossers_client = next((c for c in clients if c["id"] == best_match_id), None)
        if bossers_client:
            org_name = ""
            if "organisation" in bossers_client and isinstance(bossers_client["organisation"], dict):
                org_name = bossers_client["organisation"].get("name", "")
                
            log.warning(f"⚠️ Gebruik BESTE POTENTIËLE MATCH voor klant: {bossers_client['name']} + Org: {org_name}")
    
    if not bossers_client:
        log.error("❌ Klant 'Bossers & Cnossen' NIET GEVONDEN in Halo")
        # Toon alle potentiële matches voor debugging
        if potential_matches:
            log.info("🔍 Potentiële klantnamen gevonden:")
            for match in potential_matches:
                log.info(f" - ID {match['id']}: '{match['original_name']}' + Org: '{match['organisation_name']}' (Normalized: '{match['normalized_name']}')")
        else:
            log.info("🔍 Geen potentiële klantnamen gevonden met 'boss' of 'cno'")
        return []
    
    client_id = int(bossers_client["id"])
    org_name = ""
    if "organisation" in bossers_client and isinstance(bossers_client["organisation"], dict):
        org_name = bossers_client["organisation"].get("name", "")
    
    log.info(f"✅ Gebruik klant-ID: {client_id} (Naam: '{bossers_client['name']}' + Org: '{org_name}')")
    
    # Stap 3: Vind de juiste Site ID voor "Main" (FLEXIBEL)
    log.info("🔍 Zoek locatie 'Main' met flexibele matching...")
    main_site = None
    for s in sites:
        site_name = str(s.get("name", "")).lower().strip()
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
            
            # Haal organisatie naam op voor logging
            org_name = ""
            if "organisation" in bossers_client and isinstance(bossers_client["organisation"], dict):
                org_name = bossers_client["organisation"].get("name", "")
            
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
                "debug_hint": "Deze integratie probeert automatisch alle varianten van 'Bossers & Cnossen' te matchen inclusief organisatienaam"
            }), 500
        
        # Haal client en site namen op voor de response
        client_name = bossers_client["name"]
        org_name = ""
        if "organisation" in bossers_client and isinstance(bossers_client["organisation"], dict):
            org_name = bossers_client["organisation"].get("name", "")
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
        log.info("🔍 /debug endpoint aangeroepen - haal klanten en locaties op")
        clients = fetch_all_clients()  # Bevat nu ook organisaties!
        sites = fetch_all_sites()
        
        # Toon eerste 3 klanten en locaties voor debugging
        sample_clients = [{"id": c["id"], "name": c["name"]} for c in clients[:3]]
        sample_sites = [{"id": s["id"], "name": s["name"]} for s in sites[:3]]
        
        # Zoek naar potentiële Bossers & Cnossen varianten
        bossers_variants = []
        all_candidates = []
        
        for c in clients:
            # Haal organisatie naam op
            organisation_name = ""
            if "organisation" in c and isinstance(c["organisation"], dict):
                org_name = c["organisation"].get("name", "")
                if org_name and org_name != "None":
                    organisation_name = org_name
            
            original_name = c.get("name", "Onbekend")
            normalized_name = normalize_name(original_name, organisation_name)
            
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
                    "id": c["id"],
                    "original_name": original_name,
                    "organisation_name": organisation_name,
                    "normalized_name": normalized_name,
                    "has_bossers": has_bossers,
                    "has_cnossen": has_cnossen
                })
            
            # Check voor alle kandidaten met 'bos' of 'cno'
            if "bos" in normalized_name or "cno" in normalized_name:
                all_candidates.append({
                    "id": c["id"],
                    "client_name": original_name,
                    "organisation_name": organisation_name,
                    "full_normalized": normalized_name
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
            "all_possible_candidates": all_candidates,
            "troubleshooting": [
                "1. Klantnaam kan variëren: 'Bossers & Cnossen', 'B&C', 'Bossers en Cnossen'",
                "2. Organisatie naam is KRIKEND belangrijk - check 'organisation_name' in response",
                "3. Beheerder moet ALLE vinkjes hebben aangevinkt in API-toegang",
                "4. Gebruik 'all_possible_candidates' om de exacte spelling te vinden",
                "5. De integratie combineert nu client-naam en organisatie-naam voor matching"
            ],
            "hint": "Deze integratie gebruikt ULTRA-FLEXIBELE matching voor klantnamen inclusief organisaties"
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
    log.info("✅ Haalt ORGANISATIES op via includeorganisations=true")
    log.info("✅ Filtert alleen ACTIEVE klanten")
    log.info("✅ COMBINEERT NU CLIENT-NAAM EN ORGANISATIE-NAAM VOOR MATCHING")
    log.info("-"*70)
    log.info("👉 VOLG DEZE 2 STAPPEN:")
    log.info("1. Herdeploy deze code naar Render")
    log.info("2. Bezoek EERST /debug om te zien of Bossers & Cnossen wordt gevonden")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
