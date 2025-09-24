import os, urllib.parse, logging, sys, time
from flask import Flask, jsonify, request
from dotenv import load_dotenv
import requests
import hashlib
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

def calculate_response_hash(response_data):
    """Bereken een hash van de API response om herhaling te detecteren"""
    try:
        # Haal de users lijst op
        users = response_data.get("users", [])
        if not users:
            users = response_data.get("Users", [])
        
        if not users:
            return "empty_response"
        
        # Maak een string van alle gebruikers ID's en emails
        user_identifiers = [f"{u.get('id', '')}:{str(u.get('emailaddress', '') or u.get('email', '')).lower()}" 
                           for u in users if u.get("id") is not None]
        user_identifiers.sort()  # Zorg voor consistente volgorde
        
        # Bereken een hash van de samengevoegde ID's
        hash_input = "|".join(user_identifiers)
        return hashlib.md5(hash_input.encode()).hexdigest()
    except Exception as e:
        log.error(f"⚠️ Fout bij berekenen response hash: {str(e)}")
        return "error_hash"

def fetch_all_bnc_users():
    """HAAL ALLE @bnc GEBRUIKERS OP MET VOLLEDIGE PAGINERING VALIDATIE"""
    log.info("🔍 Start met het ophalen van alle @bnc gebruikers met volledige pagineringsvalidatie")
    
    # Gebruik een dictionary om duplicaten te voorkomen
    all_users = {}
    seen_hashes = {}
    page = 1
    max_pages = 100
    consecutive_empty = 0
    total_bnc_count = 0
    repeated_content = 0
    api_issues = []

    while page <= max_pages:
        users_url = f"{HALO_API_BASE}/Users?page={page}&pageSize=50"
        log.info(f"➡️ API-aanvraag (pagina {page}): {users_url}")
        
        try:
            headers = get_halo_headers()
            if not headers:
                api_issues.append("Geen geldige API headers - authenticatie mislukt")
                return [], api_issues
                
            start_time = time.time()
            r = requests.get(users_url, headers=headers, timeout=30)
            request_time = time.time() - start_time
            
            if r.status_code != 200:
                issue = f"API FOUT ({r.status_code}): {r.text[:200]}"
                log.error(f"❌ {issue}")
                api_issues.append(issue)
                
                if r.status_code in [429, 500, 502, 503, 504]:
                    wait_time = 2 if r.status_code == 429 else 3
                    log.info(f"⏳ Te veel verzoeken, wacht {wait_time} seconden voordat we opnieuw proberen...")
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
                return [], api_issues
            
            # Bereken een hash van de response om herhaling te detecteren
            response_hash = calculate_response_hash(data)
            log.debug(f"   ➡️ Response hash: {response_hash}")
            
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
            total_records = data.get("totalRecords", data.get("TotalRecords", "Onbekend"))
            total_pages = data.get("totalPages", data.get("TotalPages", "Onbekend"))
            current_page = data.get("page", data.get("Page", page))
            page_size = data.get("pageSize", data.get("PageSize", 50))
            
            log.info(f"   ➡️ Paginering metadata: Pagina {current_page}/{total_pages} ({page_size} per pagina), Totaal records: {total_records}")
            
            # Controleer op lege response
            if not users:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    log.info("✅ Stoppen met ophalen na 3 lege pagina's")
                    break
                page += 1
                time.sleep(0.5)
                continue
            
            # Log de eerste en laatste gebruiker van de pagina voor debugging
            first_user = users[0]
            last_user = users[-1]
            
            first_user_email = first_user.get("emailaddress") or first_user.get("email") or "Geen email"
            first_user_id = first_user.get("id", "Onbekend")
            
            last_user_email = last_user.get("emailaddress") or last_user.get("email") or "Geen email"
            last_user_id = last_user.get("id", "Onbekend")
            
            log.info(f"   ➡️ Eerste gebruiker op deze pagina: {first_user.get('name', 'Onbekend')} - {first_user_email} (ID: {first_user_id})")
            log.info(f"   ➡️ Laatste gebruiker op deze pagina: {last_user.get('name', 'Onbekend')} - {last_user_email} (ID: {last_user_id})")
            log.info(f"   ➡️ API response tijd: {request_time:.2f} seconden")
            
            # Controleer op herhaalde response
            if response_hash in seen_hashes:
                repeated_content += 1
                previous_page = seen_hashes[response_hash]
                log.warning(f"⚠️ Waarschuwing: Dezelfde inhoud ontvangen als op pagina {previous_page} (herhaling #{repeated_content})")
                
                if repeated_content >= 2:
                    issue = f"Paginering probleem: API retourneert herhaaldelijk dezelfde inhoud (gecontroleerd op {repeated_content} herhalingen)"
                    log.error(f"❌ {issue}")
                    api_issues.append(issue)
                    
                    # Probeer een andere aanpak als paginering faalt
                    log.info("🔧 Probeer alternatieve aanpak voor paginering...")
                    alternative_users = try_alternative_pagination()
                    if alternative_users:
                        log.info("✅ Alternatieve paginering methode werkt!")
                        for user_id, user in alternative_users.items():
                            if user_id not in all_users:
                                all_users[user_id] = user
                    break
            else:
                seen_hashes[response_hash] = page
            
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
                if user_id:
                    # Filter op @bnc
                    email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
                    is_bnc = "@bnc" in email
                    
                    if is_bnc:
                        bnc_users += 1
                        total_bnc_count += 1
                    
                    if user_id not in all_users:
                        all_users[user_id] = u
                        new_users += 1
            
            log.info(f"✅ Pagina {page}: {len(users)} gebruikers opgehaald")
            log.info(f"   ➡️ {new_users} nieuwe gebruikers toegevoegd aan de database")
            log.info(f"   ➡️ {bnc_users} @bnc gebruikers gevonden op deze pagina (totaal: {total_bnc_count})")
            
            # Controleer of we minder dan 50 gebruikers hebben (laatste pagina)
            if len(users) < 50:
                log.info("✅ Laatste pagina bereikt (minder dan 50 gebruikers)")
                break
            
            page += 1
            time.sleep(0.3)
            
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
        # Haal email op (case-insensitive)
        email = str(u.get("emailaddress", "") or u.get("email", "")).strip().lower()
        
        # Sla de originele email op voor logging
        original_email = u.get("emailaddress") or u.get("email") or "Geen email"
        
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
            "site_id": site_id
        })
        
        log.info(f"📧 @bnc gebruiker: {u.get('name', 'Onbekend')} - {original_email} "
                 f"(client: {client_name}/{client_id}, site: {site_name}/{site_id})")
    
    log.info(f"✅ Totaal @bnc gebruikers gevonden: {len(bnc_users)}")
    
    return bnc_users, api_issues

def try_alternative_pagination():
    """Probeer alternatieve paginering methoden als de standaard methode faalt"""
    log.info("🔧 Probeert alternatieve paginering methoden...")
    alternative_users = {}
    
    # Methode 1: Gebruik offset in plaats van page
    log.info("   ➡️ Probeert paginering met offset i.p.v. page")
    offset = 0
    page_size = 50
    
    while offset < 500:  # Beperk tot 10 pagina's voor deze test
        users_url = f"{HALO_API_BASE}/Users?offset={offset}&limit={page_size}"
        log.info(f"   ➡️ API-aanvraag met offset (offset={offset}): {users_url}")
        
        try:
            headers = get_halo_headers()
            if not headers:
                break
                
            r = requests.get(users_url, headers=headers, timeout=30)
            
            if r.status_code != 200:
                log.warning(f"   ⚠️ Alternatieve API FOUT ({r.status_code}): {r.text}")
                break
                
            try:
                data = r.json()
            except:
                log.warning("   ⚠️ Kan alternatieve API response niet parsen als JSON")
                break
            
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
                break
            
            # Verwerk gebruikers
            for u in users:
                user_id = str(u.get("id", ""))
                if not user_id:
                    for key in ["UserId", "userID", "user_id", "ID"]:
                        if key in u and u[key]:
                            user_id = str(u[key])
                            break
                
                if user_id and user_id not in alternative_users:
                    alternative_users[user_id] = u
            
            log.info(f"   ✅ Offset {offset}: {len(users)} gebruikers opgehaald")
            
            if len(users) < page_size:
                break
                
            offset += page_size
            time.sleep(0.5)
            
        except Exception as e:
            log.warning(f"   ⚠️ Fout bij alternatieve paginering: {str(e)}")
            break
    
    # Methode 2: Gebruik een grotere page size
    if not alternative_users:
        log.info("   ➡️ Probeert paginering met grotere page size")
        users_url = f"{HALO_API_BASE}/Users?page=1&pageSize=250"
        
        try:
            headers = get_halo_headers()
            if not headers:
                return alternative_users
                
            r = requests.get(users_url, headers=headers, timeout=30)
            
            if r.status_code == 200:
                try:
                    data = r.json()
                    log.info("   ✅ Geslaagd: API ondersteunt grotere page size (250)")
                    
                    # Verwerk 'data' wrapper
                    if "data" in data and isinstance(data["data"], dict):
                        users_data = data["data"]
                    else:
                        users_data = data
                    
                    # Haal de users lijst op
                    users = users_data.get("users", [])
                    if not users:
                        users = users_data.get("Users", [])
                    
                    # Verwerk gebruikers
                    for u in users:
                        user_id = str(u.get("id", ""))
                        if not user_id:
                            for key in ["UserId", "userID", "user_id", "ID"]:
                                if key in u and u[key]:
                                    user_id = str(u[key])
                                    break
                        
                        if user_id and user_id not in alternative_users:
                            alternative_users[user_id] = u
                    
                    log.info(f"   ✅ Opgehaald: {len(users)} gebruikers met pageSize=250")
                except:
                    log.warning("   ⚠️ Kan API response niet parsen als JSON")
            else:
                log.warning(f"   ⚠️ API FOUT ({r.status_code}) bij poging met grotere page size: {r.text}")
                
        except Exception as e:
            log.warning(f"   ⚠️ Fout bij alternatieve paginering methode 2: {str(e)}")
    
    if alternative_users:
        log.info(f"✅ Alternatieve paginering methode geretourneerd {len(alternative_users)} gebruikers")
    else:
        log.error("❌ Geen succesvolle alternatieve paginering methode gevonden")
    
    return alternative_users

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
            "/api-test - Test de API connectiviteit"
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
                "email": u.get("emailaddress") or u.get("email") or "Geen email",
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
                "2. Haal ALLE gebruikers op via /Users met paginering (50 per pagina)",
                "3. FILTER OP '@bnc' IN EMAIL (geen client/site filtering)"
            ],
            "configuration": {
                "halo_api_base": HALO_API_BASE
            },
            "current_counts": {
                "total_unique_users_fetched": len(bnc_users),
                "total_bnc_users_found": len(bnc_users)
            },
            "api_issues": api_issues if api_issues else ["Geen API problemen gedetecteerd"],
            "top_clients": [{"name": name, "count": count} for name, count in top_clients],
            "top_sites": [{"name": name, "count": count} for name, count in top_sites],
            "sample_users": sample_users,
            "safety_mechanisms": [
                "• Gebruik van dictionary om duplicaten te voorkomen",
                "• Response hashing om herhaling te detecteren",
                "• Logt eerste en laatste gebruiker van elke pagina",
                "• Paginering metadata analyse",
                "• API response tijd meting",
                "• Alternatieve paginering methoden bij problemen",
                "• Case-insensitive email matching"
            ],
            "note": "Deze app valideert de API paginering en probeert alternatieve methoden bij problemen"
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
        
        if headers:
            try:
                r = requests.get(test_url, headers=headers, timeout=10)
                api_status = r.status_code
                if r.status_code == 200:
                    try:
                        data = r.json()
                        api_response = json.dumps(data)[:500] + "..." if len(json.dumps(data)) > 500 else json.dumps(data)
                        api_call_success = True
                    except:
                        api_response = r.text[:500]
                else:
                    api_response = r.text[:500]
            except Exception as e:
                api_response = str(e)
        
        # Test 3: Paginering test
        log.info("   ➡️ Test 3: Paginering test")
        pagination_test = "Ongetest"
        if api_call_success:
            try:
                # Haal pagina 1 op
                r1 = requests.get(f"{HALO_API_BASE}/Users?page=1&pageSize=2", headers=headers, timeout=10)
                data1 = r1.json() if r1.status_code == 200 else {}
                users1 = data1.get("users", []) or data1.get("Users", [])
                
                # Haal pagina 2 op
                r2 = requests.get(f"{HALO_API_BASE}/Users?page=2&pageSize=2", headers=headers, timeout=10)
                data2 = r2.json() if r2.status_code == 200 else {}
                users2 = data2.get("users", []) or data2.get("Users", [])
                
                # Vergelijk de gebruikers
                if users1 and users2:
                    first_user_page1 = users1[0].get("id")
                    first_user_page2 = users2[0].get("id")
                    
                    if first_user_page1 != first_user_page2:
                        pagination_test = "Succesvol - verschillende inhoud per pagina"
                    else:
                        pagination_test = "Mislukt - dezelfde inhoud op meerdere pagina's"
                else:
                    pagination_test = "Mislukt - geen gebruikers gevonden"
            except Exception as e:
                pagination_test = f"Fout: {str(e)}"
        
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
                "response_sample": api_response
            },
            "pagination_test": {
                "result": pagination_test,
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
    log.info("✅ Valideert of API echt pagineert (geen herhaalde pagina's)")
    log.info("✅ Logt eerste en laatste gebruiker van elke pagina")
    log.info("✅ Meet API response tijd")
    log.info("✅ Test alternatieve paginering methoden bij problemen")
    log.info("✅ Bevat API connectiviteit tester")
    log.info("-"*70)
    log.info("👉 VOLG DEZE STAPPEN VOOR VOLLEDIGE DEKING:")
    log.info("1. Bezoek /api-test EERST om API connectiviteit te testen")
    log.info("2. Controleer de logs op 'Eerste gebruiker' en 'Laatste gebruiker' meldingen")
    log.info("3. Bezoek /debug voor technische details over paginering")
    log.info("4. Bezoek /users voor ALLE @bnc gebruikers met hun client/site")
    log.info("="*70)
    
    # Gebruik de poort zoals ingesteld in de omgeving
    app.run(host="0.0.0.0", port=port, debug=False)
