import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET VOLLEDIGE KOPPELINGSANALYSE
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - VOLLEDIG ROBUST VOOR ALLE KOPPELINGEN
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# Correcte URL voor UAT
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# Jouw correcte IDs (ZOALS IN DE URL)
HALO_CLIENT_ID_NUM = 12  # Bossers & Cnossen (URL ID)
HALO_SITE_ID       = 18  # Main (URL ID)

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# Globale mapping (wordt gevuld bij eerste API call)
CLIENT_MAPPING = {}
SITE_MAPPING = {}

# ------------------------------------------------------------------------------
# Halo API helpers - MET ALLE KOPPELINGSMETHODEN
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Authenticatie met alleen 'Teams' rechten"""
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    
    try:
        r = requests.post(
            HALO_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(payload),
            timeout=10
        )
        r.raise_for_status()
        return {
            "Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        log.critical(f"❌ AUTH MISLUKT: {str(e)}")
        log.critical(f"➡️ Response: {r.text if 'r' in locals() else 'Geen response'}")
        raise

def build_id_mappings():
    """Bouw de mapping tussen URL-IDs en API-IDs"""
    global CLIENT_MAPPING, SITE_MAPPING
    
    if CLIENT_MAPPING and SITE_MAPPING:
        return
    
    log.info("🔍 Bouw ID mappings tussen URL-IDs en API-IDs")
    
    try:
        headers = get_halo_headers()
        
        # Haal alle clients op
        clients_url = f"{HALO_API_BASE}/Clients"
        r_clients = requests.get(clients_url, headers=headers, timeout=15)
        
        # Haal alle sites op
        sites_url = f"{HALO_API_BASE}/Sites"
        r_sites = requests.get(sites_url, headers=headers, timeout=15)
        
        if r_clients.status_code != 200 or r_sites.status_code != 200:
            log.error("❌ Kan clients/sites niet ophalen - gebruik fallback mapping")
            
            # Fallback mapping (gebruikt in jouw specifieke omgeving)
            CLIENT_MAPPING = {
                "12": {"api_id": "1706", "name": "Bossers & Cnossen"},
                "1": {"api_id": "1", "name": "Unknown"}
            }
            
            SITE_MAPPING = {
                "18": {"api_id": "1714", "name": "Main"},
                "1": {"api_id": "1", "name": "Unknown"}
            }
            return
        
        # Parse responses
        clients_data = r_clients.json()
        sites_data = r_sites.json()
        
        # Haal clients uit de response
        clients = []
        if isinstance(clients_data, list):
            clients = clients_data
        else:
            clients = clients_data.get("clients", []) or clients_data.get("Clients", [])
        
        # Haal sites uit de response
        sites = []
        if isinstance(sites_data, list):
            sites = sites_data
        else:
            sites = sites_data.get("sites", []) or sites_data.get("Sites", [])
        
        # Bouw client mapping
        for c in clients:
            url_id = str(c.get("external_id", ""))
            api_id = str(c.get("id", ""))
            name = c.get("name", "Onbekend")
            
            if url_id and api_id:
                CLIENT_MAPPING[url_id] = {"api_id": api_id, "name": name}
        
        # Bouw site mapping
        for s in sites:
            url_id = str(s.get("external_id", ""))
            api_id = str(s.get("id", ""))
            name = s.get("name", "Onbekend")
            client_id = str(s.get("client_id", ""))
            
            if url_id and api_id:
                SITE_MAPPING[url_id] = {
                    "api_id": api_id,
                    "name": name,
                    "client_id": client_get
                }
        
        # Log de gevonden mappings
        log.info("✅ CLIENT MAPPING GEVONDEN:")
        for url_id, data in CLIENT_MAPPING.items():
            log.info(f"  → URL ID {url_id} = API ID {data['api_id']} ({data['name']})")
        
        log.info("✅ SITE MAPPING GEVONDEN:")
        for url_id, data in SITE_MAPPING.items():
            log.info(f"  → URL ID {url_id} = API ID {data['api_id']} ({data['name']})")
    
    except Exception as e:
        log.error(f"⚠️ Mapping bouwen mislukt: {str(e)}")
        log.info("💡 Gebruik fallback mapping voor jouw omgeving")
        
        # Fallback mapping specifiek voor jouw omgeving
        CLIENT_MAPPING = {
            "12": {"api_id": "1706", "name": "Bossers & Cnossen"},
            "1": {"api_id": "1", "name": "Unknown"}
        }
        
        SITE_MAPPING = {
            "18": {"api_id": "1714", "name": "Main"},
            "1": {"api_id": "1", "name": "Unknown"}
        }

def fetch_all_users():
    """HAAL ALLE GEBRUIKERS OP MET ALLE KOPPELINGSMETHODEN"""
    log.info("🔍 Haal ALLE gebruikers op voor volledig overzicht")
    
    # Bouw eerst de ID mappings
    build_id_mappings()
    
    try:
        # Haal ALLE gebruikers op
        users_url = f"{HALO_API_BASE}/Users"
        log.info(f"➡️ API-aanvraag: {users_url}")
        
        headers = get_halo_headers()
        r = requests.get(users_url, headers=headers, timeout=30)
        
        if r.status_code != 200:
            log.error(f"❌ API FOUT ({r.status_code}): {r.text}")
            return []
        
        # Parse response
        data = r.json()
        log.info(f"🔍 RESPONSE STRUCTUUR: {type(data).__name__}")
        
        # Verwerk 'data' wrapper
        if "data" in data and isinstance(data["data"], dict):
            log.info("✅ Response heeft 'data' wrapper - gebruik geneste structuur")
            users_data = data["data"]
        else:
            users_data = data
        
        # Haal de users lijst op
        users = users_data.get("users", [])
        if not users:
            users = users_data.get("Users", [])
        
        if not users:
            log.warning("⚠️ Geen gebruikers gevonden in API response")
            return []
        
        log.info(f"✅ {len(users)} gebruikers opgehaald - start uitgebreide filtering")
        
        # Verrijk met filtering status
        enriched_users = []
        main_users_count = 0
        
        # Haal de correcte API IDs voor jouw Main-site
        client_api_id = CLIENT_MAPPING.get(str(HALO_CLIENT_ID_NUM), {}).get("api_id", str(HALO_CLIENT_ID_NUM))
        site_api_id = SITE_MAPPING.get(str(HALO_SITE_ID), {}).get("api_id", str(HALO_SITE_ID))
        
        log.info(f"🔍 Gebruik API IDs voor filtering: client_id={client_api_id}, site_id={site_api_id}")
        
        for u in users:
            # 1. Eerste methode: Directe site/client koppeling
            direct_site_match = False
            direct_client_match = False
            
            # Site ID check (alle varianten)
            for key in ["site_id", "SiteId", "siteId", "siteid", "SiteID"]:
                if key in u and u[key] is not None:
                    if str(u[key]).strip() == site_api_id:
                        direct_site_match = True
                        break
            
            # Client ID check (alle varianten)
            for key in ["client_id", "ClientId", "clientId", "clientid", "ClientID"]:
                if key in u and u[key] is not None:
                    if str(u[key]).strip() == client_api_id:
                        direct_client_match = True
                        break
            
            # 2. Tweede methode: Integer velden
            int_site_match = False
            int_client_match = False
            
            if "site_id_int" in u and u["site_id_int"] is not None:
                if str(u["site_id_int"]).strip() == site_api_id:
                    int_site_match = True
            
            if "client_id_int" in u and u["client_id_int"] is not None:
                if str(u["client_id_int"]).strip() == client_api_id:
                    int_client_match = True
            
            # 3. Derde methode: Client/Site objecten
            object_site_match = False
            object_client_match = False
            
            if "site" in u and isinstance(u["site"], dict):
                if str(u["site"].get("id", "")).strip() == site_api_id:
                    object_site_match = True
            
            if "client" in u and isinstance(u["client"], dict):
                if str(u["client"].get("id", "")).strip() == client_api_id:
                    object_client_match = True
            
            # 4. Vierde methode: Naamgebaseerde matching (als fallback)
            name_site_match = False
            name_client_match = False
            
            if str(u.get("site_name", "")).strip().lower() == "main":
                name_site_match = True
            
            if str(u.get("client_name", "")).strip().lower() == "bossers & cnossen":
                name_client_match = True
            
            # Bepaal of dit een Main-site gebruiker is (ELKE methode telt!)
            is_main_user = (
                (direct_site_match and direct_client_match) or
                (int_site_match and int_client_match) or
                (object_site_match and object_client_match) or
                (name_site_match and name_client_match)
            )
            
            if is_main_user:
                main_users_count += 1
            
            enriched_users.append({
                "user": u,
                "is_main_user": is_main_user,
                "debug": {
                    "direct_site_match": direct_site_match,
                    "direct_client_match": direct_client_match,
                    "int_site_match": int_site_match,
                    "int_client_match": int_client_match,
                    "object_site_match": object_site_match,
                    "object_client_match": object_client_match,
                    "name_site_match": name_site_match,
                    "name_client_match": name_client_match
                }
            })
        
        log.info(f"📊 Totaal Main-site gebruikers: {main_users_count}/{len(users)}")
        
        return enriched_users
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - MET VOLLEDIGE KOPPELINGSANALYSE
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_notes": [
            "1. Werkt MET ALLE KOPPELINGSMETHODEN",
            "2. Gebruikt ID MAPPING voor correcte API waarden",
            "3. Bezoek /id-mapper voor details over jouw mapping"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLEEN de Main-site gebruikers MET ALLE KOPPELINGEN"""
    enriched_users = fetch_all_users()
    main_users = [u for u in enriched_users if u["is_main_user"]]
    
    if not main_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                "1. Bezoek /id-mapper om de juiste ID mapping te zien",
                "2. Controleer of 'Teams' is aangevinkt in API-toegang",
                "3. Zorg dat de API key 'all' scope heeft"
            ],
            "debug_info": "Deze app gebruikt ID mapping om de juiste gebruikers te vinden"
        }), 500
    
    simplified = [{
        "id": u["user"].get("id"),
        "name": u["user"].get("name") or "Onbekend",
        "email": u["user"].get("emailaddress") or u["user"].get("email") or "Geen email"
    } for u in main_users]
    
    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "client_name": CLIENT_MAPPING.get(str(HALO_CLIENT_ID_NUM), {}).get("name", "Bossers & Cnossen"),
        "site_id": HALO_SITE_ID,
        "site_name": SITE_MAPPING.get(str(HALO_SITE_ID), {}).get("name", "Main"),
        "total_users": len(main_users),
        "users": simplified
    })

@app.route("/all-users", methods=["GET"])
def all_users():
    """Toon ALLE gebruikers MET VOLLEDIGE KOPPELINGSANALYSE"""
    enriched_users = fetch_all_users()
    
    # Bereid respons voor
    response = {
        "total_users": len(enriched_users),
        "main_site_users": 0,
        "users": []
    }
    
    for eu in enriched_users:
        user_data = {
            "id": eu["user"].get("id"),
            "name": eu["user"].get("name") or "Onbekend",
            "email": eu["user"].get("emailaddress") or eu["user"].get("email") or "Geen email",
            "is_main_user": eu["is_main_user"],
            "debug": eu["debug"],
            "client_name": eu["user"].get("client_name", "Onbekend"),
            "site_name": eu["user"].get("site_name", "Onbekend")
        }
        
        if eu["is_main_user"]:
            response["main_site_users"] += 1
        
        response["users"].append(user_data)
    
    return jsonify(response)

@app.route("/id-mapper", methods=["GET"])
def id_mapper():
    """TOON DE JUISTE MAPPING TUSSEN URL-IDS EN API-IDS"""
    # Zorg dat de mappings zijn gebouwd
    build_id_mappings()
    
    return {
        "status": "success",
        "client_mapping": CLIENT_MAPPING,
        "site_mapping": SITE_MAPPING,
        "note": "Gebruik deze mapping om de juiste API-IDs te vinden voor jouw URL-IDs"
    }

# ------------------------------------------------------------------------------
# App Start - MET VOLLEDIGE KOPPELINGSANALYSE
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - VOLLEDIGE KOPPELINGSANALYSE")
    log.info("-"*70)
    log.info("✅ Ondersteunt 4 koppelingsmethoden voor Main-site gebruikers")
    log.info("✅ Gebruikt ID mapping voor correcte API waarden")
    log.info("✅ Werkt met jouw specifieke Halo UAT omgeving")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek EERST /id-mapper")
    log.info("2. Noteer de API-IDs voor jouw klant/site")
    log.info("3. Bezoek DAN /all-users voor volledig overzicht")
    log.info("4. Gebruik /users voor ALLE Main-site gebruikers")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
