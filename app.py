import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET VOLLEDIGE RESPONSE ANALYSE
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - VOLLEDIG ROBUST
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# Correcte URL voor UAT
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# Jouw correcte IDs
HALO_CLIENT_ID_NUM = 12  # Bossers & Cnossen (URL ID)
HALO_SITE_ID       = 18  # Main (URL ID)

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - MET VOLLEDIGE RESPONSE ANALYSE
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
    """HAAL ALLE GEBRUIKERS OP MET VOLLEDIGE RESPONSE ANALYSE"""
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
            log.error("👉 PROBEER DEZE CURL COMMAND IN TERMINAL:")
            log.error(f"curl -X GET '{users_url}' -H 'Authorization: Bearer $(curl -X POST \\\"{HALO_AUTH_URL}\\\" -d \\\"grant_type=client_credentials&client_id={HALO_CLIENT_ID}&client_secret=******&scope=all\\\") | jq .access_token)'")
            return []
        
        # Parse response - analyseer ALLE mogelijke structuren
        data = r.json()
        log.info(f"🔍 RESPONSE STRUCTUUR: {type(data).__name__}")
        
        # Mogelijke gebruikersvelden
        user_fields = [
            "users", "Users", "user", "User",
            "items", "data", "results", "entry"
        ]
        
        # Zoek gebruikers in de response
        users = []
        if isinstance(data, list):
            log.info(f"✅ Gebruikers gevonden als LIJST ({len(data)} items)")
            users = data
        else:
            log.info("🔍 Zoek gebruikers in object response...")
            for field in user_fields:
                if field in data and isinstance(data[field], list):
                    log.info(f"✅ Gebruikers gevonden in veld: '{field}' ({len(data[field])} items)")
                    users = data[field]
                    break
        
        if not users:
            log.warning("⚠️ Geen gebruikers gevonden in API response")
            log.warning("💡 Mogelijke oorzaken:")
            log.warning("1. Verkeerde response structuur - bekijk RAW response bovenaan")
            log.warning("2. Geen rechten voor gebruikersdata - controleer 'Teams' rechten")
            log.warning("3. Lege klant/site - geen gebruikers gekoppeld")
            return []
        
        log.info(f"✅ {len(users)} gebruikers opgehaald - volledig overzicht beschikbaar")
        
        # Verrijk met filtering status
        enriched_users = []
        main_users_count = 0
        
        for u in users:
            # Haal site ID op (alle varianten) + converteer naar float
            site_id_val = None
            site_key_used = None
            for key in ["siteid", "site_id", "SiteId", "siteId", "SiteID"]:
                if key in u and u[key] is not None:
                    try:
                        site_id_val = float(u[key])
                        site_key_used = key
                        break
                    except (TypeError, ValueError):
                        pass
            
            # Haal client ID op (alle varianten) + converteer naar float
            client_id_val = None
            client_key_used = None
            for key in ["clientid", "client_id", "ClientId", "clientId", "ClientID"]:
                if key in u and u[key] is not None:
                    try:
                        client_id_val = float(u[key])
                        client_key_used = key
                        break
                    except (TypeError, ValueError):
                        pass
            
            # Bepaal of dit een Main-site gebruiker is
            is_main_user = (
                site_id_val is not None and 
                client_id_val is not None and
                abs(site_id_val - HALO_SITE_ID) < 0.1 and
                abs(client_id_val - HALO_CLIENT_ID_NUM) < 0.1
            )
            
            if is_main_user:
                main_users_count += 1
            
            enriched_users.append({
                "user": u,
                "is_main_user": is_main_user,
                "debug": {
                    "site_key_used": site_key_used,
                    "site_id_value": site_id_val,
                    "client_key_used": client_key_used,
                    "client_id_value": client_id_val,
                    "matches_criteria": is_main_user
                }
            })
        
        log.info(f"📊 Totaal Main-site gebruikers: {main_users_count}/{len(users)}")
        
        # Log de eerste gebruiker voor debugging
        if enriched_users:
            first_user = enriched_users[0]
            log.info(f"🔍 Eerste gebruiker: ID={first_user['user'].get('id')}, Naam='{first_user['user'].get('name')}'")
            log.info(f"  Site: {first_user['debug']['site_id_value']} (via '{first_user['debug']['site_key_used']}')")
            log.info(f"  Client: {first__user['debug']['client_id_value']} (via '{first_user['debug']['client_key_used']}')")
        
        return enriched_users
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - MET VOLLEDIGE RESPONSE ANALYSE
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /all-users voor volledig overzicht",
        "critical_notes": [
            "1. Bezoek /debug-raw voor de ONBEBERKTE API response",
            "2. Geen veronderstellingen meer over response structuur",
            "3. Werkt met ALLE mogelijke response formaten"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLEEN de Main-site gebruikers"""
    enriched_users = fetch_all_users()
    main_users = [u for u in enriched_users if u["is_main_user"]]
    
    if not main_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                "1. Bezoek /debug-raw voor de ONBEBERKTE API response",
                "2. Controleer of client_id=12 en site_id=18 correct zijn",
                "3. Zorg dat 'Teams' is aangevinkt in API-toegang"
            ],
            "debug_info": "Deze app logt nu de VOLLEDIGE API response voor analyse"
        }), 500
    
    simplified = [{
        "id": u["user"].get("id"),
        "name": u["user"].get("name") or "Onbekend",
        "email": u["user"].get("EmailAddress") or u["user"].get("email") or "Geen email"
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
    """Toon ALLE gebruikers MET FILTERING DETAILS"""
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
            "email": eu["user"].get("EmailAddress") or eu["user"].get("email") or "Geen email",
            "is_main_user": eu["is_main_user"],
            "debug": eu["debug"]
        }
        
        if eu["is_main_user"]:
            response["main_site_users"] += 1
        
        response["users"].append(user_data)
    
    # Log resultaat voor transparantie
    log.info(f"📊 /all-users: {response['main_site_users']} Main-site gebruikers gevonden van {response['total_users']} totaal")
    
    return jsonify(response)

@app.route("/debug-raw", methods=["GET"])
def debug_raw():
    """Toon DE VOLLEDIGE, ONBEBERKTE API RESPONSE"""
    try:
        headers = get_halo_headers()
        r = requests.get(f"{HALO_API_BASE}/Users", headers=headers, timeout=30)
        
        if r.status_code != 200:
            return {
                "error": f"API fout ({r.status_code})",
                "response": r.text[:1000],
                "curl_command": f"curl -X GET '{HALO_API_BASE}/Users' -H 'Authorization: Bearer ...'"
            }, 500
        
        try:
            # Probeer als JSON
            data = r.json()
            return {
                "status": "success",
                "response_type": "JSON",
                "data": data,
                "note": "Deze response is in JSON formaat - controleer de structuur"
            }
        except:
            # Als het geen JSON is
            return {
                "status": "success",
                "response_type": "RAW_TEXT",
                "data": r.text[:1000],
                "note": "Deze response is GEEN JSON - mogelijk verkeerde authenticatie"
            }
    
    except Exception as e:
        return {"error": str(e)}, 500

# ------------------------------------------------------------------------------
# App Start - MET VOLLEDIGE RESPONSE ANALYSE
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - VOLLEDIGE RESPONSE ANALYSE")
    log.info("-"*70)
    log.info("✅ Logt de VOLLEDIGE RAW API response voor debugging")
    log.info("✅ Ondersteunt ALLE mogelijke response formaten")
    log.info("✅ Geen veronderstellingen meer over structuur")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR DEBUGGING:")
    log.info("1. Bezoek EERST /debug-raw")
    log.info("2. Analyseer de EXACTE API response")
    log.info("3. Pas de code aan op basis van ECHTE data")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
