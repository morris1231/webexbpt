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
    """Haal ALLE klanten op met VOLLEDIGE PAGINERING en ORGANISATIE-EXTRACTIE"""
    token = get_halo_token()
    clients = []
    page = 1
    total_fetched = 0
    
    while True:
        try:
            # 🔑 BELANGRIJK: Gebruik pageSize=50 (niet 100) want UAT geeft max 50 terug
            response = requests.get(
                f"{HALO_API_BASE}/Client",
                params={
                    "page": page,
                    "pageSize": 50,  # CORRECTIE: UAT ondersteunt max 50 per pagina
                    "includeorganisations": "true",
                    "active": "true"
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # Log de RAW API response voor debugging
            log.debug(f"🔍 RAW API response voor pagina {page}: {data.keys()}")
            
            clients_page = data.get("clients", [])
            
            if not clients_page:
                log.info(f"⏹️ Geen klanten meer gevonden op pagina {page}")
                break
                
            # 🔑 ULTRA-ROBUSTE extractie van organisatiegegevens specifiek voor jouw UAT
            for client in clients_page:
                # In jouw specifieke UAT zit de organisatie in een array onder "Organisations"
                # en de naam zit in een veld "Name" (met hoofdletter)
                organisation_name = ""
                
                # Specifiek voor jouw UAT: Check op "Organisations" (met hoofdletter) en "Name"
                if "Organisations" in client and isinstance(client["Organisations"], list) and len(client["Organisations"]) > 0:
                    first_org = client["Organisations"][0]
                    if isinstance(first_org, dict) and "Name" in first_org:
                        organisation_name = first_org["Name"]
                
                # Sla de organisatie naam op voor later gebruik
                client["organisation_name"] = organisation_name
                
                # Log de specifieke client data voor debugging
                log.debug(f"🔍 Client gevonden: ID={client.get('id', 'Onbekend')} | Naam='{client.get('name', 'Onbekend')}' | Org='{organisation_name}'")
            
            clients.extend(clients_page)
            total_fetched += len(clients_page)
            
            log.info(f"✅ Pagina {page} klanten: {len(clients_page)} toegevoegd (totaal: {total_fetched})")
            
            # 🔑 BELANGRIJK: Blijf pagineren totdat er geen resultaten meer zijn
            # (niet afhankelijk van pageSize omdat UAT max 50 teruggeeft)
            if len(clients_page) < 50:
                break
                
            page += 1
            # Beveiliging tegen oneindige loops
            if page > 100:
                log.warning("⚠️ Te veel paginas - stoppen met pagineren")
                break
                
        except Exception as e:
            log.error(f"❌ Fout bij ophalen klanten: {str(e)}")
            break
            
    log.info(f"🎉 Totaal {len(clients)} klanten opgehaald (inclusief organisatiegegevens)")
    return clients

def fetch_all_sites():
    """Haal ALLE locaties op met VOLLEDIGE PAGINERING"""
    token = get_halo_token()
    sites = []
    page = 1
    total_fetched = 0
    
    while True:
        try:
            response = requests.get(
                f"{HALO_API_BASE}/Site",
                params={
                    "page": page,
                    "pageSize": 50,  # CORRECTIE: UAT ondersteunt max 50 per pagina
                    "active": "true"
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            sites_page = data.get("sites", [])
            
            if not sites_page:
                break
                
            sites.extend(sites_page)
            total_fetched += len(sites_page)
            
            log.info(f"✅ Pagina {page} locaties: {len(sites_page)} toegevoegd (totaal: {total_fetched})")
            
            if len(sites_page) < 50:
                break
                
            page += 1
            if page > 100:
                break
        except Exception as e:
            log.error(f"❌ Fout bij ophalen locaties: {str(e)}")
            break
            
    log.info(f"🎉 Totaal {len(sites)} locaties opgehaald")
    return sites

def fetch_all_users():
    """Haal ALLE gebruikers op met VOLLEDIGE PAGINERING"""
    token = get_halo_token()
    users = []
    page = 1
    total_fetched = 0
    
    while True:
        try:
            response = requests.get(
                f"{HALO_API_BASE}/User",
                params={
                    "page": page,
                    "pageSize": 50,  # CORRECTIE: UAT ondersteunt max 50 per pagina
                    "active": "true"
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            users_page = data.get("users", [])
            
            if not users_page:
                break
                
            users.extend(users_page)
            total_fetched += len(users_page)
            
            log.info(f"✅ Pagina {page} gebruikers: {len(users_page)} toegevoegd (totaal: {total_fetched})")
            
            if len(users_page) < 50:
                break
                
            page += 1
            if page > 100:
                break
        except Exception as e:
            log.error(f"❌ Fout bij ophalen gebruikers: {str(e)}")
            break
            
    log.info(f"🎉 Totaal {len(users)} gebruikers opgehaald")
    return users

def normalize_name(name, organisation_name=None):
    """
    Normaliseer namen met ULTRA-ROBUSTE afhandeling specifiek voor jouw UAT
    """
    # Combineer client en organisatie namen
    full_name = (name or "").strip()
    
    # Voeg organisatie toe als beschikbaar
    if organisation_name and str(organisation_name).strip() and str(organisation_name).strip() != "None":
        # Voeg alleen toe als het niet al in de client naam zit
        if organisation_name.lower() not in name.lower():
            full_name += " " + str(organisation_name).strip()
    
    # Stap 1: Basis schoonmaak
    full_name = full_name.lower()
    
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
        full_name = full_name.replace(old, new)
    
    # Stap 3: Verwijder alle resterende niet-alphanumerieke tekens
    full_name = re.sub(r'[^a-z0-9 ]', ' ', full_name)
    
    # Stap 4: Schoonmaak spaties
    full_name = re.sub(r'\s+', ' ', full_name).strip()
    
    return full_name

def get_main_users():
    """Combineer alle data met ULTRA-FLEXIBELE ZOEKOPDRACHTEN specifiek voor jouw UAT"""
    global client_id, bossers_client, site_id, main_site
    
    # Stap 1: Haal alle benodigde data op
    log.info("🔍 Start met ophalen van klanten, locaties en gebruikers...")
    clients = fetch_all_clients()
    sites = fetch_all_sites()
    users = fetch_all_users()
    
    # Stap 2: Verbeterde klantzoekfunctie met ULTRA-ROBUSTE matching
    log.info("🔍 Zoek klant 'Bossers & Cnossen' met ULTRA-FLEXIBELE matching...")
    bossers_client = None
    
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
    
    potential_matches = []
    for c in clients:
        # Haal organisatie naam op met ULTRA-VEILIGE afhandeling
        organisation_name = c.get("organisation_name", "")
        
        # Log de RAW data voor debugging
        client_name = c.get("name", "Onbekend")
        log.debug(f"🔍 RAW Client: '{client_name}' | Org: '{organisation_name}'")
        
        # Normaliseer met ULTRA-ROBUSTE methode
        normalized_name = normalize_name(client_name, organisation_name)
        
        # 🔑 ULTRA-FLEXIBELE matching - check op beide delen
        has_bossers = any(keyword in normalized_name for keyword in bossers_keywords)
        has_cnossen = any(keyword in normalized_name for keyword in cnossen_keywords)
        
        # Log alles voor debugging
        if has_bossers or has_cnossen:
            match_type = []
            if has_bossers: match_type.append("✅ Bossers-match")
            if has_cnossen: match_type.append("✅ Cnossen-match")
            log.info(f"{' '.join(match_type)}: '{client_name}' + Org: '{organisation_name}' → '{normalized_name}'")
            
            potential_matches.append({
                "id": c["id"],
                "client_name": client_name,
                "organisation_name": organisation_name,
                "normalized_name": normalized_name,
                "has_bossers": has_bossers,
                "has_cnossen": has_cnossen
            })
        
        # Sla op als potentiële match (alleen als BEIDE delen aanwezig zijn)
        if has_bossers and has_cnossen and not bossers_client:
            bossers_client = c
            log.info(f"🎯 GEVONDEN: Klant '{client_name}' + Org: '{organisation_name}' gematcht als Bossers & Cnossen")
    
    # Als we geen perfecte match vonden, gebruik dan de beste potentiële match
    if not bossers_client and potential_matches:
        log.warning("⚠️ Geen perfecte match gevonden, probeer beste potentiële match...")
        # Sorteer op meeste matches
        potential_matches.sort(key=lambda x: (x["has_bossers"] + x["has_cnossen"]), reverse=True)
        best_match_id = potential_matches[0]["id"]
        
        bossers_client = next((c for c in clients if c["id"] == best_match_id), None)
        if bossers_client:
            org_name = bossers_client.get("organisation_name", "")
            
            log.warning(f"⚠️ Gebruik BESTE POTENTIËLE MATCH voor klant: {bossers_client['name']} + Org: {org_name}")
    
    if not bossers_client:
        log.error("❌ Klant 'Bossers & Cnossen' NIET GEVONDEN in Halo")
        # Toon ALLE klanten voor debugging
        log.info("🔍 Alle klanten in Halo (voor debugging):")
        for c in clients[:50]:  # Meer voor overzicht
            org_name = c.get("organisation_name", "")
            log.info(f" - Client: '{c.get('name', 'Onbekend')}' + Org: '{org_name}'")
        
        return []
    
    client_id = int(bossers_client["id"])
    org_name = bossers_client.get("organisation_name", "")
    
    log.info(f"✅ Gebruik klant-ID: {client_id} (Naam: '{bossers_client['name']}' + Org: '{org_name}')")
    
    # Stap 3: Vind de juiste Site ID voor "Main"
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
    
    # Stap 4: Filter gebruikers
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
            org_name = bossers_client.get("organisation_name", "")
            
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
        org_name = bossers_client.get("organisation_name", "")
        
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
        clients = fetch_all_clients()
        sites = fetch_all_sites()
        
        # Toon eerste 5 klanten en locaties voor debugging
        sample_clients = [{"id": c["id"], "name": c["name"], "organisation": c.get("organisation_name", "")} for c in clients[:5]]
        sample_sites = [{"id": s["id"], "name": s["name"]} for s in sites[:5]]
        
        # Zoek naar potentiële Bossers & Cnossen varianten
        bossers_variants = []
        all_candidates = []
        
        for c in clients:
            # Haal organisatie naam op
            organisation_name = c.get("organisation_name", "")
            
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
                    "client_name": original_name,
                    "organisation_name": organisation_name,
                    "normalized_name": normalized_name,
                    "has_bossers": has_bossers,
                    "has_cnossen": has_cnossen
                })
            
            # Check voor alle kandidaten met 'bos' of 'cno' (ULTRA-ROBUST)
            if "bos" in normalized_name or "cno" in normalized_name or "boss" in normalized_name or "cnos" in normalized_name:
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
                "5. De integratie combineert nu client-naam en organisatie-naam voor matching",
                "6. API gebruikt 'Organisations' (met hoofdletter) en 'Name' (met hoofdletter) in jouw UAT"
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
    log.info("✅ VOLLEDIGE PAGINERING (UAT geeft max 50 per pagina)")
    log.info("✅ CORRECTE ORGANISATIE-EXTRACTIE VOOR JOUW SPECIFIEKE UAT")
    log.info("✅ ULTRA-DEBUGGABLE MET VOLLEDIGE RAW DATA LOGGING")
    log.info("-"*70)
    log.info("👉 VOLG DEZE 2 STAPPEN:")
    log.info("1. Herdeploy deze code naar Render")
    log.info("2. Bezoek EERST /debug om te zien of Bossers & Cnossen wordt gevonden")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
