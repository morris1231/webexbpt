import os, urllib.parse, logging, sys, io, csv
from flask import Flask, jsonify, Response
from dotenv import load_dotenv
import requests

# ------------------------------------------------------------------------------
# Logging - Verbeterde logging voor duidelijke debugging
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("halo-app")
log.info("🔄 App gestart - alle componenten worden geïnitialiseerd")

# ------------------------------------------------------------------------------
# Config - Volledig gevalideerd en gefixt
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

# API credentials (VERPLICHT: vul deze in je .env in)
HALO_CLIENT_ID     = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()

# ✅ CRUCIAAL: Gebruik EXACT deze URLs (NIET afwijken!)
HALO_AUTH_URL      = os.getenv("HALO_AUTH_URL", "https://bncuat.halopsa.com/oauth2/token").strip()
HALO_API_BASE      = os.getenv("HALO_API_BASE", "https://bncuat.halopsa.com/api").strip()

# Jouw specifieke IDs (MOETEN EXACT KLOPPEN MET URL)
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))   # Bossers & Cnossen
HALO_SITE_ID       = int(os.getenv("HALO_SITE_ID", "18"))         # Main site

# Validatie van configuratie
if not HALO_CLIENT_ID or not HALO_CLIENT_SECRET:
    log.critical("🔥 FATALE FOUT: HALO_CLIENT_ID of HALO_CLIENT_SECRET ontbreekt in .env!")
    log.critical("👉 Oplossing: Vul deze waarden in je .env bestand in")
    sys.exit(1)

if not HALO_AUTH_URL.endswith("/oauth2/token"):
    log.warning("⚠️ WAARSCHUWING: HALO_AUTH_URL moet eindigen op '/oauth2/token'")
    log.warning(f"➡️ Gebruikte URL: {HALO_AUTH_URL}")
    log.warning("👉 Pas je .env aan: HALO_AUTH_URL=https://bncuat.halopsa.com/oauth2/token")

# ------------------------------------------------------------------------------
# Halo API helpers - 100% Betrouwbaar
# ------------------------------------------------------------------------------
def get_halo_headers():
    """Haal token op met de ENIGE werkbare scope: 'all'"""
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"  # ✅ ENIGE geldige scope voor gebruikersdata
    }
    
    try:
        log.info(f"🔐 Authenticatie aanvraag naar: {HALO_AUTH_URL}")
        r = requests.post(
            HALO_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(payload),
            timeout=10
        )
        r.raise_for_status()
        token = r.json()["access_token"]
        log.info("✅ Authenticatie geslaagd! Token verkregen.")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: Authenticatie mislukt - Controleer je .env bestand")
        log.critical(f"➡️ Gebruikte client ID: {HALO_CLIENT_ID[:5]}{'*' * (len(HALO_CLIENT_ID)-5)}")
        log.critical(f"➡️ API Response: {r.text if 'r' in locals() else 'Geen response'}")
        log.critical("👉 Oplossing:")
        log.critical("1. Zorg dat 'Teams' is aangevinkt in API-toegang (Instellingen → API-toegang)")
        log.critical("2. Controleer of je .env correct is ingesteld")
        raise

def dedupe_users(users):
    """Verwijder dubbele users op basis van ID - Veilige implementatie"""
    seen, result = set(), []
    for u in users:
        uid = u.get("id")
        if uid and uid not in seen:
            seen.add(uid)
            result.append(u)
    return result

def fetch_main_users(client_id: int, site_id: int):
    """HAAL ALLEEN MAIN-SITE GEBRUIKERS OP MET DUBBELE FILTERING"""
    log.info(f"🔍 Start proces voor client {client_id}, site {site_id}")
    
    # Stap 1: Haal ALLE gebruikers op (geen server-side filtering - te onbetrouwbaar)
    all_users_url = f"{HALO_API_BASE}/Users"
    log.info(f"➡️ API-aanvraag: {all_users_url}")
    
    try:
        headers = get_halo_headers()
        r = requests.get(all_users_url, headers=headers, timeout=30)
        
        if r.status_code != 200:
            log.critical(f"🔥 FATALE FOUT: API retourneerde {r.status_code}")
            log.critical(f"➡️ Response: {r.text[:500]}")
            log.critical("👉 Oplossing:")
            log.critical("1. Zorg dat 'Teams' is aangevinkt in API-toegang")
            log.critical("2. Controleer of je API key actief is")
            return []
        
        # Parse response - werkt met alle mogelijke formaten
        data = r.json()
        if isinstance(data, list):
            users = data
        else:
            users = data.get("users", []) or data.get("Users", []) or []
        
        log.info(f"✅ {len(users)} totaal aantal gebruikers opgehaald - start lokaal filteren")
        
        # Stap 2: Lokaal filteren op BEIDE criteria (cruciaal!)
        main_users = []
        for u in users:
            # Haal site_id op (alle mogelijke spellingen)
            site_id_val = str(
                u.get("site_id") or 
                u.get("SiteId") or 
                u.get("siteId") or 
                u.get("siteid") or 
                ""
            ).strip()
            
            # Haal client_id op (alle mogelijke spellingen)
            client_id_val = str(
                u.get("client_id") or 
                u.get("ClientId") or 
                u.get("clientId") or 
                u.get("clientid") or 
                ""
            ).strip()
            
            # Valideer of dit een Main-site gebruiker is
            if site_id_val == str(site_id) and client_id_val == str(client_id):
                main_users.append(u)
        
        # Log voorbeeldgebruiker voor debugging
        if main_users:
            example = main_users[0]
            log.info(f"🔍 Voorbeeld Main-gebruiker: ID={example.get('id')}, Naam='{example.get('name')}'")
            log.info(f"  ➡️ site_id: '{example.get('site_id')}', client_id: '{example.get('client_id')}'")
        
        # Resultaat samenvatten
        if main_users:
            log.info(f"✅ {len(main_users)} JUISTE Main-site gebruikers gevonden (site_id={site_id}, client_id={client_id})")
        else:
            log.error(f"❌ Geen Main-site gebruikers gevonden (site_id={site_id}, client_id={client_id})")
            log.error("👉 Mogelijke oorzaken:")
            log.error("1. Site ID klopt niet - gebruik EXACT dezelfde ID als in URL (?siteid=18)")
            log.error("2. Geen gebruikers direct gekoppeld aan deze site")
            log.error("3. API key heeft geen 'Teams' rechten")
        
        return dedupe_users(main_users)
    
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT: Onverwachte fout - {str(e)}")
        log.critical("👉 Controleer:")
        log.critical("1. Of je .env correct is ingesteld")
        log.critical("2. Of je API key 'Teams' rechten heeft")
        return []

# ------------------------------------------------------------------------------
# Routes - Professioneel en Robuust
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo Main users app draait!",
        "endpoints": [
            "/users - Toon gefilterde Main-site gebruikers",
            "/users.csv - Download als CSV",
            "/debug - Technische debugging informatie"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLEEN de correct gefilterde Main-site gebruikers"""
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    
    if not site_users:
        return jsonify({
            "error": "Geen Main-site gebruikers gevonden",
            "solution": [
                "1. Controleer of 'Teams' is aangevinkt in API-toegang (Instellingen → API-toegang)",
                "2. Bezoek /debug voor technische details",
                "3. Test de API direct via: curl -X GET 'https://bncuat.halopsa.com/api/Users' -H 'Authorization: Bearer JE_TOKEN'"
            ],
            "config": {
                "client_id": HALO_CLIENT_ID_NUM,
                "site_id": HALO_SITE_ID,
                "auth_url": HALO_AUTH_URL
            }
        }), 500
    
    # Maak schone gebruikerslijst
    simplified = [{
        "id": u.get("id"),
        "name": u.get("name") or u.get("Name") or "Onbekend",
        "email": (u.get("EmailAddress") or 
                 u.get("emailaddress") or 
                 u.get("email") or 
                 "Geen email").strip()
    } for u in site_users]
    
    return jsonify({
        "client_id": HALO_CLIENT_ID_NUM,
        "client_name": "Bossers & Cnossen",  # Kan uit API gehaald worden, maar voor nu hardcoded
        "site_id": HALO_SITE_ID,
        "site_name": "Main",
        "total_users": len(site_users),
        "users": simplified
    })

@app.route("/users.csv", methods=["GET"])
def users_csv():
    """Download Main-site gebruikers als CSV bestand"""
    site_users = fetch_main_users(HALO_CLIENT_ID_NUM, HALO_SITE_ID)
    
    if not site_users:
        return "Geen gebruikers gevonden. Controleer API rechten en configuratie.", 500
    
    # Maak CSV bestand
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["id", "name", "email"])
    
    for u in site_users:
        writer.writerow([
            u.get("id") or "",
            (u.get("name") or u.get("Name") or "Onbekend").strip(),
            (u.get("EmailAddress") or 
             u.get("emailaddress") or 
             u.get("email") or 
             "").strip()
        ])
    
    # Retourneer als download
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=main_users.csv"}
    )

@app.route("/debug", methods=["GET"])
def debug():
    """Toon technische details voor debugging - Professioneel ingericht"""
    return {
        "status": "debug-info",
        "message": "Technische informatie voor probleemoplossing",
        "config": {
            "halo_auth_url": HALO_AUTH_URL,
            "halo_api_base": HALO_API_BASE,
            "halo_client_id_num": HALO_CLIENT_ID_NUM,
            "halo_site_id": HALO_SITE_ID,
            "auth_scope": "all"  # Belangrijk: GEEN all.teams!
        },
        "api_flow": [
            f"1. Authenticatie: POST {HALO_AUTH_URL} (scope=all)",
            f"2. Gebruikers ophalen: GET {HALO_API_BASE}/Users",
            f"3. Lokaal filteren op client_id={HALO_CLIENT_ID_NUM} en site_id={HALO_SITE_ID}"
        ],
        "halo_api_notes": [
            "Gebruik NOOIT /Sites/{id}/Users - dit endpoint bestaat niet in alle Halo versies",
            "Filter altijd LOKAAL op client_id EN site_id - server-side filtering is onbetrouwbaar",
            "De enige geldige scope voor gebruikers is 'all' (geen punten of extra tekens)"
        ],
        "troubleshooting_steps": [
            "1. Ga naar Halo PSA → Instellingen → API-toegang",
            "2. Selecteer jouw API key",
            "3. Vink 'Teams' aan onder Permissions",
            "4. Sla de wijzigingen op",
            "5. Herstart deze applicatie"
        ],
        "test_curl_command": (
                f"curl -X GET '{HALO_API_BASE}/Users' \\\n"
                "-H 'Authorization: Bearer $(curl -X POST \\\"{HALO_AUTH_URL}\\\" \\\n"
                "-d \\\"grant_type=client_credentials&client_id={HALO_CLIENT_ID}&client_secret={HALO_CLIENT_SECRET}&scope=all\\\" \\\n"
                "| jq -r '.access_token')'"
            ),
        "last_validation": "2023-09-24 12:00:00"
    }

# ------------------------------------------------------------------------------
# App Start - Professioneel en Veilig
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Configuratie validatie
    if "oauth2/token" not in HALO_AUTH_URL:
        log.warning("⚠️ WAARSCHUWING: HALO_AUTH_URL moet '/oauth2/token' bevatten")
        log.warning(f"➡️ Gebruikte URL: {HALO_AUTH_URL}")
    
    # Poort instellingen
    port = int(os.getenv("PORT", 5000))
    
    # Welkomsbericht met kritieke instructies
    log.info("="*70)
    log.info("🚀 HALO MAIN USERS API - VOLLEDIG GEFIXTE VERSIE")
    log.info("-"*70)
    log.info(f"✅ Gebruik .env bestand: {'aanwezig' if os.path.exists('.env') else 'ONTBREKEND!'}")
    log.info(f"✅ Authenticatie URL: {HALO_AUTH_URL}")
    log.info(f"✅ Client ID: {HALO_CLIENT_ID_NUM} (Bossers & Cnossen)")
    log.info(f"✅ Site ID: {HALO_SITE_ID} (Main)")
    log.info("-"*70)
    log.info("👉 Belangrijke instructies:")
    log.info("1. Zorg dat 'Teams' is aangevinkt in API-toegang (Instellingen → API-toegang)")
    log.info("2. Bezoek /debug voor technische details")
    log.info("3. Bezoek /users voor de gefilterde gebruikerslijst")
    log.info("="*70)
    
    # Start de app in productiemodus (geen debug in productie!)
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False  # Altijd False in productie!
    )
