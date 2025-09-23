import os, requests, urllib.parse, json, logging, sys
from flask import Flask, request
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Logging configuratie
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("ticketbot")

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN", "").strip()
WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}

HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE = os.getenv("HALO_API_BASE", "").strip()

HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", "55"))
HALO_TEAM_ID = int(os.getenv("HALO_TEAM_ID", "1"))
HALO_DEFAULT_IMPACT = int(os.getenv("HALO_IMPACT", "3"))
HALO_DEFAULT_URGENCY = int(os.getenv("HALO_URGENCY", "3"))

HALO_ACTIONTYPE_PUBLIC = int(os.getenv("HALO_ACTIONTYPE_PUBLIC", "78"))

# Specifieke klant en site (Bossers & Cnossen / Main)
HALO_CLIENT_ID_NUM = int(os.getenv("HALO_CLIENT_ID_NUM", "12"))
HALO_SITE_ID = int(os.getenv("HALO_SITE_ID", "18"))

ticket_room_map = {}

# ------------------------------------------------------------------------------
# Halo helpers
# ------------------------------------------------------------------------------
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    r = requests.post(
        HALO_AUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(payload)
    )
    if r.status_code != 200:
        print(f"❌ Auth faalde: {r.status_code} {r.text}", flush=True)
    r.raise_for_status()
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "Content-Type": "application/json"
    }

def fetch_all_client_users(client_id: int):
    """Haalt ALLE users van een ClientID op met pagination."""
    h = get_halo_headers()
    all_users = []
    page = 1
    page_size = 100
    while True:
        url = f"{HALO_API_BASE}/Users?$filter=ClientID eq {client_id}&pageSize={page_size}&pageNumber={page}"
        r = requests.get(url, headers=h)
        if r.status_code != 200:
            log.error(f"❌ Fout bij ophalen users (page {page}): {r.status_code} {r.text}")
            break
        data = r.json()
        users = data.get("users", [])
        count = len(users)
        if not users:
            log.debug(f"📄 Page {page} had 0 users → stoppen.")
            break
        all_users.extend(users)
        log.debug(f"📄 Page {page}: {count} users (totaal nu {len(all_users)})")
        # ✅ Stop als minder dan page_size terugkomt (laatste pagina)
        if count < page_size:
            log.debug(f"📄 Stoppen op page {page}, want {count} < {page_size}")
            break
        page += 1
    log.info(f"✅ Totaal {len(all_users)} users opgehaald voor Client {client_id}")
    return all_users

def get_main_users():
    """Filter alleen users van site Main (SiteID=18) uit Client 12."""
    all_users = fetch_all_client_users(HALO_CLIENT_ID_NUM)
    main_users = [u for u in all_users if str(u.get("site_id")) == str(HALO_SITE_ID)
                                        or str(u.get("site_name","")).lower() == "main"]
    log.info(f"✅ {len(main_users)} users in Bossers & Cnossen / Main")
    return main_users

def dump_site_users():
    """Dump alle users van Main in de logs bij startup."""
    users = get_main_users()
    for u in users:
        print(
            f"UserID={u.get('id')} | Name={u.get('name')} | "
            f"Email={u.get('emailaddress')} | Site={u.get('site_name')}",
            flush=True
        )

def get_halo_user_id(email: str):
    """Zoek user in Main via email/login/adobject."""
    if not email: 
        return None
    users = get_main_users()
    email = email.strip().lower()
    for u in users:
        emails = {
            str(u.get("emailaddress") or "").lower(),
            str(u.get("networklogin") or "").lower(),
            str(u.get("adobject") or "").lower()
        }
        if email in emails:
            log.info(f"✅ Match: {email} → UserID {u.get('id')} (Site={u.get('site_name')})")
            return u.get("id")
    log.warning(f"❌ {email} niet gevonden in Bossers & Cnossen/Main")
    return None

# ------------------------------------------------------------------------------
# Ticket en notes functies
# ------------------------------------------------------------------------------
def safe_post_action(url, headers, payload, room_id=None):
    log.debug("➡️ Payload naar Halo:\n" + json.dumps(payload, indent=2))
    r = requests.post(url, headers=headers, json=payload)
    log.debug(f"⬅️ Halo response: {r.status_code} {r.text}")
    if r.status_code != 200 and room_id:
        send_message(room_id, f"⚠️ Error {r.status_code}:\n```\n{r.text}\n```")
    return r

def create_halo_ticket(summary, naam, email,
                       omschrijving="", sindswanneer="", watwerktniet="",
                       zelfgeprobeerd="", impacttoelichting="",
                       impact_id=3, urgency_id=3, room_id=None):
    user_id = get_halo_user_id(email)
    if not user_id:
        if room_id:
            send_message(room_id, f"❌ {email} hoort niet bij Bossers & Cnossen/Main. Ticket niet gemaakt.")
        return None

    h = get_halo_headers()
    ticket = {
        "Summary": summary,
        "Details": f"Aangemaakt door {naam} ({email})",
        "TypeID": HALO_TICKET_TYPE_ID,
        "TeamID": HALO_TEAM_ID,
        "Impact": int(impact_id),
        "Urgency": int(urgency_id),
        "SiteID": HALO_SITE_ID,
        "ClientID": HALO_CLIENT_ID_NUM,
        "CFReportedUser": f"{naam} ({email})"
    }
    r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[ticket])
    r.raise_for_status()
    data = r.json()[0] if isinstance(r.json(), list) else r.json()
    ticket_id = data.get("id") or data.get("ID")

    note = f"**Ticket aangemaakt door {naam} ({email})**\n\nOmschrijving: {omschrijving}\nSinds: {sindswanneer}\nWat werkt niet: {watwerktniet}\nZelf geprobeerd: {zelfgeprobeerd}\nImpact toelichting: {impacttoelichting}"
    payload = {
        "TicketID": int(ticket_id),
        "Details": note,
        "ActionTypeID": HALO_ACTIONTYPE_PUBLIC,
        "IsPrivate": False,
        "VisibleToCustomer": True,
        "UserID": int(user_id),
        "TimeSpent": 0
    }
    safe_post_action(f"{HALO_API_BASE}/Actions", headers=h, payload=payload)
    return {"id": ticket_id, "ref": ticket_id}

def add_note_to_ticket(ticket_id, text, sender="Webex", email=None, room_id=None):
    user_id = get_halo_user_id(email)
    if not user_id:
        send_message(room_id, f"❌ Geen notitie toegevoegd: {email} niet in Bossers & Cnossen/Main.")
        return
    h = get_halo_headers()
    payload = {
        "TicketID": int(ticket_id),
        "Details": f"{sender} ({email}) schreef:\n{text}",
        "ActionTypeID": HALO_ACTIONTYPE_PUBLIC,
        "IsPrivate": False,
        "VisibleToCustomer": True,
        "UserID": int(user_id),
        "TimeSpent": 0
    }
    safe_post_action(f"{HALO_API_BASE}/Actions", headers=h, payload=payload, room_id=room_id)

# ------------------------------------------------------------------------------
# Webex helpers
# ------------------------------------------------------------------------------
def send_message(room_id, text):
    requests.post("https://webexapis.com/v1/messages",
                  headers=WEBEX_HEADERS,
                  json={"roomId": room_id, "markdown": text})

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}

# ------------------------------------------------------------------------------
# Startup dump
# ------------------------------------------------------------------------------
print("🚀 Ticketbot start op", flush=True)
dump_site_users()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
