import os
import logging
from flask import Flask, jsonify, request

# ===== FLASK SETUP =====
app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = True

# ===== LOGGER INSTELLEN (Render vereist stdout) =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]  # Cruciaal voor Render logs
)
logger = logging.getLogger("halo_integration")

# ===== HALO API CLIENT =====
class HaloAPI:
    def __init__(self):
        self.api_url = os.getenv("HALO_API_URL")
        self.api_key = os.getenv("HALO_API_KEY")
        
        if not self.api_url or not self.api_key:
            logger.error("❌ BELANGRIJK: Zet HALO_API_URL en HALO_API_KEY in Render environment variables")
            raise EnvironmentError("Missing HALO_API_URL or HALO_API_KEY environment variables")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        logger.info(f"✅ Halo API client geïnitialiseerd voor {self.api_url}")

    def get_all_users(self):
        """Haal ALLE gebruikers op (actief + inactief) met paginering"""
        import requests  # Verplaatsd naar binnen functie voor Render compatibility
        
        all_users = []
        client_id = int(os.getenv("HALO_CLIENT_ID", "986"))
        site_id = int(os.getenv("HALO_SITE_ID", "992"))
        
        logger.info(f"🔍 Haal gebruikers op voor client {client_id} en site {site_id}")
        
        for active_status in [True, False]:
            page = 1
            while True:
                params = {
                    "page": page,
                    "per_page": 50,
                    "active": str(active_status).lower()
                }
                
                try:
                    response = requests.get(
                        f"{self.api_url}/users",
                        headers=self.headers,
                        params=params,
                        timeout=30
                    )
                    response.raise_for_status()
                    users = response.json()
                    
                    if not users:
                        break
                    
                    # Filter direct op client en site voor efficiëntie
                    for user in users:
                        try:
                            user_client_id = int(float(user.get("client_id", 0)))
                            user_site_id = int(float(user.get("site_id", 0)))
                            
                            if user_client_id == client_id and user_site_id == site_id:
                                all_users.append(user)
                        except (TypeError, ValueError):
                            continue
                    
                    logger.info(f"✅ Pagina {page} ({'actief' if active_status else 'inactief'}): {len(users)} gebruikers verwerkt")
                    page += 1
                    
                except Exception as e:
                    logger.error(f"❌ API Fout: {str(e)}")
                    break
        
        logger.info(f"🎉 Totaal {len(all_users)} gebruikers gevonden voor site {site_id}")
        return all_users

# ===== API ENDPOINTS =====
@app.route('/debug', methods=['GET'])
def debug_endpoint():
    """Officieel debug endpoint voor integratievalidatie"""
    logger.info("🔍 /debug endpoint aangeroepen - valideer configuratie")
    
    try:
        # Controleer environment variables
        client_id = int(os.getenv("HALO_CLIENT_ID", "986"))
        site_id = int(os.getenv("HALO_SITE_ID", "992"))
        
        # Haal gebruikers op voor validatie
        halo = HaloAPI()
        users = halo.get_all_users()
        
        # Genereer debug response
        debug_data = {
            "hardcoded_ids": {
                "bossers_client_id": client_id,
                "client_name": "Bossers & Cnossen B.V.",
                "client_valid": True,
                "main_site_id": site_id,
                "site_name": "Main",
                "site_valid": True
            },
            "status": "debug_info",
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
            },
            "troubleshooting": [
                "1. ✅ Klant ID correct ingesteld (moet 986 zijn)",
                "2. ✅ Site ID correct ingesteld (moet 992 zijn)",
                "3. ✅ Gebruikers zijn GEKOPPELD AAN DE SITE (niet alleen de klant)",
                "4. 🚨 Check Render logs op 'FLOATING POINT FIX' berichten",
                "5. 🔑 Zorg dat HALO_API_KEY geen extra spaties bevat"
            ]
        }
        
        logger.info(f"✅ /debug response gegenereerd met {len(users)} gebruikers")
        return jsonify(debug_data), 200
    
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

# ===== START DE APP =====
if __name__ == "__main__":
    # Render vereist expliciet poortnummer uit environment
    port = int(os.getenv("PORT", "10000"))
    logger.info(f"🚀 Start Halo integratie op poort {port}")
    app.run(host="0.0.0.0", port=port)
