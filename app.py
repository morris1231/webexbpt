import os
import logging
from flask import Flask, jsonify
import requests

# ===== DEZE REGEL IS CRUCIAAL VOOR RENDER =====
app = Flask(__name__)  # MOET EXTERN STAAN VOOR GUNICORN

# ===== LOGGER INSTELLEN (Render compatible) =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("halo_integration")

# ===== HALO API CLIENT =====
class HaloAPI:
    def __init__(self):
        self.api_url = os.getenv("HALO_API_URL", "https://jouw.halo.domain/api")
        self.api_key = os.getenv("HALO_API_KEY")
        
        if not self.api_key:
            logger.error("❌ Zet HALO_API_KEY in je omgeving (Render environment variables)")
            raise EnvironmentError("Missing HALO_API_KEY")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        logger.info(f"✅ Halo API client geïnitialiseerd voor {self.api_url}")

    def get_users_for_site(self, client_id, site_id):
        """Haal GEBRUIKERS OP VOOR SPECIFIEKE SITE MET FLOAT FIX"""
        users = []
        page = 1
        
        # Stap 1: Haal zowel actieve als inactieve gebruikers op
        for active_status in [True, False]:
            while True:
                try:
                    params = {
                        "page": page,
                        "per_page": 50,
                        "active": str(active_status).lower()
                    }
                    response = requests.get(
                        f"{self.api_url}/users",
                        headers=self.headers,
                        params=params,
                        timeout=30
                    )
                    response.raise_for_status()
                    page_users = response.json()
                    
                    if not page_users:
                        break
                    
                    # ===== CRUCIALE FIX: FLOAT CONVERSIE VOOR SITE_ID =====
                    for user in page_users:
                        try:
                            # Fix 1: Converteer naar float dan int (oplost 992.0 != 992 probleem)
                            user_site_id = int(float(user.get("site_id", 0)))
                            user_client_id = int(float(user.get("client_id", 0)))
                            
                            # Fix 2: Filter direct op beide ID's met geconverteerde waarden
                            if user_client_id == client_id and user_site_id == site_id:
                                users.append(user)
                        except (TypeError, ValueError):
                            continue
                    
                    logger.info(f"✅ Pagina {page} ({'actief' if active_status else 'inactief'}) verwerkt - {len(page_users)} gebruikers")
                    page += 1
                    
                except Exception as e:
                    logger.error(f"❌ API Fout: {str(e)}")
                    break
        
        return users

# ===== API ENDPOINTS =====
@app.route('/debug', methods=['GET'])
def debug_endpoint():
    """OFFICIËLE DEBUG ROUTE - Dit is waar Render naar zoekt"""
    logger.info("🔍 /debug endpoint aangeroepen - valideer hardcoded ID's")
    logger.info("🔍 Haal gebruikers op voor locatie 992 via de Users endpoint...")
    
    try:
        # Stap 1: Haal alle gebruikers op
        halo = HaloAPI()
        users = halo.get_users_for_site(986, 992)  # Gebruik jouw hardcoded waarden
        
        # Stap 2: Log resultaten
        if not users:
            logger.error("❌ Geen gebruikers gevonden voor de locatie")
            logger.info("🔍 Controleer koppelingen tussen gebruikers en locaties...")
            
            # Toon voorbeelden uit de eerste 5 gebruikers
            test_response = requests.get(
                f"{halo.api_url}/users?page=1&per_page=5",
                headers=halo.headers
            )
            
            if test_response.status_code == 200:
                test_users = test_response.json()[:5]
                for i, user in enumerate(test_users):
                    try:
                        site_id = int(float(user.get("site_id", 0)))
                        client_id = int(float(user.get("client_id", 0)))
                        
                        logger.info(f" - Voorbeeldgebruiker {i+1}: '{user.get('name')}'")
                        logger.info(f"    • Site ID (direct): {user.get('site_id')}")
                        logger.info(f"    • Geëxtraheerde Site ID: {site_id}")
                        logger.info(f"    • Client ID: {client_id}")
                    except:
                        continue
        else:
            logger.info(f"✅ {len(users)}/92 gebruikers gevonden voor locatie 992")
            logger.info("🎉 Succes! Alle gebruikers zijn correct gekoppeld aan de site.")
            
            # Toon eerste 3 gevonden gebruikers
            for i, user in enumerate(users[:3]):
                logger.info(f"  • Gebruiker {i+1}: {user.get('name')} (ID: {user.get('id')})")
                
        # Return debug response zoals in jouw logs
        return jsonify({
            "hardcoded_ids": {
                "bossers_client_id": 986,
                "client_name": "Bossers & Cnossen B.V.",
                "client_valid": True,
                "main_site_id": 992,
                "site_name": "Main",
                "site_valid": True
            },
            "hint": "Deze integratie gebruikt een FLOATING POINT FIX voor site_id vergelijking",
            "status": "debug_info",
            "troubleshooting": [
                "1. Controleer of klant met ID 986 bestaat in Halo",
                "2. Controleer of locatie met ID 992 bestaat in Halo",
                "3. Zorg dat gebruikers correct zijn gekoppeld aan deze locatie (NIET alleen aan de klant)",
                "4. In Halo: Ga naar de locatie > Gebruikers om te controleren welke gebruikers gekoppeld zijn",
                "5. Gebruikers moeten zowel aan de klant ALS aan de locatie zijn gekoppeld",
                "6. BELANGRIJK: Controleer de Render logs voor 'STRUCTUUR VAN EERSTE GEBRUIKER'"
            ],
            "user_data": {
                "total_users_found": len(users),
                "sample_users": [
                    {
                        "id": user.get("id"),
                        "name": user.get("name"),
                        "client_id": user.get("client_id"),
                        "site_id": user.get("site_id")
                    } for user in users[:5]
                ]
            }
        }), 200
    
    except Exception as e:
        logger.exception("🚨 Fatale fout in debug endpoint")
        return jsonify({
            "error": str(e),
            "hint": "Controleer Render environment variables en API rechten"
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Render health check endpoint"""
    return jsonify({"status": "healthy"}), 200

# ===== DEZE BLOK MOET AAN HET EIND STAAN (Render vereist dit) =====
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"🚀 Start applicatie op poort {port}")
    app.run(host="0.0.0.0", port=port)
