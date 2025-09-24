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

def get_all_email_addresses(user):
    """Haal ALLE mogelijke email adressen op uit de gebruiker"""
    email_fields = [
        "emailaddress", "email", "email2", "email3",
        "email_1", "email_2", "email_primary", "email_secondary",
        "EmailAddress", "Email", "Email2", "Email3"
    ]
    
    emails = []
    for field in email_fields:
        if field in user and user[field]:
            email = str(user[field]).strip()
            if email and "@" in email:
                emails.append((email.lower(), field))
    
    return emails

def get_all_client_info(user):
    """Verzamel ALLE client informatie uit de gebruiker"""
    client_info = {
        "names": [],
        "ids": [],
        "raw_data": {}
    }
    
    # Mogelijke client naam velden
    client_name_keys = ["client_name", "clientName", "ClientName", "clientname"]
    for key in client_name_keys:
        if key in user and user[key]:
            client_info["names"].append((user[key], key))
            client_info["raw_data"][key] = user[key]
    
    # Mogelijke client ID velden
    client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
    for key in client_id_keys:
        if key in user and user[key] is not None:
            client_info["ids"].append((str(user[key]), key))
            client_info["raw_data"][key] = str(user[key])
    
    return client_info

def get_all_site_info(user):
    """Verzamel ALLE site informatie uit de gebruiker"""
    site_info = {
        "names": [],
        "ids": [],
        "raw_data": {}
    }
    
    # Mogelijke site naam velden
    site_name_keys = ["site_name", "siteName", "SiteName", "sitename"]
    for key in site_name_keys:
        if key in user and user[key]:
            site_info["names"].append((user[key], key))
            site_info["raw_data"][key] = user[key]
    
    # Mogelijke site ID velden
    site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
    for key in site_id_keys:
        if key in user and user[key] is not None:
            site_info["ids"].append((str(user[key]), key))
            site_info["raw_data"][key] = str(user[key])
    
    return site_info

def fetch_all_bnc_users():
    """HAAL ALLE GEBRUIKERS OP EN FILTER OP '@bnc' ZONDER CLIENT/SITE FILTERING"""
    log.info("🔍 Start met het ophalen van alle gebruikers met '@bnc' email (geen filtering)")
    
    # Stap 1: Haal alle gebruikers op in ÉÉN API call
    log.info("➡️ API-aanvraag: Probeer alle gebruikers in één call op te halen")
    all_users = []
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
        
        # Stap 2: Filter op '@bnc' in ALLE email velden
        log.info("🔍 Filter gebruikers op '@bnc' in ALLE email velden (geen client/site filtering)")
        
        bnc_users = []
        no_email_count = 0
        bnc_count = 0
        
        for u in users:
            # Haal alle email adressen op
            emails = get_all_email_addresses(u)
            
            # Controleer of we een @bnc email hebben
            bnc_emails = []
            for email, field in emails:
                if "@bnc" in email:
                    bnc_emails.append((email, field))
            
            # Sla alleen op als we @bnc email hebben
            if bnc_emails:
                bnc_count += 1
                
                # Verzamel client en site informatie
                client_info = get_all_client_info(u)
                site_info = get_all_site_info(u)
                
                # Log gedetailleerde informatie
                user_name = u.get("name", "Onbekend")
                user_id = u.get("id", "Onbekend")
                
                # Log de gebruiker en alle relevante informatie
                log.info(f"📧 @bnc gebruiker gevonden: {user_name} (ID: {user_id})")
                
                # Log alle email adressen
                for email, field in emails:
                    if "@bnc" in email:
                        log.info(f"   ✅ @bnc email gevonden: {email} (veld: {field})")
                    else:
                        log.info(f"   ➡️ Email gevonden: {email} (veld: {field})")
                
                # Log client informatie
                if client_info["names"] or client_info["ids"]:
                    log.info("   ➡️ Client informatie gevonden:")
                    for name, field in client_info["names"]:
                        log.info(f"      - Naam: {name} (veld: {field})")
                    for id_val, field in client_info["ids"]:
                        log.info(f"      - ID: {id_val} (veld: {field})")
                else:
                    log.warning("   ⚠️ Waarschuwing: Geen client informatie gevonden")
                
                # Log site informatie
                if site_info["names"] or site_info["ids"]:
                    log.info("   ➡️ Site informatie gevonden:")
                    for name, field in site_info["names"]:
                        log.info(f"      - Naam: {name} (veld: {field})")
                    for id_val, field in site_info["ids"]:
                        log.info(f"      - ID: {id_val} (veld: {field})")
                else:
                    log.warning("   ⚠️ Waarschuwing: Geen site informatie gevonden")
                
                # Voeg toe aan resultaten
                bnc_users.append({
                    "user": u,
                    "client_info": client_info,
                    "site_info": site_info,
                    "bnc_emails": bnc_emails
                })
            else:
                log.debug(f"   ➡️ Gebruiker {u.get('name', 'Onbekend')} (ID: {u.get('id', 'Onbekend')}) heeft geen @bnc email")
        
        # Log samenvatting
        log.info(f"✅ Totaal @bnc gebruikers gevonden: {bnc_count}")
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
        "message": "Halo ALL BNC USERS app draait! Bezoek /users voor alle @bnc gebruikers",
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
            
            # Gebruik het eerste @bnc email adres
            email, email_field = item["bnc_emails"][0]
            
            # Bepaal client naam en ID
            client_name = "Onbekend"
            if item["client_info"]["names"]:
                client_name = item["client_info"]["names"][0][0]
            
            client_id = "Onbekend"
            if item["client_info"]["ids"]:
                client_id = item["client_info"]["ids"][0][0]
            
            # Bepaal site naam en ID
            site_name = "Onbekend"
            if item["site_info"]["names"]:
                site_name = item["site_info"]["names"][0][0]
            
            site_id = "Onbekend"
            if item["site_info"]["ids"]:
                site_id = item["site_info"]["ids"][0][0]
            
            simplified.append({
                "id": u.get("id"),
                "name": u.get("name") or "Onbekend",
                "email": email,
                "email_field": email_field,
                "client_name": client_name,
                "client_id": client_id,
                "site_name": site_name,
                "site_id": site_id
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
            # Gebruik het eerste @bnc email adres
            email, email_field = item["bnc_emails"][0]
            name = u.get("name") or "Onbekend"
            
            # Client informatie
            client_names = []
            for name_val, field in item["client_info"]["names"]:
                client_names.append(f"{name_val} ({field})")
            
            client_ids = []
            for id_val, field in item["client_info"]["ids"]:
                client_ids.append(f"{id_val} ({field})")
            
            # Site informatie
            site_names = []
            for name_val, field in item["site_info"]["names"]:
                site_names.append(f"{name_val} ({field})")
            
            site_ids = []
            for id_val, field in item["site_info"]["ids"]:
                site_ids.append(f"{id_val} ({field})")
            
            # Verzamel alle email velden
            email_fields = []
            for email, field in item["bnc_emails"]:
                email_fields.append(f"{field}: {email}")
            
            sample_users.append({
                "volgorde": i,
                "name": name,
                "email": email,
                "email_field": email_field,
                "client_names": ", ".join(client_names) if client_names else "Niet gevonden",
                "client_ids": ", ".join(client_ids) if client_ids else "Niet gevonden",
                "site_names": ", ".join(site_names) if site_names else "Niet gevonden",
                "site_ids": ", ".join(site_ids) if site_ids else "Niet gevonden",
                "email_fields": ", ".join(email_fields) if email_fields else "Geen emails",
                "user_id": u.get("id", "Onbekend")
            })
        
        # Analyseer de meest voorkomende client/sites
        client_name_counts = {}
        client_id_counts = {}
        site_name_counts = {}
        site_id_counts = {}
        
        for item in bnc_users:
            # Client namen
            for name, _ in item["client_info"]["names"]:
                client_name_counts[name] = client_name_counts.get(name, 0) + 1
            
            # Client ID's
            for id_val, _ in item["client_info"]["ids"]:
                client_id_counts[id_val] = client_id_counts.get(id_val, 0) + 1
            
            # Site namen
            for name, _ in item["site_info"]["names"]:
                site_name_counts[name] = site_name_counts.get(name, 0) + 1
            
            # Site ID's
            for id_val, _ in item["site_info"]["ids"]:
                site_id_counts[id_val] = site_id_counts.get(id_val, 0) + 1
        
        # Sorteer op aantal
        top_client_names = sorted(client_name_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_client_ids = sorted(client_id_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_site_names = sorted(site_name_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_site_ids = sorted(site_id_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Analyseer email velden
        email_field_counts = {}
        for item in bnc_users:
            for _, email_field in item["bnc_emails"]:
                email_field_counts[email_field] = email_field_counts.get(email_field, 0) + 1
        
        # Analyseer client/site combinaties
        client_site_combinations = {}
        for item in bnc_users:
            client_name = item["client_info"]["names"][0][0] if item["client_info"]["names"] else "Onbekend"
            site_name = item["site_info"]["names"][0][0] if item["site_info"]["names"] else "Onbekend"
            
            combination = f"{client_name} - {site_name}"
            client_site_combinations[combination] = client_site_combinations.get(combination, 0) + 1
        
        # Sorteer op aantal
        top_combinations = sorted(client_site_combinations.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "status": "debug-info",
            "api_flow": [
                "1. Authenticatie naar /auth/token (scope=all)",
                "2. Haal ALLE gebruikers op in ÉÉN API call (pageSize=250)",
                "3. FILTER OP '@bnc' IN ALLE EMAIL VELDEN (geen client/site filtering)"
            ],
            "configuration": {
                "halo_api_base": HALO_API_BASE
            },
            "current_counts": {
                "total_users_fetched": len(bnc_users),
                "total_bnc_users_found": len(bnc_users)
            },
            "api_issues": api_issues if api_issues else ["Geen API problemen gedetecteerd"],
            "email_field_usage": [{"field": field, "count": count} for field, count in email_field_counts.items()],
            "client_analysis": {
                "top_names": [{"name": name, "count": count} for name, count in top_client_names],
                "top_ids": [{"id": id_val, "count": count} for id_val, count in top_client_ids]
            },
            "site_analysis": {
                "top_names": [{"name": name, "count": count} for name, count in top_site_names],
                "top_ids": [{"id": id_val, "count": count} for id_val, count in top_site_ids]
            },
            "client_site_combinations": [{"combination": comb, "count": count} for comb, count in top_combinations],
            "sample_users": sample_users,
            "safety_mechanisms": [
                "• Gebruikt ÉÉN API call met pageSize=250",
                "• Scan ALLE mogelijke email velden voor '@bnc'",
                "• Verzamel ALLE client/site informatie (geen filtering)",
                "• Gedetailleerde logging van alle gevonden velden",
                "• Case-insensitive email matching"
            ],
            "troubleshooting": [
                "Als geen @bnc gebruikers worden gevonden:",
                "1. Controleer de logs op 'Gebruiker heeft geen @bnc email' meldingen",
                "2. Controleer of de emailadressen in Halo correct zijn ingesteld",
                "3. Bezoek /debug om te zien welke email velden worden gebruikt",
                "",
                "Als client/site informatie ontbreekt:",
                "1. Controleer of de gebruikers zijn gekoppeld aan een client/site in Halo",
                "2. Controleer of de API key toegang heeft tot client/site informatie",
                "3. Gebruik de 'client_analysis' en 'site_analysis' secties om te zien welke velden beschikbaar zijn"
            ],
            "note": "Deze app scant ALLE email velden voor '@bnc' en toont ALLE client/site informatie zoals deze in de API staat, zonder enige filtering"
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
    log.info("🚀 HALO ALL BNC USERS - ZONDER FILTERING")
    log.info("-"*70)
    log.info("✅ Toont ALLE gebruikers met '@bnc' email, ongeacht client/site")
    log.info("✅ Verzamelt ALLE client/site informatie zoals deze in de API staat")
    log.info("✅ Geen aannames over client/site namen of ID's")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /debug voor een complete analyse van de API response")
    log.info("2. Controleer de logs op gedetailleerde informatie over elke gebruiker")
    log.info("3. Gebruik de client/site analyse om te zien welke combinaties bestaan")
    log.info("="*70)
    
    # Gebruik de poort zoals ingesteld in de omgeving
    app.run(host="0.0.0.0", port=port, debug=False)
