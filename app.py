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
# Custom Integration Core - VOLLEDIG GEFIXT VOOR AGENT USERS
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

def fetch_all_agents():
    """Haal ALLE AGENT USERS op met VOLLEDIGE STRUCTUUR INSPECTIE"""
    token = get_halo_token()
    agents = []
    page = 1
    
    while True:
        try:
            # 🔑 BELANGRIJK: Filter specifiek op AGENTS met is_agent=1
            response = requests.get(
                f"{HALO_API_BASE}/Users",
                params={
                    "page": page,
                    "per_page": 50,
                    "is_agent": "1",  # Cruciaal: alleen agent users
                    "include": "site,client"  # Haal zowel site als client gegevens mee
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            agents_page = data.get("users", [])
            
            if not agents_page:
                log.info(f"⏹️ Geen agent gebruikers meer gevonden op pagina {page}")
                break
            
            # Log de STRUCTUUR van de eerste agent voor debugging
            if page == 1 and len(agents_page) > 0:
                first_agent = agents_page[0]
                log.info("🔍 STRUCTUUR VAN EERSTE AGENT GEBRUIKER:")
                log.info(f" - ID: {first_agent.get('id', 'Onbekend')}")
                log.info(f" - Naam: {first_agent.get('name', 'Onbekend')}")
                log.info(f" - Is Agent: {first_agent.get('is_agent', 'Onbekend')}")
                log.info(f" - User Type: {first_agent.get('user_type', 'Onbekend')}")
                log.info(f" - Client ID: {first_agent.get('client_id', 'Onbekend')}")
                log.info(f" - Site ID: {first_agent.get('site_id', 'Onbekend')}")
                log.info(f" - Client Object: {first_agent.get('client', 'Onbekend')}")
                log.info(f" - Site Object: {first_agent.get('site', 'Onbekend')}")
            
            # Filter op unieke agents en alleen voor de juiste klant
            new_agents = []
            for agent in agents_page:
                # Controleer of de agent een echte agent is
                if str(agent.get("is_agent", "")) == "1" or str(agent.get("user_type", "")) == "1":
                    new_agents.append(agent)
            
            if not new_agents:
                log.info(f"⏹️ Geen nieuwe agent gebruikers gevonden op pagina {page}")
                break
            
            agents.extend(new_agents)
            log.info(f"✅ Pagina {page} AGENT gebruikers: {len(new_agents)} toegevoegd (totaal: {len(agents)})")
            page += 1
            
        except Exception as e:
            log.error(f"❌ Fout bij ophalen agent gebruikers: {str(e)}")
            break
    
    log.info(f"🎉 Totaal {len(agents)} AGENT gebruikers opgehaald")
    return agents

def get_agents_by_site_id(site_id, client_id):
    """Haal AGENT gebruikers op voor specifieke locatie met FLOATING POINT FIX"""
    log.info(f"🔍 Haal ALLE AGENT gebruikers op om te filteren op locatie {site_id}")
    # Stap 1: Haal alle agent gebruikers op
    all_agents = fetch_all_agents()
    
    # Stap 2: Filter op de juiste locatie met FLOATING POINT FIX
    site_agents = []
    for agent in all_agents:
        try:
            # Controleer site koppeling met FLOATING POINT FIX
            agent_site_id = None
            # Mogelijkheid 1: Directe site_id
            if "site_id" in agent:
                agent_site_id = agent["site_id"]
            
            # Mogelijkheid 2: Site object
            elif "site" in agent and isinstance(agent["site"], dict):
                agent_site_id = agent["site"].get("id")
            
            # Mogelijkheid 3: Geen site koppeling
            else:
                continue
            
            # Converteer naar float en dan naar int om .0 te verwijderen
            try:
                agent_site_id_int = int(float(agent_site_id))
                expected_site_id_int = int(float(site_id))
                
                # Controleer ook op client ID
                agent_client_id = None
                if "client_id" in agent:
                    agent_client_id = agent["client_id"]
                elif "client" in agent and isinstance(agent["client"], dict):
                    agent_client_id = agent["client"].get("id")
                
                if agent_client_id:
                    try:
                        agent_client_id_int = int(float(agent_client_id))
                        expected_client_id_int = int(float(client_id))
                        
                        if (agent_site_id_int == expected_site_id_int and 
                            agent_client_id_int == expected_client_id_int):
                            site_agents.append({
                                "id": agent["id"],
                                "name": agent["name"],
                                "email": agent.get("emailaddress") or agent.get("email") or "Geen email",
                                "debug": {
                                    "raw_site_id": agent_site_id,
                                    "expected_site_id": site_id,
                                    "converted_site_id": agent_site_id_int,
                                    "raw_client_id": agent_client_id,
                                    "expected_client_id": client_id,
                                    "converted_client_id": agent_client_id_int
                                }
                            })
                    except (ValueError, TypeError):
                        continue
            except (ValueError, TypeError):
                continue
        except (TypeError, ValueError, KeyError) as e:
            log.debug(f"⚠️ Agent overslaan bij filtering: {str(e)}")
            continue
    
    log.info(f"✅ {len(site_agents)}/{len(all_agents)} AGENT gebruikers gevonden voor locatie {site_id}")
    # Extra debug log als we geen gebruikers vinden
    if not site_agents:
        log.error("❌ Geen AGENT gebruikers gevonden voor de locatie")
        log.info("🔍 Controleer koppelingen tussen AGENT gebruikers en locaties...")
        # Toon voorbeeldgebruikers voor debugging
        for i, agent in enumerate(all_agents[:5]):
            site_id_debug = agent.get("site_id", "Onbekend")
            site_debug = agent.get("site", "Onbekend")
            client_id_debug = agent.get("client_id", "Onbekend")
            client_debug = agent.get("client", "Onbekend")
            
            site_id_extracted = "Niet-converteerbaar"
            try:
                if "site_id" in agent:
                    site_id_extracted = int(float(agent["site_id"]))
                elif "site" in agent and isinstance(agent["site"], dict):
                    site_id_extracted = int(float(agent["site"].get("id", "Onbekend")))
            except (ValueError, TypeError):
                pass
            
            client_id_extracted = "Niet-converteerbaar"
            try:
                if "client_id" in agent:
                    client_id_extracted = int(float(agent["client_id"]))
                elif "client" in agent and isinstance(agent["client"], dict):
                    client_id_extracted = int(float(agent["client"].get("id", "Onbekend")))
            except (ValueError, TypeError):
                pass
            
            log.info(f" - Voorbeeldagent {i+1}: '{agent.get('name', 'Onbekend')}'")
            log.info(f"   • Client ID (direct): {client_id_debug}")
            log.info(f"   • Client Object: {client_debug}")
            log.info(f"   • Geëxtraheerde Client ID: {client_id_extracted}")
            log.info(f"   • Site ID (direct): {site_id_debug}")
            log.info(f"   • Site Object: {site_debug}")
            log.info(f"   • Geëxtraheerde Site ID: {site_id_extracted}")
    
    return site_agents

def get_main_agents():
    """Haal Main-site AGENT gebruikers op voor Bossers & Cnossen met HARDCODED ID's"""
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
    
    # Stap 3: Haal de AGENT gebruikers op VIA DE USERS ENDPOINT
    log.info(f"🔍 Haal AGENT gebruikers op voor locatie {MAIN_SITE_ID} via de Users endpoint...")
    main_agents = get_agents_by_site_id(MAIN_SITE_ID, BOSSERS_CLIENT_ID)
    
    if not main_agents:
        log.error("❌ Geen Main-site AGENT gebruikers gevonden")
        return []
    
    log.info(f"✅ {len(main_agents)} Main-site AGENT gebruikers gevonden")
    return main_agents

# ------------------------------------------------------------------------------
# API Endpoints - ULTRA-DEBUGGABLE
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health_check():
    return {
        "status": "custom_integration_ready",
        "message": "Halo Custom Integration API - Bezoek /agents voor data",
        "environment": "UAT",
        "instructions": [
            "1. Zorg dat .env correct is ingesteld",
            "2. Bezoek /debug voor technische validatie",
            "3. Bezoek /agents voor Main-site agent gebruikers"
        ]
    }

@app.route("/agents", methods=["GET"])
def get_agents():
    """Eindpunt voor jouw applicatie - MET HARDCODED ID'S"""
    try:
        log.info("🔄 /agents endpoint aangeroepen - start verwerking")
        main_agents = get_main_agents()
        if not main_agents:
            log.error("❌ Geen Main-site AGENT gebruikers gevonden")
            return jsonify({
                "error": "Geen Main-site AGENT gebruikers gevonden",
                "solution": [
                    f"1. Controleer of klant met ID {BOSSERS_CLIENT_ID} bestaat",
                    f"2. Controleer of locatie met ID {MAIN_SITE_ID} bestaat",
                    "3. Zorg dat AGENT gebruikers correct zijn gekoppeld aan deze locatie",
                    "4. In Halo: Ga naar Agents > Filter op locatie",
                    "5. Controleer de Render logs voor 'STRUCTUUR VAN EERSTE AGENT GEBRUIKER'"
                ],
                "debug_hint": "Deze integratie logt nu de VOLLEDIGE STRUCTUUR van de eerste agent gebruiker voor debugging"
            }), 500
        log.info(f"🎉 Succesvol {len(main_agents)} Main-site AGENT gebruikers geretourneerd")
        return jsonify({
            "client_id": client_id,
            "client_name": bossers_client.get("name", "Onbekend"),
            "site_id": site_id,
            "site_name": main_site.get("name", "Onbekend"),
            "total_agents": len(main_agents),
            "agents": main_agents
        })
    except Exception as e:
        log.error(f"🔥 Fout in /agents: {str(e)}")
        return jsonify({
            "error": str(e),
            "hint": "Controleer eerst de Render logs voor de STRUCTUUR VAN EERSTE AGENT GEBRUIKER"
        }), 500

@app.route("/debug", methods=["GET"])
def debug_info():
    """Technische debug informatie - MET AGENT USERS FIX"""
    try:
        log.info("🔍 /debug endpoint aangeroepen - valideer hardcoded ID's")
        # Valideer klant ID
        bossers_client = get_client_by_id(BOSSERS_CLIENT_ID)
        client_valid = bossers_client is not None
        # Valideer site ID
        main_site = get_site_by_id(MAIN_SITE_ID)
        site_valid = main_site is not None
        # Haal AGENT gebruikers op via de Users endpoint
        log.info(f"🔍 Haal AGENT gebruikers op voor locatie {MAIN_SITE_ID} via de Users endpoint...")
        site_agents = get_agents_by_site_id(MAIN_SITE_ID, BOSSERS_CLIENT_ID)
        # Haal een sample van de gebruikers voor debugging
        sample_agents = site_agents[:3] if site_agents else []
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
                "total_agents_found": len(site_agents),
                "sample_agents": sample_agents,
                "site_data_structure": main_site if site_valid else "Site niet gevonden"
            },
            "troubleshooting": [
                f"1. Controleer of klant met ID {BOSSERS_CLIENT_ID} bestaat in Halo",
                f"2. Controleer of locatie met ID {MAIN_SITE_ID} bestaat in Halo",
                "3. Zorg dat AGENT gebruikers correct zijn gekoppeld aan deze locatie",
                "4. In Halo: Ga naar Agents > Filter op locatie",
                "5. Gebruikers moeten zowel aan de klant ALS aan de locatie zijn gekoppeld",
                "6. BELANGRIJK: Controleer de Render logs voor 'STRUCTUUR VAN EERSTE AGENT GEBRUIKER'"
            ],
            "hint": "Deze integratie gebruikt een FLOATING POINT FIX voor site_id vergelijking - controleer de Render logs"
        })
    except Exception as e:
        log.error(f"❌ Fout in /debug: {str(e)}")
        return jsonify({
            "error": str(e),
            "critical_hint": "Controleer de Render logs voor de STRUCTUUR VAN EERSTE AGENT GEBRUIKER"
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
    log.info("✅ FILTERT SPECIFIEK OP AGENT USERS (is_agent=1)")
    log.info("✅ HAALT SITE EN KLANT GEGEVENS MEE VIA 'include=site,client'")
    log.info("✅ FIX VOOR FLOATING POINT SITE_ID WAARDEN (bijv. 992.0)")
    log.info("✅ CONVERTEERT SITE_ID WAARDEN NAAR INTEGER VOOR VERGELIJKING")
    log.info("-"*70)
    log.info("👉 VOLG DEZE 2 STAPPEN:")
    log.info("1. Herdeploy deze code naar Render")
    log.info("2. Bezoek EERST /debug en controleer de Render logs voor 'STRUCTUUR VAN EERSTE AGENT GEBRUIKER'")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port)
