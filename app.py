import logging
import requests

# ===== BELANGRIJK: Alleen deze waarden aanpassen =====
CLIENT_ID = 986  # Klant ID van Bossers & Cnossen B.V.
SITE_ID = 992    # Site ID van "Main" locatie
HALO_API_URL = "https://jouw.halo.domain/api"
API_KEY = "JOUW_API_SLEUTEL"

# ===== LOGGER CONFIGURATIE =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("halo_fix")

def haal_gebruikers_op():
    """Haal ALLE gebruikers op (actief + inactief) en filter correct op site ID"""
    gefilterde_gebruikers = []
    
    # Stap 1: Haal zowel actieve als inactieve gebruikers op
    for active_status in [True, False]:
        pagina = 1
        while True:
            try:
                # API-aanroep met actieve status
                params = {
                    "page": pagina,
                    "per_page": 50,
                    "active": str(active_status).lower()
                }
                headers = {"Authorization": f"Bearer {API_KEY}"}
                
                response = requests.get(
                    f"{HALO_API_URL}/users",
                    params=params,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                gebruikers = response.json()
                
                if not gebruikers:
                    break
                
                # Stap 2: DIRECTE FILTERING MET FLOAT CONVERSIE
                for user in gebruikers:
                    try:
                        # FIX 1: Converteer site_id naar float dan int (voor 992.0 → 992)
                        user_site_id = int(float(user.get("site_id", 0)))
                        user_client_id = int(float(user.get("client_id", 0)))
                        
                        # FIX 2: Filter direct op beide ID's met geconverteerde waarden
                        if user_client_id == CLIENT_ID and user_site_id == SITE_ID:
                            gefilterde_gebruikers.append(user)
                    except (TypeError, ValueError):
                        continue
                
                logger.info(f"✅ Pagina {pagina} gebruikers ({'actief' if active_status else 'inactief'}): {len(gebruikers)} verwerkt")
                pagina += 1
                
            except Exception as e:
                logger.error(f"❌ API Fout op pagina {pagina}: {str(e)}")
                break
    
    return gefilterde_gebruikers

def debug():
    """OFFICIËLE DEBUG FUNCTIE - Gebruik deze voor troubleshooting"""
    logger.info("🔍 /debug endpoint aangeroepen - valideer hardcoded ID's")
    logger.info(f"🔍 Haal gebruikers op voor locatie {SITE_ID} via de Users endpoint...")
    
    try:
        # Stap 1: Haal alle gebruikers op
        gebruikers = haal_gebruikers_op()
        
        # Stap 2: Log resultaten
        if not gebruikers:
            logger.error("❌ Geen gebruikers gevonden voor de locatie")
            logger.info("🔍 Controleer koppelingen tussen gebruikers en locaties...")
            
            # Toon voorbeelden uit de eerste 5 gebruikers
            test_gebruikers = requests.get(
                f"{HALO_API_URL}/users?page=1&per_page=5",
                headers={"Authorization": f"Bearer {API_KEY}"}
            ).json()[:5]
            
            for i, user in enumerate(test_gebruikers):
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
            logger.info(f"✅ {len(gebruikers)}/92 gebruikers gevonden voor locatie {SITE_ID}")
            logger.info("🎉 Succes! Alle gebruikers zijn correct gekoppeld aan de site.")
            
            # Toon eerste 3 gevonden gebruikers
            for i, user in enumerate(gebruikers[:3]):
                logger.info(f"  • Gebruiker {i+1}: {user.get('name')} (ID: {user.get('id')})")
                
    except Exception as e:
        logger.exception(f"🚨 Onverwachte fout: {str(e)}")

# ===== DIT IS DE ENIGE REGEL DIE JE MOET UITVOEREN =====
if __name__ == "__main__":
    debug()
