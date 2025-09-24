import os, urllib.parse, logging, sys, time
from flask import Flask, jsonify
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# Correcte URL voor UAT
HALO_AUTH_URL      = "https://bncuat.halopsa.com/auth/token"
HALO_API_BASE      = "https://bncuat.halopsa.com/api"

# Controleer .env
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATAL ERROR: Vul HALO_CLIENT_ID en HALO_CLIENT_SECRET in .env in!")
    sys.exit(1)

# ------------------------------------------------------------------------------
# Halo API helpers
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Authenticatie met 'all' scope"""
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
    """HAAL ALLE GEBRUIKERS OP EN FILTER OP @bnc"""
    log.info("🔍 Start met het ophalen van alle gebruikers")
    all_users = []
    bnc_users = []
    page = 1
    max_pages = 100
    consecutive_empty = 0
    client_id = None
    site_id = None

    # Stap 1: Haal alle gebruikers op
    while page <= max_pages:
        users_url = f"{HALO_API_BASE}/Users?page={page}&pageSize=50"
        log.info(f"➡️ API-aanvraag (pagina {page}): {users_url}")
        
        try:
            headers = get_halo_headers()
            r = requests.get(users_url, headers=headers, timeout=30)
            
            if r.status_code != 200:
                log.error(f"❌ API FOUT ({r.status_code}): {r.text}")
                if r.status_code in [429, 500, 502, 503, 504]:
                    time.sleep(2)
                    continue
                break
                
            data = r.json()
            
            # Verwerk 'data' wrapper
            if "data" in data and isinstance(data["data"], dict):
                users_data = data["data"]
            else:
                users_data = data
            
            # Haal de users lijst op
            users = users_data.get("users", [])
            if not users:
                users = users_data.get("Users", [])
            
            if not users:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    log.info("✅ Stoppen met ophalen na 3 lege pagina's")
                    break
                page += 1
                time.sleep(0.5)
                continue
            
            consecutive_empty = 0
            all_users.extend(users)
            log.info(f"✅ Pagina {page}: {len(users)} gebruikers opgehaald (totaal: {len(all_users)})")
            
            # Stap 2: Filter op @bnc in real-time
            for u in users:
                email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
                
                # Controleer op @bnc (case-insensitive)
                if "@bnc" in email:
                    bnc_users.append(u)
                    log.info(f"📧 GEVONDEN @bnc gebruiker: {u.get('name', 'Onbekend')} - {email}")
            
            if len(users) < 50:
                log.info("✅ Laatste pagina bereikt (minder dan 50 gebruikers)")
                break
            
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            log.error(f"⚠️ Fout bij ophalen pagina {page}: {str(e)}")
            break

    log.info(f"✅ Totaal opgehaald: {len(all_users)} gebruikers")
    log.info(f"✅ Totaal @bnc gebruikers gevonden: {len(bnc_users)}")

    # Stap 3: Als we @bnc gebruikers hebben, probeer client/site ID's te bepalen
    if bnc_users:
        log.info("🔍 Bepaal client/site ID's op basis van de eerste @bnc gebruiker")
        
        # Gebruik de eerste @bnc gebruiker om client/site ID's te vinden
        example_user = bnc_users[0]
        
        # Haal client_id op
        client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
        for key in client_id_keys:
            if key in example_user and example_user[key] is not None:
                try:
                    client_id = str(example_user[key]).strip()
                    log.info(f"✅ Gebruik client_id: {client_id} (gevonden via '{key}')")
                    break
                except:
                    pass
        
        # Haal site_id op
        site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
        for key in site_id_keys:
            if key in example_user and example_user[key] is not None:
                try:
                    site_id = str(example_user[key]).strip()
                    log.info(f"✅ Gebruik site_id: {site_id} (gevonden via '{key}')")
                    break
                except:
                    pass
        
        # Stap 4: Filter alle gebruikers op dezelfde client/site
        if client_id and site_id:
            log.info(f"🔍 Filter alle gebruikers op client_id={client_id} en site_id={site_id}")
            filtered_users = []
            
            for u in all_users:
                # Controleer client ID
                client_match = False
                for key in client_id_keys:
                    if key in u and u[key] is not None:
                        try:
                            if str(u[key]).strip() == client_id:
                                client_match = True
                                break
                        except:
                            pass
                
                # Controleer site ID
                site_match = False
                for key in site_id_keys:
                    if key in u and u[key] is not None:
                        try:
                            if str(u[key]).strip() == site_id:
                                site_match = True
                                break
                        except:
                            pass
                
                # Bepaal of dit een gebruiker is uit dezelfde groep
                if client_match and site_match:
                    filtered_users.append(u)
            
            log.info(f"📊 Totaal gebruikers in dezelfde groep: {len(filtered_users)}/{len(all_users)}")
            return filtered_users
    
    # Als we geen client/site ID's konden bepalen, retourneer alle @bnc gebruikers
    if bnc_users:
        log.warning("⚠️ Kon geen client/site ID's bepalen, retourneer alle @bnc gebruikers")
        return bnc_users
    
    log.error("❌ Geen @bnc gebruikers gevonden in de hele database!")
    return []

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_notes": [
            "1. Haalt ALLE gebruikers op en filtert op '@bnc'",
            "2. Bepaalt automatisch de juiste groep",
            "3. Bezoek /debug voor technische details"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLE @bnc gebruikers"""
    bnc_users = fetch_all_users()
    
    if not bnc_users:
        return jsonify({
            "error": "Geen @bnc gebruikers gevonden in Halo",
            "solution": [
                "1. Controleer of de API key toegang heeft tot alle gebruikers",
                "2. Zorg dat 'Teams' is aangevinkt in API-toegang",
                "3. Bezoek /debug voor meer technische details"
            ]
        }), 500
    
    # Toon de eerste 5 gebruikers in de logs voor debug
    log.info(f"📋 Eerste 5 @bnc gebruikers gevonden:")
    for i, u in enumerate(bnc_users[:5], 1):
        email = u.get("emailaddress") or u.get("email") or "Geen email"
        name = u.get("name") or "Onbekend"
        log.info(f"   {i}. {name} - {email}")
    
    simplified = [{
        "id": u.get("id"),
        "name": u.get("name") or "Onbekend",
        "email": u.get("emailaddress") or u.get("email") or "Geen email"
    } for u in bnc_users]
    
    return jsonify({
        "total_bnc_users": len(bnc_users),
        "users": simplified
    })

@app.route("/debug", methods=["GET"])
def debug():
    """Toon uitgebreide debug informatie"""
    bnc_users = fetch_all_users()
    
    # Verzamel voorbeeldgegevens
    sample_users = []
    for u in bnc_users[:5]:
        email = u.get("emailaddress") or u.get("email") or "Geen email"
        name = u.get("name") or "Onbekend"
        
        # Verzamel client/site info
        client_info = "Onbekend"
        site_info = "Onbekend"
        
        for key in ["client_name", "clientName", "ClientName"]:
            if key in u and u[key]:
                client_info = u[key]
                break
        
        for key in ["site_name", "siteName", "SiteName"]:
            if key in u and u[key]:
                site_info = u[key]
                break
        
        sample_users.append({
            "name": name,
            "email": email,
            "client": client_info,
            "site": site_info
        })
    
    return {
        "status": "debug-info",
        "api_flow": [
            "1. Authenticatie naar /auth/token (scope=all)",
            "2. Haal ALLE gebruikers op via /Users met paginering (50 per pagina)",
            "3. FILTER OP '@bnc' IN EMAIL",
            "4. BEPAAL GROEP VIA EERSTE @bnc GEBRUIKER"
        ],
        "current_counts": {
            "total_users_fetched": len(fetch_all_users.cache) if hasattr(fetch_all_users, 'cache') else "N/A",
            "total_bnc_users_found": len(bnc_users)
        },
        "sample_users": sample_users,
        "safety_mechanisms": [
            "• Maximaal 100 pagina's om oneindige lus te voorkomen",
            "• 0.3s delay tussen aanvragen om rate limiting te voorkomen",
            "• 3 opeenvolgende lege pagina's stoppen de lus",
            "• Herkansingen bij tijdelijke netwerkfouten"
        ],
        "troubleshooting": [
            "Als geen @bnc gebruikers worden gevonden:",
            "1. Controleer of de API key toegang heeft tot alle gebruikers",
            "2. Zorg dat 'Teams' is aangevinkt in API-toegang",
            "3. Bezoek /debug om technische details te zien"
        ],
        "note": "Deze app filtert automatisch op '@bnc' in de email, dus alle gebruikers met '@bnc' in hun email worden geretourneerd"
    }

# ------------------------------------------------------------------------------
# App Start
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO ALL BNC USERS - ZONDER HARDCODED EMAILS")
    log.info("-"*70)
    log.info("✅ Haalt ALLE gebruikers op en filtert op '@bnc' in de email")
    log.info("✅ Bepaalt automatisch de juiste groep")
    log.info("✅ Werkt met jouw specifieke Halo UAT omgeving")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Controleer de logs voor '@bnc gebruiker' meldingen")
    log.info("3. Bezoek /users voor ALLE @bnc gebruikers")
    log.info("="*70)
    app.run(host="0.0.0.0", port=port, debug=True)
