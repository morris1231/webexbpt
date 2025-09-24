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

# Jouw specifieke client en site IDs
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
    """HAAL ALLE GEBRUIKERS OP MET JUISTE PAGINERING"""
    log.info("🔍 Start met het ophalen van alle gebruikers")
    
    # Gebruik een dictionary om duplicaten te voorkomen
    all_users = {}
    page = 1
    max_pages = 100
    consecutive_empty = 0
    total_bnc_count = 0

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
            
            # Verwerk gebruikers en voorkom duplicaten
            new_users = 0
            bnc_users = 0
            
            for u in users:
                user_id = str(u.get("id", ""))
                if not user_id:
                    # Probeer alternatieve ID velden
                    for key in ["UserId", "userID", "user_id", "ID"]:
                        if key in u and u[key]:
                            user_id = str(u[key])
                            break
                
                # Sla gebruiker op met ID als sleutel om duplicaten te voorkomen
                if user_id:
                    # Filter op @bnc
                    email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
                    is_bnc = "@bnc" in email
                    
                    if is_bnc:
                        bnc_users += 1
                        total_bnc_count += 1
                    
                    all_users[user_id] = u
                    new_users += 1
            
            log.info(f"✅ Pagina {page}: {len(users)} gebruikers opgehaald")
            log.info(f"   ➡️ {new_users} nieuwe gebruikers toegevoegd aan de database")
            log.info(f"   ➡️ {bnc_users} @bnc gebruikers gevonden op deze pagina (totaal: {total_bnc_count})")
            
            if len(users) < 50:
                log.info("✅ Laatste pagina bereikt (minder dan 50 gebruikers)")
                break
            
            page += 1
            time.sleep(0.3)
            
        except Exception as e:
            log.error(f"⚠️ Fout bij ophalen pagina {page}: {str(e)}")
            time.sleep(1)
            continue
    
    log.info(f"✅ Totaal unieke gebruikers opgehaald: {len(all_users)}")
    log.info(f"✅ Totaal unieke @bnc gebruikers gevonden: {total_bnc_count}")
    
    # Stap 2: Filter op @bnc en valideer client/site koppeling
    log.info(f"🔍 Filter gebruikers op '@bnc' en valideer client/site koppeling (client_id={HALO_CLIENT_ID_NUM}, site_id={HALO_SITE_ID})")
    
    bnc_users = []
    exact_match_count = 0
    client_site_matches = 0
    no_client_site_info = 0
    
    # Definieer alle mogelijke veldnamen voor client en site ID's
    client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
    site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
    
    for user_id, u in all_users.items():
        # Haal email op (case-insensitive)
        email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
        
        # Sla de originele email op voor logging
        original_email = u.get("emailaddress") or u.get("email") or "Geen email"
        
        # Filter op @bnc
        if "@bnc" not in email:
            continue
            
        # Controleer client ID
        client_match = False
        client_id_value = None
        for key in client_id_keys:
            if key in u and u[key] is not None:
                try:
                    if str(u[key]).strip() == str(HALO_CLIENT_ID_NUM):
                        client_match = True
                        client_id_value = u[key]
                        break
                except:
                    pass
        
        # Controleer site ID
        site_match = False
        site_id_value = None
        for key in site_id_keys:
            if key in u and u[key] is not None:
                try:
                    if str(u[key]).strip() == str(HALO_SITE_ID):
                        site_match = True
                        site_id_value = u[key]
                        break
                except:
                    pass
        
        # Bepaal of dit een geldige gebruiker is
        if client_match and site_match:
            client_site_matches += 1
            bnc_users.append(u)
            
            # Controleer op exacte email matches
            is_exact_match = False
            if "edwin.nieborg@bnc.nl" in email or "danja.berlo@bnc.nl" in email:
                is_exact_match = True
                exact_match_count += 1
            
            match_type = "EXACT" if is_exact_match else "MATCH"
            log.info(f"{match_type} @bnc gebruiker: {u.get('name', 'Onbekend')} - {original_email} "
                     f"(client: {client_id_value}, site: {site_id_value})")
        else:
            no_client_site_info += 1
            log.warning(f"⚠️ @bnc gebruiker GEEN client/site koppeling: {u.get('name', 'Onbekend')} - {original_email} "
                        f"(client: {client_id_value}, site: {site_id_value})")
    
    log.info(f"✅ Totaal @bnc gebruikers met correcte client/site koppeling: {len(bnc_users)}")
    log.info(f"✅ Totaal @bnc gebruikers zonder client/site koppeling: {no_client_site_info}")
    
    if exact_match_count == 0:
        log.warning("⚠️ WAARSCHUWING: Geen exacte matches gevonden voor Edwin.Nieborg@bnc.nl of danja.berlo@bnc.nl")
    
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
            "1. Haalt ALLE gebruikers op via /Users endpoint",
            "2. Filtert op '@bnc' in de email",
            "3. Valideert client/site koppeling (client_id=12, site_id=18)",
            "4. Bezoek /debug voor technische details"
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
        
        simplified = []
        for u in bnc_users:
            # Zoek client en site namen
            client_name = "Onbekend"
            site_name = "Onbekend"
            
            # Probeer client naam te vinden
            for key in ["client_name", "clientName", "ClientName"]:
                if key in u and u[key]:
                    client_name = u[key]
                    break
            
            # Probeer site naam te vinden
            for key in ["site_name", "siteName", "SiteName"]:
                if key in u and u[key]:
                    site_name = u[key]
                    break
            
            simplified.append({
                "id": u.get("id"),
                "name": u.get("name") or "Onbekend",
                "email": u.get("emailaddress") or u.get("email") or "Geen email",
                "client_id": str(HALO_CLIENT_ID_NUM),
                "client_name": client_name,
                "site_id": str(HALO_SITE_ID),
                "site_name": site_name
            })
        
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
    """Toon uitgebreide debug informatie"""
    try:
        bnc_users = fetch_all_users()
        
        # Verzamel voorbeeldgegevens
        sample_users = []
        for i, u in enumerate(bnc_users[:5], 1):
            email = u.get("emailaddress") or u.get("email") or "Geen email"
            name = u.get("name") or "Onbekend"
            
            # Zoek client en site namen
            client_name = "Onbekend"
            site_name = "Onbekend"
            
            # Probeer client naam te vinden
            for key in ["client_name", "clientName", "ClientName"]:
                if key in u and u[key]:
                    client_name = u[key]
                    break
            
            # Probeer site naam te vinden
            for key in ["site_name", "siteName", "SiteName"]:
                if key in u and u[key]:
                    site_name = u[key]
                    break
            
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
                "client_name": client_name,
                "site_name": site_name,
                "client_ids": ", ".join(client_ids) if client_ids else "Niet gevonden",
                "site_ids": ", ".join(site_ids) if site_ids else "Niet gevonden",
                "user_id": u.get("id", "Onbekend")
            })
        
        return {
            "status": "debug-info",
            "api_flow": [
                "1. Authenticatie naar /auth/token (scope=all)",
                "2. Haal ALLE gebruikers op via /Users met paginering (50 per pagina)",
                "3. FILTER OP '@bnc' IN EMAIL",
                "4. VALIDEER CLIENT/SITE KOPPELING"
            ],
            "configuration": {
                "client_id": HALO_CLIENT_ID_NUM,
                "site_id": HALO_SITE_ID,
                "halo_api_base": HALO_API_BASE
            },
            "current_counts": {
                "total_unique_users_fetched": len(fetch_all_users.cache) if hasattr(fetch_all_users, 'cache') else "N/A",
                "total_bnc_users_found": len(bnc_users),
                "exact_email_matches": sum(1 for u in bnc_users 
                    if "edwin.nieborg@bnc.nl" in str(u.get("emailaddress") or u.get("email") or "").lower() 
                    or "danja.berlo@bnc.nl" in str(u.get("emailaddress") or u.get("email") or "").lower())
            },
            "sample_users": sample_users,
            "safety_mechanisms": [
                "• Gebruik van dictionary om duplicaten te voorkomen",
                "• 0.3s delay tussen aanvragen om rate limiting te voorkomen",
                "• Herkansingen bij tijdelijke netwerkfouten",
                "• Case-insensitive email matching"
            ],
            "troubleshooting": [
                "Als geen gebruikers worden gevonden:",
                "1. Controleer of client_id=12 en site_id=18 correct zijn",
                "2. Bezoek /debug om te zien welke ID-velden beschikbaar zijn",
                "3. Pas de client_id/site_id aan in de code als nodig",
                "4. Controleer of de API key toegang heeft tot alle gebruikers"
            ],
            "note": "Deze app haalt ALLE gebruikers op en filtert alleen op basis van de aanwezige data in de /Users endpoint"
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
    log.info("🚀 HALO ALL USERS - DIRECTE FILTERING OP /Users")
    log.info("-"*70)
    log.info(f"✅ Gebruikt alleen /Users endpoint (geen /Clients of /Sites)")
    log.info(f"✅ Filtert op '@bnc' en valideert client_id={HALO_CLIENT_ID_NUM}/site_id={HALO_SITE_ID}")
    log.info("✅ Geen duplicaten door unieke gebruikersopslag")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Controleer de logs op '@bnc gebruiker' meldingen")
    log.info("3. Bezoek /users voor ALLE @bnc gebruikers met correcte koppeling")
    log.info("="*70)
    
    # Gebruik de poort zoals ingesteld in de omgeving
    app.run(host="0.0.0.0", port=port, debug=False)
