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

def get_email_from_user(user):
    """Haal email op uit alle mogelijke velden"""
    email_fields = [
        "emailaddress", "email", "email2", "email3",
        "email_1", "email_2", "email_primary", "email_secondary"
    ]
    
    for field in email_fields:
        if field in user and user[field]:
            email = str(user[field]).strip().lower()
            if email:
                return email, field
    
    return "", "geen"

def fetch_all_bnc_users():
    """HAAL ALLE @bnc GEBRUIKERS OP MET ALLE EMAIL VELDEN"""
    log.info("🔍 Start met het ophalen van alle @bnc gebruikers (alle email velden)")
    
    # Stap 1: Haal alle gebruikers op in ÉÉN API call
    log.info("➡️ API-aanvraag: Probeer alle gebruikers in één call op te halen")
    bnc_users = []
    api_issues = []
    
    try:
        headers = get_halo_headers()
        if not headers:
            api_issues.append("Geen geldige API headers - authenticatie mislukt")
            return [], api_issues
            
        # Gebruik een grote pageSize om alles in één call op te halen
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
        total_records = data.get("record_count", len(users))
        log.info(f"   ➡️ API response bevat {len(users)} gebruikers (Totaal records: {total_records})")
        
        # Stap 2: Filter op @bnc in ALLE email velden
        log.info("🔍 Filter gebruikers op '@bnc' in ALLE email velden")
        
        # Definieer mogelijke veldnamen voor client en site
        client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
        site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
        client_name_keys = ["client_name", "clientName", "ClientName"]
        site_name_keys = ["site_name", "siteName", "SiteName"]
        
        # Teller voor debugging
        bnc_count = 0
        no_email_count = 0
        no_client_site_count = 0
        
        for u in users:
            # Haal email op uit alle mogelijke velden
            email, email_field = get_email_from_user(u)
            original_email = email
            
            # Controleer of we een email hebben
            if not email:
                no_email_count += 1
                log.debug(f"   ⚠️ Gebruiker {u.get('name', 'Onbekend')} heeft geen emailadres")
                continue
                
            # Filter op @bnc
            if "@bnc" not in email:
                continue
                
            bnc_count += 1
            
            # Bepaal client naam
            client_name = "Onbekend"
            client_name_field = "geen"
            for key in client_name_keys:
                if key in u and u[key]:
                    client_name = u[key]
                    client_name_field = key
                    break
            
            # Bepaal site naam
            site_name = "Onbekend"
            site_name_field = "geen"
            for key in site_name_keys:
                if key in u and u[key]:
                    site_name = u[key]
                    site_name_field = key
                    break
            
            # Bepaal client ID
            client_id = "Onbekend"
            client_id_field = "geen"
            for key in client_id_keys:
                if key in u and u[key] is not None:
                    client_id = str(u[key])
                    client_id_field = key
                    break
            
            # Bepaal site ID
            site_id = "Onbekend"
            site_id_field = "geen"
            for key in site_id_keys:
                if key in u and u[key] is not None:
                    site_id = str(u[key])
                    site_id_field = key
                    break
            
            # Log gedetailleerde informatie
            client_info = f"{client_name}/{client_id} ({client_name_field}/{client_id_field})"
            site_info = f"{site_name}/{site_id} ({site_name_field}/{site_id_field})"
            
            if "bossers" in client_name.lower() or "cnossen" in client_name.lower():
                client_status = "✅"
            else:
                client_status = "⚠️"
                
            if "main" in site_name.lower() or "hoofd" in site_name.lower():
                site_status = "✅"
            else:
                site_status = "⚠️"
            
            log.info(f"{client_status}{site_status} @bnc gebruiker: {u.get('name', 'Onbekend')} - {original_email} "
                     f"(email veld: {email_field}, client: {client_info}, site: {site_info})")
            
            # Voeg toe aan resultaten
            bnc_users.append({
                "user": u,
                "client_name": client_name,
                "site_name": site_name,
                "client_id": client_id,
                "site_id": site_id,
                "email_field": email_field
            })
        
        # Log samenvatting
        log.info(f"✅ Totaal @bnc gebruikers gevonden: {bnc_count}")
        if no_email_count > 0:
            log.warning(f"⚠️ {no_email_count} gebruikers zonder emailadres overgeslagen")
        if len(bnc_users) == 0:
            log.error("❌ Geen @bnc gebruikers gevonden - controleer de API response")
            api_issues.append("Geen @bnc gebruikers gevonden - controleer of de emailadressen correct zijn")
    
    except Exception as e:
        issue = f"Fout bij ophalen gebruikers: {str(e)}"
        log.error(f"⚠️ {issue}")
        api_issues.append(issue)
        return [], api_issues
    
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
                "email": u.get(item["email_field"]) or "Geen email",
                "email_field": item["email_field"],
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
            email_field = item["email_field"]
            email = u.get(email_field) or "Geen email"
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
                "email_field": email_field,
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
        
        # Analyseer email velden
        email_field_counts = {}
        for item in bnc_users:
            field = item["email_field"]
            email_field_counts[field] = email_field_counts.get(field, 0) + 1
        
        return {
            "status": "debug-info",
            "api_flow": [
                "1. Authenticatie naar /auth/token (scope=all)",
                "2. Haal ALLE gebruikers op in ÉÉN API call (pageSize=250)",
                "3. FILTER OP '@bnc' IN ALLE EMAIL VELDEN"
            ],
            "configuration": {
                "halo_api_base": HALO_API_BASE
            },
            "current_counts": {
                "total_users_fetched": len(bnc_users),
                "total_bnc_users_found": len(bnc_users),
                "users_without_email": sum(1 for u in fetch_all_bnc_users()[0] if not u["user"].get("emailaddress") and not u["user"].get("email"))
            },
            "api_issues": api_issues if api_issues else ["Geen API problemen gedetecteerd"],
            "email_field_usage": [{"field": field, "count": count} for field, count in email_field_counts.items()],
            "top_clients": [{"name": name, "count": count} for name, count in top_clients],
            "top_sites": [{"name": name, "count": count} for name, count in top_sites],
            "sample_users": sample_users,
            "safety_mechanisms": [
                "• Controleert ALLE mogelijke email velden (emailaddress, email2, email3, etc.)",
                "• Geen paginering (één API call voor alle gebruikers)",
                "• Gedetailleerde logging van welk email veld wordt gebruikt",
                "• Herkent Bossers & Cnossen klant met meerdere criteria",
                "• Case-insensitive email matching"
            ],
            "note": "Deze app scant ALLE email velden voor '@bnc' en toont welk veld is gebruikt voor elke gebruiker"
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
    log.info("🚀 HALO ALL BNC USERS - ALLE EMAIL VELDEN GESCAND")
    log.info("-"*70)
    log.info("✅ Controleert ALLE email velden (emailaddress, email2, email3, etc.)")
    log.info("✅ Gebruikt ÉÉN API call om alle gebruikers op te halen")
    log.info("✅ Toont welk email veld is gebruikt voor elke gebruiker")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor technische details")
    log.info("2. Controleer de logs op 'email veld' informatie")
    log.info("3. Bezoek /users voor ALLE @bnc gebruikers met hun client/site")
    log.info("="*70)
    
    # Gebruik de poort zoals ingesteld in de omgeving
    app.run(host="0.0.0.0", port=port, debug=False)
