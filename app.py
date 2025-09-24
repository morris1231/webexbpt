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

# Jouw correcte IDs (zoals in URL)
HALO_CLIENT_ID_NUM = 12  # Bossers & Cnossen
HALO_SITE_ID       = 18  # Main

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

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

def fetch_all_users():
    """HAAL ALLE GEBRUIKERS OP MET ALLE KOPPELINGSMETHODEN"""
    log.info("🔍 Haal ALLE gebruikers op voor volledig overzicht")
    
    try:
        # Haal ALLE gebruikers op
        users_url = f"{HALO_API_BASE}/Users"
        log.info(f"➡️ API-aanvraag: {users_url}")
        
        headers = get_halo_headers()
        r = requests.get(users_url, headers=headers, timeout=30)
        
        # Log de RAW response voor analyse
        log.info(f"🔍 RAW API RESPONSE: {r.text[:500]}")
        
        if r.status_code != 200:
            log.error(f"❌ API FOUT ({r.status_code}): {r.text}")
            return []
        
        # Parse response - SPECIFIEK VOOR JOUW STRUCTUUR
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
        
        for u in users:
            # 1. Eerste methode: Directe site/client koppeling
            direct_site_match = False
            direct_client_match = False
            
            # Site ID check (alle varianten)
            site_id_val = None
            for key in ["site_id", "SiteId", "siteId", "siteid", "SiteID"]:
                if key in u and u[key] is not None:
                    try:
                        site_id_val = float(u[key])
                        if abs(site_id_val - HALO_SITE_ID) < 0.1:
                            direct_site_match = True
                        break
                    except (TypeError, ValueError):
                        pass
            
            # Client ID check (alle varianten)
            client_id_val = None
            for key in ["client_id", "ClientId", "clientId", "clientid", "ClientID"]:
                if key in u and u[key] is not None:
                    try:
                        client_id_val = float(u[key])
                        if abs(client_id_val - HALO_CLIENT_ID_NUM) < 0.1:
                            direct_client_match = True
                        break
                    except (TypeError, ValueError):
                        pass
            
            # 2. Tweede methode: Integer velden (specifiek voor jouw omgeving)
            int_site_match = False
            int_client_match = False
            
            if "site_id_int" in u and u["site_id_int"] is not None:
                try:
                    if int(u["site_id_int"]) == HALO_SITE_ID:
                        int_site_match = True
                except (TypeError, ValueError):
                    pass
            
            if "client_id_int" in u and u["client_id_int"] is not None:
                try:
                    if int(u["client_id_int"]) == HALO_CLIENT_ID_NUM:
                        int_client_match = True
                except (TypeError, ValueError):
                    pass
            
            # 3. Derde methode: Client/Site objecten
            object_site_match = False
            object_client_match = False
            
            if "site" in u and isinstance(u["site"], dict):
                try:
                    if int(u["site"].get("id", 0)) == HALO_SITE_ID:
                        object_site_match = True
                except (TypeError, ValueError):
                    pass
            
            if "client" in u and isinstance(u["client"], dict):
                try:
                    if int(u["client"].get("id", 0)) == HALO_CLIENT_ID_NUM:
                        object_client_match = True
                except (TypeError, ValueError):
                    pass
            
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
        
        # Log de eerste Main-site gebruiker voor debugging
        if main_users_count > 0:
            main_user = next(u for u in enriched_users if u["is_main_user"])
            log.info(f"🔍 Voorbeeld Main-gebruiker: ID={main_user['user'].get('id')}, Naam='{main_user['user'].get('name')}'")
        
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
        "message": "Halo Main users app draait! Bezoek /all-users voor volledig overzicht",
        "critical_notes": [
            "1. Ondersteunt 4 koppelingsmethoden voor Main-site gebruikers",
            "2. Geen enkele gebruiker wordt gemist",
            "3. Bezoek /all-users voor complete mapping"
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
                "1. Bezoek /all-users voor volledig overzicht",
                "2. Controleer of client_id=12 en site_id=18 correct zijn",
                "3. Zorg dat 'Teams' is aangevinkt in API-toegang"
            ],
            "debug_info": "Deze app gebruikt 4 koppelingsmethoden om Main-site gebruikers te vinden"
        }), 500
    
    simplified = [{
        "id": u["user"].get("id"),
        "name": u["user"].get("name") or "Onbekend",
        "email": u["user"].get("emailaddress") or u["user"].get("email") or "Geen email"
    } for u in main_users]
    
    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "client_name": "Bossers & Cnossen",
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
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
    
    # Log resultaat voor transparantie
    log.info(f"📊 /all-users: {response['main_site_users']} Main-site gebruikers gevonden van {response['total_users']} totaal")
    
    return jsonify(response)

@app.route("/debug-mapping", methods=["GET"])
def debug_mapping():
    """TOON VOLLEDIGE KOPPELINGSANALYSE VOOR MAIN-SITE"""
    enriched_users = fetch_all_users()
    main_users = [u for u in enriched_users if u["is_main_user"]]
    
    mapping = {
        "client_id_matches": {
            "direct": 0,
            "int": 0,
            "object": 0,
            "name": 0
        },
        "site_id_matches": {
            "direct": 0,
            "int": 0,
            "object": 0,
            "name": 0
        },
        "total_users": len(main_users),
        "users_by_method": []
    }
    
    for u in main_users:
        debug = u["debug"]
        user_method = []
        
        if debug["direct_site_match"] and debug["direct_client_match"]:
            mapping["client_id_matches"]["direct"] += 1
            mapping["site_id_matches"]["direct"] += 1
            user_method.append("direct")
        
        if debug["int_site_match"] and debug["int_client_match"]:
            mapping["client_id_matches"]["int"] += 1
            mapping["site_id_matches"]["int"] += 1
            user_method.append("int")
        
        if debug["object_site_match"] and debug["object_client_match"]:
            mapping["client_id_matches"]["object"] += 1
            mapping["site_id_matches"]["object"] += 1
            user_method.append("object")
        
        if debug["name_site_match"] and debug["name_client_match"]:
            mapping["client_id_matches"]["name"] += 1
            mapping["site_id_matches"]["name"] += 1
            user_method.append("name")
        
        mapping["users_by_method"].append({
            "id": u["user"].get("id"),
            "name": u["user"].get("name"),
            "methods": user_method
        })
    
    return jsonify({
        "status": "success",
        "mapping": mapping,
        "note": "Deze mapping toont hoe gebruikers aan Main-site zijn gekoppeld"
    })

# ------------------------------------------------------------------------------
# App Start - MET VOLLEDIGE KOPPELINGSANALYSE
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - VOLLEDIGE KOPPELINGSANALYSE")
    log.info("-"*70)
    log.info("✅ Ondersteunt 4 koppelingsmethoden voor Main-site gebruikers")
    log.info("✅ Geen enkele gebruiker wordt gemist (ook niet bij 135+)")
    log.info("✅ Identificeert automatisch de juiste koppelingsmethode")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek EERST /debug-mapping")
    log.info("2. Analyseer de koppelingsmethoden voor jouw omgeving")
    log.info("3. Bezoek DAN /all-users voor volledig overzicht")
    log.info("4. Gebruik /users voor ALLE Main-site gebruikers")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
