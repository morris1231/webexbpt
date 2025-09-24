import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - Met REAL-TIME DATA VALIDATIE
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config - GEEN RUIMTE VOOR ONDUidelijkheid
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# ✅ FORCEER correcte AUTH URL (NIET AFWIJKEN!)
HALO_AUTH_URL      = "https://bncuat.halopsa.com/oauth2/token"
HALO_API_BASE      = os.getenv("HALO_API_BASE", "https://bncuat.halopsa.com/api").strip()

# Jouw IDs
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))   # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))         # Main site

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAAL: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers - MET REAL-TIME DATA VALIDATIE
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Authenticatie met geforceerde URL"""
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
        log.critical("👉 OPLOSSING:")
        log.critical("1. GA NAAR: Instellingen → API-toegang")
        log.critical("2. VINK 'Teams' EXPLICIET AAN (niet alleen 'Algemeen')")
        log.critical("3. DRUK OP 'OPSLAAN'")
        log.critical("4. HERSTART DE APP VOLLEDIG")
        raise

def fetch_main_users(client_id: int, site_id: int):
    """HAAL GEBRUIKERS OP MET ULTRA-ROBUUSTE FILTERING"""
    log.info(f"🔍 Start proces voor client {client_id}, site {site_id}")
    
    try:
        # Stap 1: Haal ALLE gebruikers op
        users_url = f"{HALO_API_BASE}/Users"
        log.info(f"➡️ API-aanvraag: {users_url}")
        
        headers = get_halo_headers()
        r = requests.get(users_url, headers=headers, timeout=30)
        r.raise_for_status()
        
        # Parse response
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or data.get("Users", [])
        log.info(f"✅ {len(users)} gebruikers opgehaald - start ULTRA-ROBUUSTE filtering")
        
        # Stap 2: Real-time data validatie
        valid_users = []
        site_ids_found = set()
        client_ids_found = set()
        
        for u in users:
            # Haal site ID op (ALLE mogelijke varianten)
            site_id_val = str(
                u.get("site_id") or 
                u.get("SiteId") or 
                u.get("siteId") or 
                u.get("siteid") or  # 👈 BELANGRIJK: Alle kleine varianten!
                (u["site"].get("id") if "site" in u and isinstance(u["site"], dict) else None) or
                ""
            ).strip().lower()
            
            # Haal client ID op (ALLE mogelijke varianten)
            client_id_val = str(
                u.get("client_id") or 
                u.get("ClientId") or 
                u.get("clientId") or 
                u.get("clientid") or  # 👈 BELANGRIJK: Alle kleine varianten!
                (u["client"].get("id") if "client" in u and isinstance(u["client"], dict) else None) or
                ""
            ).strip().lower()
            
            # Log gevonden IDs voor debugging
            if site_id_val: site_ids_found.add(site_id_val)
            if client_id_val: client_ids_found.add(client_id_val)
            
            # Valideer of dit een Main-site gebruiker is
            if site_id_val == str(site_id).lower() and client_id_val == str(client_id).lower():
                valid_users.append(u)
        
        # Stap 3: Real-time validatie rapport
        log.info(f"🔍 GEVONDEN SITE_IDS: {', '.join(site_ids_found)}")
        log.info(f"🔍 GEVONDEN CLIENT_IDS: {', '.join(client_ids_found)}")
        
        if site_ids_found:
            log.info(f"💡 TIP: Jouw site_id={site_id} moet exact overeenkomen met bovenstaande waarden")
        if client_ids_found:
            log.info(f"💡 TIP: Jouw client_id={client_id} moet exact overeenkomen met bovenstaande waarden")
        
        # Resultaat rapporteren
        if valid_users:
            log.info(f"✅ {len(valid_users)} JUISTE Main-site gebruikers gevonden!")
            if users:
                example = valid_users[0]
                log.info(f"  → Voorbeeldgebruiker: ID={example.get('id')}, Naam='{example.get('name')}'")
        else:
            log.error("❌ Geen Main-site gebruikers gevonden - REAL-TIME VALIDATIE")
            log.error(f"➡️ Gezochte site_id: '{site_id}' (geconverteerd naar '{str(site_id).lower()}')")
            log.error(f"➡️ Gezochte client_id: '{client_id}' (geconverteerd naar '{str(client_id).lower()}')")
            log.error(f"➡️ Gevonden site_ids: {', '.join(site_ids_found)}")
            log.error(f"➡️ Gevonden client_ids: {', '.join(client_ids_found)}")
            log.error("👉 OPLOSSING:")
            log.error("1. BEZOEK /debug-data voor ECHTE WAARDEN")
            log.error("2. PAS JOUW SITE/CLIENT IDs AAN OM EXACT TE KLOPPEN")
        
        return valid_users
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: {str(e)}")
        return []

# ------------------------------------------------------------------------------
# Routes - MET DIRECTE DATA VALIDATIE
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_steps": [
            "1. Bezoek /debug-data OM TE ZIEN WELKE WAARDEN ER WERKELIJK ZIJN",
            "2. PAS JOUW SITE/CLIENT IDs AAN OM EXACT TE KLOPPEN MET DEZE WAARDEN"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    
    if not site_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                "1. Bezoek /debug-data OM TE ZIEN WELKE WAARDEN ER WERKELIJK ZIJN",
                "2. PAS JOUW SITE/CLIENT IDs AAN OM EXACT TE KLOPPEN MET DEZE WAARDEN",
                "3. Voorbeeld: Als /debug-data '18 ' toont (met spatie), gebruik dan '18 ' i.p.v. '18'"
            ],
            "debug_info": "De meeste problemen komen doordat de site/client IDs niet EXACT overeenkomen met de API waarden"
        }), 500
    
    simplified = [{
        "id": u.get("id"),
        "name": u.get("name") or "Onbekend",
        "email": u.get("EmailAddress") or u.get("email") or "Geen email"
    } for u in site_users]
    
    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "site_id": HALO_SITE_ID,
        "total_users": len(site_users),
        "users": simplified
    })

@app.route("/debug-data", methods=["GET"])
def debug_data():
    """Toon ECHTE waarden van site/client IDs in de API"""
    try:
        headers = get_halo_headers()
        r = requests.get(f"{HALO_API_BASE}/Users", headers=headers, timeout=30)
        r.raise_for_status()
        
        data = r.json()
        users = data if isinstance(data, list) else data.get("users", []) or []
        
        site_ids = {}
        client_ids = {}
        
        # Verzamel alle unieke waarden
        for u in users:
            # Site IDs
            site_id_val = str(
                u.get("site_id") or 
                u.get("SiteId") or 
                u.get("siteId") or 
                u.get("siteid") or
                (u["site"].get("id") if "site" in u and isinstance(u["site"], dict) else None) or
                ""
            ).strip()
            
            if site_id_val:
                site_ids[site_id_val] = site_ids.get(site_id_val, 0) + 1
            
            # Client IDs
            client_id_val = str(
                u.get("client_id") or 
                u.get("ClientId") or 
                u.get("clientId") or 
                u.get("clientid") or
                (u["client"].get("id") if "client" in u and isinstance(u["client"], dict) else None) or
                ""
            ).strip()
            
            if client_id_val:
                client_ids[client_id_val] = client_ids.get(client_id_val, 0) + 1
        
        return {
            "status": "success",
            "message": "Dit zijn de EXACTE waarden zoals ze in de API staan",
            "site_ids": [
                {"value": val, "count": count, "length": len(val), "has_whitespace": bool(val != val.strip())}
                for val, count in site_ids.items()
            ],
            "client_ids": [
                {"value": val, "count": count, "length": len(val), "has_whitespace": bool(val != val.strip())}
                for val, count in client_ids.items()
            ],
            "note": "Let op spaties en hoofdlettergebruik - dit moet EXACT kloppen!"
        }
    
    except Exception as e:
        return {"error": str(e)}, 500

# ------------------------------------------------------------------------------
# App Start - MET ONTWERP VOOR SUCCES
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Forceer correcte auth URL
    os.environ["HALO_AUTH_URL"] = "https://bncuat.halopsa.com/oauth2/token"
    
    port = int(os.getenv("PORT", 5000))
    
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS - ONTWERP VOOR SUCCES")
    log.info("-"*70)
    log.info("💡 BELANGRIJK: Volg deze stappen IN VOLGORDE:")
    log.info("1. Bezoek EERST /debug-data")
    log.info("2. Noteer de EXACTE waarden voor jouw site/client")
    log.info("3. Pas jouw .env aan met DEZE EXACTE WAARDEN")
    log.info("4. Bezoek /users")
    log.info("-"*70)
    log.info("🔍 VOORBEELD PROBLEEM:")
    log.info("  - Jouw .env gebruikt site_id=18")
    log.info("  - Maar API bevat '18 ' (met spatie)")
    log.info("  - Oplossing: Zet site_id='18 ' in .env")
    log.info("="*70)
    
    app.run(host="0.0.0.0", port=port, debug=True)
