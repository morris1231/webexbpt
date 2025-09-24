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

# Jouw specifieke client en site IDs (ZOALS IN DE URL)
HALO_CLIENT_ID_NUM = 12  # Bossers & Cnossen (URL ID)
HALO_SITE_ID       = 18  # Main (URL ID)

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
        if 'r' in locals():
            log.critical(f"➡️ Response: {r.text}")
            log.critical(f"➡️ Status code: {r.status_code}")
        return None

def fetch_all_users():
    """HAAL ALLE GEBRUIKERS OP MET JUISTE CLIENT/SITE FILTERING"""
    log.info("🔍 Start met het ophalen van alle gebruikers met correcte client/site filtering")
    
    # Stap 1: Haal alle gebruikers op met paginering
    all_users = []
    page = 1
    max_pages = 100
    consecutive_empty = 0
    
    while page <= max_pages:
        users_url = f"{HALO_API_BASE}/Users?page={page}&pageSize=50"
        log.info(f"➡️ API-aanvraag (pagina {page}): {users_url}")
        
        try:
            headers = get_halo_headers()
            if not headers:
                return []
                
            r = requests.get(users_url, headers=headers, timeout=30)
            
            if r.status_code != 200:
                log.error(f"❌ API FOUT ({r.status_code}): {r.text}")
                if r.status_code in [429, 500, 502, 503, 504]:
                    time.sleep(2)
                    continue
                break
                
            try:
                data = r.json()
            except Exception as e:
                log.error(f"❌ Kan API response niet parsen als JSON: {str(e)}")
                log.error(f"➡️ Raw response: {r.text[:500]}")
                return []
            
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
            
            # Voeg gebruikers toe aan de complete lijst
            all_users.extend(users)
            log.info(f"✅ Pagina {page}: {len(users)} gebruikers opgehaald (totaal: {len(all_users)})")
            
            # Stop als we geen volgende pagina hebben
            if len(users) < 50:
                log.info("✅ Laatste pagina bereikt (minder dan 50 gebruikers)")
                break
            
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            log.error(f"⚠️ Fout bij ophalen pagina {page}: {str(e)}")
            time.sleep(1)
            continue
    
    log.info(f"✅ Totaal opgehaald: {len(all_users)} gebruikers")
    
    # Stap 2: Filter op @bnc en valideer client/site koppeling
    log.info(f"🔍 Filter gebruikers op '@bnc' en valideer client/site koppeling (client_id={HALO_CLIENT_ID_NUM}, site_id={HALO_SITE_ID})")
    
    bnc_users = []
    exact_match_count = 0
    
    for u in all_users:
        # Haal email op (case-insensitive)
        email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
        
        # Filter op @bnc
        if "@bnc" not in email:
            continue
            
        # Controleer client ID
        client_match = False
        client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
        for key in client_id_keys:
            if key in u and u[key] is not None:
                try:
                    if str(u[key]).strip() == str(HALO_CLIENT_ID_NUM):
                        client_match = True
                        break
                except:
                    pass
        
        # Controleer site ID
        site_match = False
        site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
        for key in site_id_keys:
            if key in u and u[key] is not None:
                try:
                    if str(u[key]).strip() == str(HALO_SITE_ID):
                        site_match = True
                        break
                except:
                    pass
        
        # Controleer op exacte email matches voor Edwin en Danja
        is_exact_match = False
        if "edwin.nieborg@bnc.nl" in email or "danja.berlo@bnc.nl" in email:
            is_exact_match = True
            exact_match_count += 1
        
        # Bepaal of dit een geldige gebruiker is
        if client_match and site_match:
            bnc_users.append(u)
            match_type = "EXACT" if is_exact_match else "MATCH"
            log.info(f"{match_type} @bnc gebruiker: {u.get('name', 'Onbekend')} - {email} (client: {client_match}, site: {site_match})")
    
    log.info(f"✅ Totaal @bnc gebruikers gevonden met correcte client/site koppeling: {len(bnc_users)}")
    
    if exact_match_count == 0:
        log.warning("⚠️ WAARSCHUWING: Geen exacte matches gevonden voor Edwin.Nieborg@bnc.nl of danja.berlo@bnc.nl")
        log.warning("➡️ Mogelijke oorzaken:")
        log.warning("   1. De emailadressen staan niet letterlijk zo in Halo")
        log.warning("   2. De client/site ID's zijn niet correct ingesteld")
        log.warning("   3. De gebruikers hebben een andere site in Halo")
    
    return bnc_users

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait! Bezoek /users voor data",
        "critical_notes": [
            "1. Werkt MET JUISTE CLIENT/SITE FILTERING (geen /Clients endpoint)",
            "2. Gebruikt jouw specifieke client_id=12 en site_id=18",
            "3. Bezoek /debug voor technische details"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLE @bnc gebruikers met correcte client/site koppeling"""
    try:
        bnc_users = fetch_all_users()
        
        if not bnc_users:
            log.error("❌ Geen @bnc gebruikers gevonden met correcte client/site koppeling")
            return jsonify({
                "error": "Geen @bnc gebruikers gevonden met correcte client/site koppeling",
                "solution": [
                    "1. Controleer of de API key 'all' scope heeft",
                    "2. Zorg dat 'Teams' is aangevinkt in API-toegang",
                    "3. Bezoek /debug voor technische details"
                ],
                "config": {
                    "client_id": HALO_CLIENT_ID_NUM,
                    "site_id": HALO_SITE_ID
                }
            }), 500
        
        log.info(f"✅ Succesvol {len(bnc_users)} @bnc gebruikers met correcte koppeling geretourneerd")
        
        simplified = [{
            "id": u.get("id"),
            "name": u.get("name") or "Onbekend",
            "email": u.get("emailaddress") or u.get("email") or "Geen email",
            "client_id": str(HALO_CLIENT_ID_NUM),
            "client_name": "Bossers & Cnossen",
            "site_id": str(HALO_SITE_ID),
            "site_name": "Main"
        } for u in bnc_users]
        
        return jsonify({
            "client_id": HALO_CLIENT_ID_NUM,
            "client_name": "Bossers & Cnossen",
            "site_id": HALO_SITE_ID,
            "site_name": "Main",
            "total_users": len(bnc_users),
            "users": simplified
        })
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT in /users: {str(e)}")
        return jsonify({
            "error": "Interne serverfout",
            "details": str(e)
        }), 500

@app.route("/debug", methods=["GET"])
def debug():
    """Toon technische debug informatie"""
    try:
        bnc_users = fetch_all_users()
        
        # Zoek voorbeeldgebruikers
        sample_users = []
        for i, u in enumerate(bnc_users[:5], 1):
            email = u.get("emailaddress") or u.get("email") or "Geen email"
            name = u.get("name") or "Onbekend"
            
            # Verzamel alle mogelijke ID's
            client_ids = []
            for key in ["client_id", "ClientId", "clientId", "ClientID", "clientid"]:
                if key in u and u[key]:
                    client_ids.append(f"{key}: {u[key]}")
            
            site_ids = []
            for key in ["site_id", "SiteId", "siteId", "SiteID", "siteid"]:
                if key in u and u[key]:
                    site_ids.append(f"{key}: {u[key]}")
            
            sample_users.append({
                "volgorde": i,
                "name": name,
                "email": email,
                "client_ids": ", ".join(client_ids) if client_ids else "Niet gevonden",
                "site_ids": ", ".join(site_ids) if site_ids else "Niet gevonden",
                "user_id": u.get("id", "Onbekend")
            })
        
        return {
            "status": "debug-info",
            "api_flow": [
                "1. Authenticatie naar /auth/token (scope=all)",
                "2. Haal ALLE gebruikers op via /Users met paginering (50 per pagina)",
                "3. FILTER OP '@bnc' EN CLIENT/SITE KOPPELING"
            ],
            "configuration": {
                "client_id": HALO_CLIENT_ID_NUM,
                "site_id": HALO_SITE_ID,
                "halo_api_base": HALO_API_BASE
            },
            "current_counts": {
                "total_users_fetched": len(bnc_users),
                "exact_email_matches": sum(1 for u in bnc_users 
                    if "edwin.nieborg@bnc.nl" in str(u.get("emailaddress") or u.get("email") or "").lower() 
                    or "danja.berlo@bnc.nl" in str(u.get("emailaddress") or u.get("email") or "").lower())
            },
            "sample_users": sample_users,
            "safety_mechanisms": [
                "• Geen gebruik van niet-bestaande /Clients endpoint",
                "• 0.3s delay tussen aanvragen om rate limiting te voorkomen",
                "• Herkansingen bij tijdelijke netwerkfouten",
                "• Case-insensitive email matching"
            ],
            "troubleshooting": [
                "Als geen gebruikers worden gevonden:",
                "1. Controleer of client_id=12 en site_id=18 correct zijn",
                "2. Bezoek /debug om te zien welke ID-velden beschikbaar zijn",
                "3. Pas de client_id/site_id aan in de code als nodig"
            ]
        }
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT in /debug: {str(e)}")
        return jsonify({
            "error": "Interne serverfout",
            "details": str(e)
        }), 500

# ------------------------------------------------------------------------------
# App Start
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info("="*70)
    log.info("🚀 HALO BNC USERS - DIRECTE CLIENT/SITE KOPPELING")
    log.info("-"*70)
    log.info(f"✅ Gebruikt directe client_id={HALO_CLIENT_ID_NUM} en site_id={HALO_SITE_ID}")
    log.info("✅ Geen gebruik van niet-bestaande /Clients endpoint")
    log.info("✅ Filtert op '@bnc' in de email en valideert client/site koppeling")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Controleer de logs op '@bnc gebruiker' meldingen")
    log.info("3. Bezoek /users voor ALLE @bnc gebruikers met correcte koppeling")
    log.info("="*70)
    
    # Gebruik de poort zoals ingesteld in de omgeving
    app.run(host="0.0.0.0", port=port, debug=False)
