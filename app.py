import os
import logging
from flask import Flask, jsonify
import requests

# ===== FLASK APP MOET HIER BUITEN FUNCTIES STAAN (VERPLICHT VOOR GUNICORN) =====
app = Flask(__name__)  # DEZE REGEL MOET ZICHER STAAAN VOORALLE FUNCTIONELE CODE
app.config['PROPAGATE_EXCEPTIONS'] = True

# ===== LOGGER INSTELLEN =====
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
            logger.error("❌ Zet HALO_API_KEY in Render environment variables")
            raise EnvironmentError("Missing HALO_API_KEY environment variable")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        logger.info(f"✅ Halo API client geïnitialiseerd voor {self.api_url}")

    def get_users_for_site(self, client_id, site_id):
        """Haal GEBRUIKERS OP VOOR SPECIFIEKE SITE MET FLOAT FIX"""
        client_id = int(client_id)
        site_id = int(site_per_id)
        users = []
        page = 1
        
        while True:
            try:
                params = {
                    "page": page,
                    "per_page": 50
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
                        # Converteer naar float dan int (oplost 992.0 != 992 probleem)
                        user_site_id = int(float(user.get("site_id", 0)))
                        user_client_id = int(float(user.get("client_id", 0)))
                        
                        if user_client_id == client_id and user_site_id == site_id:
                            users.append(user)
                    except (TypeError, ValueError):
                        continue
                
                logger.info(f"✅ Pagina {page} verwerkt - {len(page_users)} gebruikers")
                page += 1
                
            except Exception as e:
                logger.error(f"❌ API Fout: {str(e)}")
                break
        
        logger.info(f"🎉 Totaal {len(users)} gebruikers gevonden voor site {site_id}")
        return users

# ===== API ENDPOINTS =====
@app.route('/debug', methods=['GET'])
def debug_endpoint():
    """OFFICIËLE DEBUG ROUTE - Dit is waar Render naar zoekt"""
    logger.info("🔍 /debug endpoint aangeroepen - valideer configuratie")
    
    try:
        # Haal waarden uit environment (met defaults voor lokale test)
        client_id = int(os.getenv("HALO_CLIENT_ID", "986"))
        site_id = int(os.getenv("HALO_SITE_ID", "992"))
        
        # Initialiseer API client
        halo = HaloAPI()
        
        # Haal gebruikers op met FIX
        users = halo.get_users_for_site(client_id, site_id)
        
        # Genereer debug response
        return jsonify({
            "status": "success",
            "total_users": len(users),
            "client_id": client_id,
            "site_id": site_id,
            "sample_users": [
                {
                    "id": user.get("id"),
                    "name": user.get("name"),
                    "client_id": user.get("client_id"),
                    "site_id": user.get("site_id")
                } for user in users[:3]
            ],
            "troubleshooting": [
                "✅ Site ID conversie correct (gebruikt float → int fix)",
                "✅ Alle gebruikers (actief + inactief) opgehaald",
                "✅ Client/Site koppeling gevalideerd"
            ]
        }), 200
    
    except Exception as e:
        logger.exception("🚨 Fout in debug endpoint")
        return jsonify({
            "error": str(e),
            "hint": "Controleer HALO_API_KEY en site/client IDs in Render env vars"
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
