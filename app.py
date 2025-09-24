import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - MET SPECIFIEKE API STRUCTUUR
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - AANGEKOPPELD AAN JOUW API RESPONSE
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
# Halo API helpers - MET JOUW SPECIFIEKE RESPONSE STRUCTUUR
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
    """HAAL ALLE GEBRUIKERS OP MET JOUW SPECIFIEKE RESPONSE STRUCTUUR"""
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
        
        # 👉 SPECIALE FIX VOOR JOUW RESPONSE STRUCTUUR 👈
        # Jouw response heeft een 'data' wrapper: {"data": {"record_count":50, "users": [...]} }
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
            log.warning("💡 Mogelijke oorzaken:")
            log.warning("1. Verkeerde response structuur - zie RAW response bovenaan")
            log.warning("2. Geen rechten voor gebruikersdata - controleer 'Teams' rechten")
            return []
        
        log.info(f"✅ {len(users)} gebruikers opgehaald - volledig overzicht beschikbaar")
        
        # Verrijk met filtering status
        enriched_users = []
        main_users_count = 0
        
        for u in users:
            # 👉 SPECIALE FIX VOOR JOUW VELD NAMEN 👈
            # Jouw response gebruikt site_id_int (integer) i.p.v. site_id (float)
            site_id_val = None
            site_key_used = None
            
            # Probeer eerst site_id_int (integer versie)
            if "site_id_int" in u and u["site_id_int"] is not None:
                try:
                    site_id_val = float(u["site_id_int"])
                    site_key_used = "site_id_int"
                except (TypeError, ValueError):
                    pass
            
            # Als dat niet werkt, probeer site_id (float versie)
            if site_id_val is None and "site_id" in u and u["site_id"] is not None:
                try:
                    site_id_val = float(u["site_id"])
                    site_key_used = "site_id"
                except (TypeError, ValueError):
                    pass
            
            # Haal client ID op
            client_id_val = None
            client_key_used = None
            
            # Probeer eerst client_id_int
            if "client_id_int" in u and u["client_id_int"] is not None:
                try:
                    client_id_val = float(u["client_id_int"])
                    client_key_used = "client_id_int"
                except (TypeError, ValueError):
                    pass
            
            # Als dat niet werkt, probeer client_id
            if client_id_val is None and "client_id" in u and u["client_id"] is not None:
                try:
                    client_id_val = float(u["client_id"])
                    client_key_used = "client_id"
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
        
        # Log de eerste Main-site gebruiker voor debugging
        if main_users_count > 0:
            main_user = next(u for u in enriched_users if u["is_main_user"])
            log.info(f"🔍 Voorbeeld Main-gebruiker: ID={main_user['user'].get('id')}, Naam='{main_user['user'].get('name')}'")
            log.info(f"  Site: {main_user['debug']['site_id_value']} (via '{main_user['debug']['site_key_used']}')")
            log.info(f"  Client: {main_user['debug']['client_id_value']} (via '{main_user['debug']['client_key_used']}')")
        
        return enriched_users
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - MET JOUW SPECIFIEKE RESPONSE STRUCTUUR
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_notes": [
            "1. Werkt MET JOUW SPECIFIEKE API RESPONSE STRUCTUUR",
            "2. Gebruikt 'data' wrapper en site_id_int/client_id_int",
            "3. Bezoek /all-users voor volledig overzicht"
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
                "1. Bezoek /all-users voor volledig overzicht",
                "2. Controleer of client_id=12 en site_id=18 correct zijn",
                "3. Zorg dat 'Teams' is aangevinkt in API-toegang"
            ],
            "debug_info": "Deze app is afgestemd op jouw specifieke API response structuur"
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
            "email": eu["user"].get("emailaddress") or eu["user"].get("email") or "Geen email",
            "is_main_user": eu["is_main_user"],
            "debug": eu["debug"]
        }
        
        if eu["is_main_user"]:
            response["main_site_users"] += 1
        
        response["users"].append(user_data)
    
    # Log resultaat voor transparantie
    log.info(f"📊 /all-users: {response['main_site_users']} Main-site gebruikers gevonden van {response['total_users']} totaal")
    
    return jsonify(response)

# ------------------------------------------------------------------------------
# App Start - MET JOUW SPECIFIEKE RESPONSE STRUCTUUR
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - AFGESTEMD OP JOUW SPECIFIEKE API")
    log.info("-"*70)
    log.info("✅ Werkt MET DE 'data' WRAPPER IN DE API RESPONSE")
    log.info("✅ Gebruikt site_id_int/client_id_int (GEEN floats!)")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN:")
    log.info("1. Bezoek /all-users voor volledig overzicht")
    log.info("2. Controleer de 'is_main_user' vlag voor elke gebruiker")
    log.info("3. Gebruik /users voor ALLEEN de Main-site gebruikers")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
