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
        "email_1", "email_2", "email_primary", "email_secondary",
        "EmailAddress", "Email", "Email2", "Email3"
    ]
    
    for field in email_fields:
        if field in user and user[field]:
            email = str(user[field]).strip().lower()
            if email and "@" in email:  # Alleen geldige emailadressen
                return email, field
    
    return "", "geen"

def fetch_all_bnc_users():
    """HAAL ALLE @bnc GEBRUIKERS OP MET ECHTE PAGINERING EN VOLLEDIGE DEBUGGING"""
    log.info("🔍 Start met het ophalen van alle @bnc gebruikers met volledige pagineringsdebugging")
    
    # Gebruik een dictionary om duplicaten te voorkomen
    all_users = {}
    seen_hashes = {}
    page = 1
    max_pages = 20  # Verhoogd van 10 naar 20 voor volledige dekking
    consecutive_empty = 0
    total_bnc_count = 0
    repeated_content = 0
    api_issues = []
    page_hashes = {}

    while page <= max_pages:
        users_url = f"{HALO_API_BASE}/Users?page={page}&pageSize=50"
        log.info(f"➡️ API-aanvraag (pagina {page}): {users_url}")
        
        try:
            headers = get_halo_headers()
            if not headers:
                api_issues.append("Geen geldige API headers - authenticatie mislukt")
                break
                
            start_time = time.time()
            r = requests.get(users_url, headers=headers, timeout=30)
            request_time = time.time() - start_time
            
            if r.status_code != 200:
                issue = f"API FOUT ({r.status_code}): {r.text[:200]}"
                log.error(f"❌ {issue}")
                api_issues.append(issue)
                
                if r.status_code in [429, 500, 502, 503, 504]:
                    wait_time = 2 if r.status_code == 429 else 3
                    log.info(f"⏳ Te veel verzoeken, wacht {wait_time} seconden...")
                    time.sleep(wait_time)
                    continue
                break
                
            try:
                data = r.json()
                # Log de ruwe response voor debugging (alleen de eerste 500 tekens)
                log.debug(f"   ➡️ Raw API response (eerste 500 tekens): {json.dumps(data)[:500]}")
            except Exception as e:
                issue = f"Kan API response niet parsen als JSON: {str(e)}"
                log.error(f"❌ {issue}")
                log.error(f"➡️ Raw response: {r.text[:500]}")
                api_issues.append(issue)
                break
            
            # Bereken een hash van de response om herhaling te detecteren
            response_hash = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
            page_hashes[page] = response_hash
            
            log.debug(f"   ➡️ Response hash voor pagina {page}: {response_hash}")
            
            # Verwerk 'data' wrapper
            if "data" in data and isinstance(data["data"], dict):
                users_data = data["data"]
            else:
                users_data = data
            
            # Haal de users lijst op
            users = users_data.get("users", [])
            if not users:
                users = users_data.get("Users", [])
            
            # Log paginering metadata als die beschikbaar is
            total_records = data.get("record_count", data.get("TotalRecords", "Onbekend"))
            total_pages = data.get("totalPages", data.get("TotalPages", "Onbekend"))
            current_page = data.get("page", data.get("Page", page))
            page_size = data.get("pageSize", data.get("PageSize", 50))
            
            log.info(f"   ➡️ Paginering metadata: Pagina {current_page}/{total_pages} ({page_size} per pagina), Totaal records: {total_records}")
            
            # Log de eerste en laatste gebruiker van de pagina voor debugging
            if users:
                first_user = users[0]
                last_user = users[-1]
                
                first_user_email = first_user.get("emailaddress") or first_user.get("email") or "Geen email"
                first_user_id = first_user.get("id", "Onbekend")
                
                last_user_email = last_user.get("emailaddress") or last_user.get("email") or "Geen email"
                last_user_id = last_user.get("id", "Onbekend")
                
                log.info(f"   ➡️ Eerste gebruiker op deze pagina: {first_user.get('name', 'Onbekend')} - {first_user_email} (ID: {first_user_id})")
                log.info(f"   ➡️ Laatste gebruiker op deze pagina: {last_user.get('name', 'Onbekend')} - {last_user_email} (ID: {last_user_id})")
                log.info(f"   ➡️ API response tijd: {request_time:.2f} seconden")
            else:
                log.warning(f"   ⚠️ Waarschuwing: Lege response op pagina {page}")
            
            # Controleer op herhaalde response
            if response_hash in seen_hashes:
                repeated_page = seen_hashes[response_hash]
                repeated_content += 1
                log.warning(f"⚠️ Waarschuwing: Dezelfde inhoud ontvangen als op pagina {repeated_page} (herhaling #{repeated_content})")
                
                # Log de inhoud van de herhaalde pagina's voor vergelijking
                if repeated_page in page_hashes and page in page_hashes:
                    log.info(f"   ➡️ Hash van pagina {repeated_page}: {page_hashes[repeated_page]}")
                    log.info(f"   ➡️ Hash van pagina {page}: {page_hashes[page]}")
                
                if repeated_content >= 2:
                    log.info("✅ Stoppen met ophalen na 2 herhalingen van dezelfde inhoud")
                    break
            else:
                seen_hashes[response_hash] = page
            
            # Controleer op lege response
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
                    for key in ["UserId", "userID", "user_id", "ID", "id_int"]:
                        if key in u and u[key]:
                            user_id = str(u[key])
                            break
                
                # Sla gebruiker op met ID als sleutel om duplicaten te voorkomen
                if user_id and user_id not in all_users:
                    all_users[user_id] = u
                    new_users += 1
                    
                    # Controleer op @bnc
                    email, email_field = get_email_from_user(u)
                    is_bnc = "@bnc" in email
                    
                    if is_bnc:
                        bnc_users += 1
                        total_bnc_count += 1
                        
                        # Log alle email velden voor debugging
                        email_fields = []
                        for field in ["emailaddress", "email", "email2", "email3"]:
                            if field in u and u[field]:
                                email_fields.append(f"{field}: {u[field]}")
                        
                        log.info(f"📧 @bnc gebruiker gevonden: {u.get('name', 'Onbekend')} - {email} (veld: {email_field})")
                        if email_fields:
                            log.info(f"   ➡️ Alle email velden: {', '.join(email_fields)}")
            
            log.info(f"✅ Pagina {page}: {len(users)} gebruikers opgehaald")
            log.info(f"   ➡️ {new_users} nieuwe gebruikers toegevoegd aan de database")
            log.info(f"   ➡️ {bnc_users} @bnc gebruikers gevonden op deze pagina (totaal: {total_bnc_count})")
            
            # Controleer of we minder dan 50 gebruikers hebben (laatste pagina)
            if len(users) < 50:
                log.info("✅ Laatste pagina bereikt (minder dan 50 gebruikers)")
                break
            
            page += 1
            time.sleep(0.5)  # Verhoogd van 0.3 naar 0.5 voor betere rate limiting
            
        except Exception as e:
            issue = f"Fout bij ophalen pagina {page}: {str(e)}"
            log.error(f"⚠️ {issue}")
            api_issues.append(issue)
            time.sleep(1)
            continue
    
    log.info(f"✅ Totaal unieke gebruikers opgehaald: {len(all_users)}")
    log.info(f"✅ Totaal unieke @bnc gebruikers gevonden: {total_bnc_count}")
    
    # Stap 2: Filter alleen op @bnc, geen client/site filtering
    log.info("🔍 Filter gebruikers op '@bnc' (geen client/site filtering)")
    
    bnc_users = []
    
    # Definieer mogelijke veldnamen voor client en site
    client_id_keys = ["client_id", "ClientId", "clientId", "ClientID", "clientid", "client_id_int"]
    site_id_keys = ["site_id", "SiteId", "siteId", "SiteID", "siteid", "site_id_int"]
    client_name_keys = ["client_name", "clientName", "ClientName"]
    site_name_keys = ["site_name", "siteName", "SiteName"]
    
    for user_id, u in all_users.items():
        # Haal email op
        email, email_field = get_email_from_user(u)
        original_email = u.get(email_field.replace("_", "")) or "Geen email"
        
        # Filter op @bnc
        if "@bnc" not in email:
            continue
            
        # Bepaal client naam
        client_name = "Onbekend"
        for key in client_name_keys:
            if key in u and u[key]:
                client_name = u[key]
                break
        
        # Bepaal site naam
        site_name = "Onbekend"
        for key in site_name_keys:
            if key in u and u[key]:
                site_name = u[key]
                break
        
        # Bepaal client ID
        client_id = "Onbekend"
        for key in client_id_keys:
            if key in u and u[key] is not None:
                client_id = str(u[key])
                break
        
        # Bepaal site ID
        site_id = "Onbekend"
        for key in site_id_keys:
            if key in u and u[key] is not None:
                site_id = str(u[key])
                break
        
        # Voeg toe aan resultaten
        bnc_users.append({
            "user": u,
            "client_name": client_name,
            "site_name": site_name,
            "client_id": client_id,
            "site_id": site_id,
            "email_field": email_field
        })
    
    log.info(f"✅ Totaal @bnc gebruikers gevonden: {len(bnc_users)}")
    
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
            "/debug - Technische informatie over de API response",
            "/api-test - Test de API connectiviteit en paginering"
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
            }), 200  # Geen fout, gewoon een waarschuwing
        
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
            "api_issues": api_issues if api_issues else "Geen API problemen gedetecteerd"
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
            
            # Verzamel alle email velden
            email_fields = []
            for field in ["emailaddress", "email", "email2", "email3"]:
                if field in u and u[field]:
                    email_fields.append(f"{field}: {u[field]}")
            
            sample_users.append({
                "volgorde": i,
                "name": name,
                "email": email,
                "email_field": email_field,
                "client_name": item["client_name"],
                "site_name": item["site_name"],
                "client_ids": ", ".join(client_ids) if client_ids else "Niet gevonden",
                "site_ids": ", ".join(site_ids) if site_ids else "Niet gevonden",
                "email_fields": ", ".join(email_fields) if email_fields else "Geen emails",
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
        
        # Paginering analyse
        pagination_analysis = {
            "total_pages_attempted": max(page-1, 1),
            "pages_with_data": 0,
            "empty_pages": 0,
            "repeated_content_pages": 0
        }
        
        # Hier zou je de paginering analyse toevoegen als je die data hebt
        
        return {
            "status": "debug-info",
            "api_flow": [
                "1. Authenticatie naar /auth/token (scope=all)",
                "2. Haal ALLE gebruikers op via /Users met paginering (50 per pagina)",
                "3. FILTER OP '@bnc' IN ALLE EMAIL VELDEN"
            ],
            "configuration": {
                "halo_api_base": HALO_API_BASE,
                "max_pages": 20,
                "page_size": 50
            },
            "current_counts": {
                "total_unique_users_fetched": len(bnc_users),
                "total_bnc_users_found": len(bnc_users),
                "users_without_email": sum(1 for u in bnc_users if not u["user"].get("emailaddress") and not u["user"].get("email"))
            },
            "api_issues": api_issues if api_issues else ["Geen API problemen gedetecteerd"],
            "email_field_usage": [{"field": field, "count": count} for field, count in email_field_counts.items()],
            "top_clients": [{"name": name, "count": count} for name, count in top_clients],
            "top_sites": [{"name": name, "count": count} for name, count in top_sites],
            "pagination_analysis": pagination_analysis,
            "sample_users": sample_users,
            "safety_mechanisms": [
                "• Gebruik van dictionary om duplicaten te voorkomen",
                "• Response hashing om herhaling te detecteren",
                "• Logt eerste en laatste gebruiker van elke pagina",
                "• Paginering metadata analyse",
                "• API response tijd meting",
                "• Case-insensitive email matching",
                "• Controleert ALLE mogelijke email velden",
                "• Verhoogde delay (0.5s) om rate limiting te voorkomen"
            ],
            "troubleshooting": [
                "Als geen @bnc gebruikers worden gevonden:",
                "1. Controleer de logs op 'Eerste gebruiker op deze pagina' meldingen",
                "2. Controleer of de emailadressen in de juiste velden staan",
                "3. Bezoek /api-test om de API connectiviteit te testen",
                "",
                "Als paginering problemen optreden:",
                "1. Controleer de 'Paginering metadata' in de logs",
                "2. Zoek naar 'Dezelfde inhoud ontvangen' waarschuwingen",
                "3. Verhoog de 'max_pages' waarde in de code als nodig"
            ],
            "note": "Deze app scant ALLE email velden voor '@bnc' en valideert de paginering door meerdere pagina's te controleren"
        }
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT in /debug: {str(e)}")
        return jsonify({
            "error": "Interne serverfout",
            "details": str(e)
        }), 500

@app.route("/api-test", methods=["GET"])
def api_test():
    """Test de API connectiviteit en paginering"""
    try:
        log.info("🔧 Start API connectiviteit test")
        
        # Test 1: Authenticatie
        log.info("   ➡️ Test 1: Authenticatie")
        headers = get_halo_headers()
        auth_success = bool(headers)
        
        # Test 2: Basis API call
        log.info("   ➡️ Test 2: Basis API call")
        test_url = f"{HALO_API_BASE}/Users?page=1&pageSize=1"
        api_call_success = False
        api_status = "Onbekend"
        api_response = "Geen response"
        api_structure = "Onbekend"
        
        if headers:
            try:
                r = requests.get(test_url, headers=headers, timeout=10)
                api_status = r.status_code
                if r.status_code == 200:
                    try:
                        data = r.json()
                        api_response = json.dumps(data)[:500] + "..." if len(json.dumps(data)) > 500 else json.dumps(data)
                        
                        # Analyseer de API structuur
                        if "data" in data and isinstance(data["data"], dict):
                            api_structure = "Wrapped response (data wrapper)"
                        else:
                            api_structure = "Direct response"
                            
                        # Check of gebruikers lijst bestaat
                        users = data.get("users", []) or data.get("Users", [])
                        if "data" in data:
                            users = data["data"].get("users", []) or data["data"].get("Users", [])
                        
                        if users:
                            api_call_success = True
                            log.info(f"   ✅ API response bevat gebruikers (structuur: {api_structure})")
                        else:
                            log.warning("   ⚠️ API response bevat GEEN gebruikers")
                    except Exception as e:
                        api_response = str(e)
                        log.error(f"   ❌ Kan API response niet parsen: {str(e)}")
                else:
                    api_response = r.text[:500]
            except Exception as e:
                api_response = str(e)
                log.error(f"   ❌ Fout bij API call: {str(e)}")
        
        # Test 3: Paginering test
        log.info("   ➡️ Test 3: Paginering test")
        pagination_test = "Ongetest"
        pagination_details = []
        
        if api_call_success:
            try:
                pages_to_test = 3  # Test eerste 3 pagina's
                page_contents = {}
                
                for page_num in range(1, pages_to_test + 1):
                    url = f"{HALO_API_BASE}/Users?page={page_num}&pageSize=2"
                    r = requests.get(url, headers=headers, timeout=10)
                    
                    if r.status_code == 200:
                        try:
                            data = r.json()
                            # Verwerk 'data' wrapper
                            if "data" in data and isinstance(data["data"], dict):
                                users = data["data"].get("users", []) or data["data"].get("Users", [])
                            else:
                                users = data.get("users", []) or data.get("Users", [])
                            
                            # Sla eerste gebruiker op voor vergelijking
                            if users:
                                first_user_id = users[0].get("id", "Onbekend")
                                page_contents[page_num] = first_user_id
                                
                                # Log voor debug
                                email = users[0].get("emailaddress") or users[0].get("email") or "Geen email"
                                pagination_details.append(f"Pagina {page_num}: ID {first_user_id}, Email {email}")
                            else:
                                page_contents[page_num] = "leeg"
                                pagination_details.append(f"Pagina {page_num}: Lege response")
                        except:
                            page_contents[page_num] = "parse_error"
                    else:
                        page_contents[page_num] = f"error_{r.status_code}"
                
                # Analyseer paginering
                unique_pages = set(page_contents.values())
                if len(unique_pages) == 1:
                    pagination_test = "Mislukt - dezelfde inhoud op alle pagina's"
                elif len(unique_pages) == pages_to_test:
                    pagination_test = "Succesvol - unieke inhoud op elke pagina"
                else:
                    pagination_test = "Gedeeltelijk succes - sommige pagina's herhalen"
                
            except Exception as e:
                pagination_test = f"Fout: {str(e)}"
                pagination_details.append(f"Fout bij paginering test: {str(e)}")
        
        return {
            "status": "api-test",
            "authentication": {
                "success": auth_success,
                "message": "Authenticatie geslaagd" if auth_success else "Authenticatie mislukt - controleer je API credentials"
            },
            "api_call": {
                "success": api_call_success,
                "url": test_url,
                "status_code": api_status,
                "response_sample": api_response,
                "response_structure": api_structure
            },
            "pagination_test": {
                "result": pagination_test,
                "details": pagination_details,
                "note": "Een succesvolle paginering test toont verschillende gebruikers op elke pagina"
            },
            "troubleshooting": [
                "Als authenticatie mislukt:",
                "1. Controleer of HALO_CLIENT_ID en HALO_CLIENT_SECRET correct zijn",
                "2. Zorg dat de API key 'all' scope heeft",
                "3. Controleer of de API key actief is",
                "",
                "Als API call mislukt:",
                "1. Controleer of de URL correct is",
                "2. Zorg dat de API key toegang heeft tot de Users endpoint",
                "3. Controleer of 'Teams' is aangevinkt in API-toegang",
                "",
                "Als paginering mislukt:",
                "1. Probeer de alternatieve paginering methoden in /debug",
                "2. Controleer of de API ondersteunt wat je probeert",
                "3. Neem contact op met Halo support voor API documentatie"
            ]
        }
    except Exception as e:
        log.critical(f"🔥 FATALE FOUT in /api-test: {str(e)}")
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
    log.info("🚀 HALO ALL BNC USERS - VOLLEDIGE PAGINERING VALIDATIE")
    log.info("-"*70)
    log.info("✅ Echte paginering met maximaal 20 pagina's (geen herhalingen)")
    log.info("✅ Logt eerste en laatste gebruiker van ELKE pagina")
    log.info("✅ Controleert ALLE email velden (emailaddress, email2, email3, etc.)")
    log.info("✅ Bevat uitgebreide API-tester voor paginering")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek EERST /api-test om de API connectiviteit te testen")
    log.info("2. Controleer de logs op 'Eerste gebruiker op deze pagina' meldingen")
    log.info("3. Bezoek /debug voor technische details over de API response")
    log.info("4. Bezoek /users voor ALLE @bnc gebruikers met hun client/site")
    log.info("="*70)
    
    # Gebruik de poort zoals ingesteld in de omgeving
    app.run(host="0.0.0.0", port=port, debug=False)
