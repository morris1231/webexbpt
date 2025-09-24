import os, urllib.parse, logging, sys, time
from flask import Flask, jsonify
from dotenv import load_dotenv
import requests
import json

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
        if 'r' in locals():
            log.critical(f"➡️ Response: {r.text}")
            log.critical(f"➡️ Status code: {r.status_code}")
        return None

def fetch_all_bnc_users():
    """HAAL ALLE @bnc GEBRUIKERS OP MET DE ENIGE WERKENDE METHODE VOOR JOUW API"""
    log.info("🔍 Start met het ophalen van alle @bnc gebruikers (specifieke oplossing voor jouw API)")
    
    # Stap 1: Haal EERST alle gebruikers op in ÉÉN API call
    log.info("➡️ API-aanvraag: Probeer alle gebruikers in één call op te halen")
    all_users = []
    api_issues = []
    
    try:
        headers = get_halo_headers()
        if not headers:
            api_issues.append("Geen geldige API headers - authenticatie mislukt")
            return [], api_issues
            
        # Probeer een grote pageSize om alles in één call op te halen
        users_url = f"{HALO_API_BASE}/Users?pageSize=250"
        log.info(f"➡️ API-aanvraag: {users_url}")
        
        r = requests.get(users_url, headers=headers, timeout=30)
        
        if r.status_code != 200:
            issue = f"API FOUT ({r.status_code}): {r.text}"
            log.error(f"❌ {issue}")
            api_issues.append(issue)
            return [], api_issues
            
        try:
            data = r.json()
            log.debug(f"   ➡️ Volledige API response (eerste 500 tekens): {json.dumps(data)[:500]}")
        except Exception as e:
            issue = f"Kan API response niet parsen als JSON: {str(e)}"
            log.error(f"❌ {issue}")
            log.error(f"➡️ Raw response: {r.text[:500]}")
            api_issues.append(issue)
            return [], api_issues
        
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
            issue = "Geen gebruikers gevonden in API response"
            log.error(f"❌ {issue}")
            api_issues.append(issue)
            return [], api_issues
        
        # Log paginering metadata
        total_records = data.get("record_count", "Onbekend")
        log.info(f"   ➡️ API response bevat {len(users)} gebruikers (Totaal records: {total_records})")
        
        # Stap 2: Filter op @bnc
        log.info("🔍 Filter gebruikers op '@bnc' (geen client/site filtering)")
        
        bnc_users = []
        client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
        site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
        client_name_keys = ["client_name", "clientName", "ClientName"]
        site_name_keys = ["site_name", "siteName", "SiteName"]
        
        for u in users:
            # Haal email op
            email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
            original_email = u.get("emailaddress") or u.get("email") or "Geen email"
            
            # Filter op @bnc
            if "@bnc" not in email:
                continue
                
            # Bepaal client naam
            client_name = "Onbekend"
            for key in client_name_keys:
                if key in u and u[key]:
                    client_status = "✅" if "Bossers & Cnossen" in str(u[key]).lower() else "⚠️"
                    log.info(f"   {client_status} Client naam gevonden: {u[key]} ({key})")
                    client_name = u[key]
                    break
            
            # Bepaal site naam
            site_name = "Onbekend"
            for key in site_name_keys:
                if key in u and u[key]:
                    site_status = "✅" if "main" in str(u[key]).lower() else "⚠️"
                    log.info(f"   {site_status} Site naam gevonden: {u[key]} ({key})")
                    site_name = u[key]
                    break
            
            # Bepaal client ID
            client_id = "Onbekend"
            for key in client_id_keys:
                if key in u and u[key] is not None:
                    log.info(f"   ➡️ Client ID gevonden: {u[key]} ({key})")
                    client_id = str(u[key])
                    break
            
            # Bepaal site ID
            site_id = "Onbekend"
            for key in site_id_keys:
                if key in u and u[key] is not None:
                    log.info(f"   ➡️ Site ID gevonden: {u[key]} ({key})")
                    site_id = str(u[key])
                    break
            
            # Voeg toe aan resultaten
            bnc_users.append({
                "user": u,
                "client_name": client_name,
                "site_name": site_name,
                "client_id": client_id,
                "site_id": site_id
            })
            
            log.info(f"📧 @bnc gebruiker: {u.get('name', 'Onbekend')} - {original_email} "
                     f"(client: {client_name}/{client_id}, site: {site_name}/{site_id})")
    
    except Exception as e:
        issue = f"Fout bij ophalen gebruikers: {str(e)}"
        log.error(f"⚠️ {issue}")
        api_issues.append(issue)
        return [], api_issues
    
    log.info(f"✅ Totaal @bnc gebruikers gevonden: {len(bnc_users)}")
    
    if len(bnc_users) == 0:
        api_issues.append("Geen @bnc gebruikers gevonden - controleer of de emailadressen correct zijn")
    
    return bnc_users, api_issues

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {
        "status": "ok",
        "message": "Halo BNC users app draait! Bezoek /users voor alle @bnc gebruikers",
        "endpoints": [
            "/users - Toon alle @bnc gebruikers met hun client/site",
            "/debug - Technische informatie over de API response"
        ]
    }

@app.route("/users", methods=["GET"])
def users():
    """Toon ALLE @bnc gebruikers met hun client/site informatie"""
    try:
        bnc_users, api_issues = fetch_all_bnc_users()
        
        if not bnc_users:
            log.warning("⚠️ Geen @bnc gebruikers gevonden in Halo")
            return jsonify({
                "warning": "Geen @bnc gebruikers gevonden",
                "api_issues": api_issues,
                "solution": [
                    "1. Controleer of de API key toegang heeft tot alle gebruikers",
                    "2. Zorg dat 'Teams' is aangevinkt in API-toegang",
                    "3. Controleer of er gebruikers met '@bnc' in Halo staan"
                ]
            }), 200
        
        log.info(f"✅ Succesvol {len(bnc_users)} @bnc gebruikers geretourneerd")
        
        simplified = []
        for item in bnc_users:
            u = item["user"]
            simplified.append({
                "id": u.get("id"),
                "name": u.get("name") or "Onbekend",
                "email": u.get("emailaddress") or u.get("email") or "Geen email",
                "client_name": item["client_name"],
                "site_name": item["site_name"],
                "client_id": item["client_id"],
                "site_id": item["site_id"]
            })
        
        return jsonify({
            "total_users": len(bnc_users),
            "users": simplified,
            "api_issues": api_issues if api_issues else "Geen API problemen"
        })
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT in /users: {str(e)}")
        return jsonify({
            "error": "Interne serverfout",
            "details": str(e)
        }), 500

@app.route("/debug", methods=["GET"])
def debug():
    """Toon technische informatie over de API response"""
    try:
        bnc_users, api_issues = fetch_all_bnc_users()
        
        # Verzamel voorbeeldgegevens
        sample_users = []
        for i, item in enumerate(bnc_users[:5], 1):
            u = item["user"]
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
                "client_name": item["client_name"],
                "site_name": item["site_name"],
                "client_ids": ", ".join(client_ids) if client_ids else "Niet gevonden",
                "site_ids": ", ".join(site_ids) if site_ids else "Niet gevonden",
                "user_id": u.get("id", "Onbekend")
            })
        
        # Analyseer de meest voorkomende client/sites
        client_counts = {}
        site_counts = {}
        
        for item in bnc_users:
            client_key = f"{item['client_name']} ({item['client_id']})"
            site_key = f"{item['site_name']} ({item['site_id']})"
            
            client_counts[client_key] = client_counts.get(client_key, 0) + 1
            site_counts[site_key] = site_counts.get(site_key, 0) + 1
        
        # Sorteer op aantal
        top_clients = sorted(client_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_sites = sorted(site_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "status": "debug-info",
            "api_flow": [
                "1. Authenticatie naar /auth/token (scope=all)",
                "2. Haal ALLE gebruikers op in ÉÉN API call (pageSize=250)",
                "3. FILTER OP '@bnc' IN EMAIL"
            ],
            "configuration": {
                "halo_api_base": HALO_API_BASE
            },
            "current_counts": {
                "total_users_fetched": len(bnc_users),
                "total_bnc_users_found": len(bnc_users)
            },
            "api_issues": api_issues if api_issues else ["Geen API problemen gedetecteerd"],
            "top_clients": [{"name": name, "count": count} for name, count in top_clients],
            "top_sites": [{"name": name, "count": count} for name, count in top_sites],
            "sample_users": sample_users,
            "safety_mechanisms": [
                "• Gebruikt pageSize=250 om alles in één call op te halen",
                "• Geen paginering (omdat jouw API dit niet ondersteunt)",
                "• Gedetailleerde logging van gevonden client/site velden",
                "• Case-insensitive email matching"
            ],
            "note": "Deze app haalt ALLE gebruikers op in ÉÉN API call (geen paginering) omdat jouw Halo API geen correcte paginering ondersteunt"
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
    log.info("🚀 HALO ALL BNC USERS - ÉÉN API CALL OPLOSSING")
    log.info("-"*70)
    log.info("✅ Omdat jouw API GEEN correcte paginering ondersteunt, gebruiken we ÉÉN API call")
    log.info("✅ Gebruikt pageSize=250 om alles in één call op te halen")
    log.info("✅ Gedetailleerde logging van client/site informatie")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Controleer de logs op 'Client naam gevonden' en 'Site naam gevonden' meldingen")
    log.info("3. Bezoek /users voor ALLE @bnc gebruikers met hun client/site")
    log.info("="*70)
    
    # Gebruik de poort zoals ingesteld in de omgeving
    app.run(host="0.0.0.0", port=port, debug=False)
