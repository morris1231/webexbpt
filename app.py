import os, requests, urllib.parse, json
from flask import Flask, request
from dotenv import load_dotenv

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
HALO_SITE_ID = int(os.getenv("HALO_SITE_ID", "18"))  # Bossers & Cnossen Main

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
    r.raise_for_status()
    return {
        "Authorization": f"Bearer {r.json()['access_token']}",
        "Content-Type": "application/json"
    }

def get_halo_user_id(email: str):
    """Zoek user in Halo en valideer of deze voorkomt in Bossers & Cnossen Main (SiteID 18)."""
    if not email:
        return None
    h = get_halo_headers()
    email = email.strip().lower()

    # 1. Globale search op Users
    url = f"{HALO_API_BASE}/Users?$filter=Email eq '{email}' or NetworkLogin eq '{email}' or ADObject eq '{email}'"
    r = requests.get(url, headers=h)
    if r.status_code != 200:
        print(f"❌ Error bij user lookup: {r.text}")
        return None
    users = r.json()
    if not users or not isinstance(users, list):
        print(f"❌ Geen user gevonden in globale search voor {email}")
        return None

    found_user = users[0]
    user_id = found_user.get("ID")
    if not user_id:
        return None

    # 2. Haal alle users van SiteID 18
    try:
        site_users = requests.get(f"{HALO_API_BASE}/Sites/{HALO_SITE_ID}/Users", headers=h).json()
    except Exception as e:
        print(f"❌ Kon site users niet ophalen: {e}")
        return None

    site_user_ids = [u.get("ID") for u in site_users if isinstance(u, dict)]

    if user_id in site_user_ids:
        print(f"✅ User {email} gevonden in SiteID {HALO_SITE_ID} → UserID {user_id}")
        return user_id
    else:
        print(f"❌ User {email} bestaat wel maar zit NIET in SiteID {HALO_SITE_ID}")
        return None

# ------------------------------------------------------------------------------
# Safe POST wrapper
# ------------------------------------------------------------------------------
def safe_post_action(url, headers, payload, room_id=None):
    print("➡️ Payload naar Halo:", json.dumps(payload, indent=2))
    r = requests.post(url, headers=headers, json=payload)
    print("⬅️ Halo response:", r.status_code, r.text)
    if r.status_code != 200 and room_id:
        send_message(room_id, f"⚠️ Halo error {r.status_code}:\n```\n{r.text}\n```")
    return r

# ------------------------------------------------------------------------------
# Ticket creation
# ------------------------------------------------------------------------------
def create_halo_ticket(summary, naam, email,
                       omschrijving="", sindswanneer="", watwerktniet="",
                       zelfgeprobeerd="", impacttoelichting="",
                       impact_id=3, urgency_id=3, room_id=None):
    h = get_halo_headers()
    user_id = get_halo_user_id(email)

    if not user_id:
        if room_id:
            send_message(room_id, f"❌ Het opgegeven e-mailadres **{email}** hoort niet bij Bossers & Cnossen (Main). Ticket wordt niet aangemaakt.")
        return None

    print(f"👤 Ticket aanmaker → Email: {email}, UserID: {user_id}")

    ticket = {
        "Summary": summary,
        "Details": f"👤 Ticket aangemaakt door {naam} ({email})",
        "TypeID": HALO_TICKET_TYPE_ID,
        "TeamID": HALO_TEAM_ID,
        "Impact": int(impact_id),
        "Urgency": int(urgency_id),
        "SiteID": HALO_SITE_ID,
        "CFReportedUser": f"{naam} ({email})"
    }
    r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[ticket])
    r.raise_for_status()
    data = r.json()[0] if isinstance(r.json(), list) else r.json()
    ticket_id = data.get("id") or data.get("ID")

    qa_note = (
        f"**Vragenlijst ingevuld door {naam} ({email}):**\n\n"
        f"- Probleemomschrijving: {omschrijving or '—'}\n"
        f"- Sinds wanneer: {sindswanneer or '—'}\n"
        f"- Wat werkt niet: {watwerktniet or '—'}\n"
        f"- Zelf geprobeerd: {zelfgeprobeerd or '—'}\n"
        f"- Impact toelichting: {impacttoelichting or '—'}\n"
        f"- Impact: {impact_id}\n"
        f"- Urgency: {urgency_id}\n"
    )
    note_payload = {
        "TicketID": int(ticket_id),
        "Details": qa_note,
        "Note": qa_note,
        "ActionTypeID": HALO_ACTIONTYPE_PUBLIC,
        "IsPrivate": False,
        "VisibleToCustomer": True,
        "UserID": int(user_id),
        "TimeSpent": 0
    }
    safe_post_action(f"{HALO_API_BASE}/Actions", headers=h, payload=note_payload)
    return {"id": ticket_id, "ref": ticket_id}

# ------------------------------------------------------------------------------
# Notes vanuit Webex
# ------------------------------------------------------------------------------
def add_note_to_ticket(ticket_id, text, sender="Webex", email=None, room_id=None):
    h = get_halo_headers()
    user_id = get_halo_user_id(email)
    if not user_id:
        send_message(room_id, f"❌ Kan geen notitie toevoegen: {email} hoort niet bij Bossers & Cnossen (Main).")
        return
    note_text = f"{sender} ({email}) schreef:\n{text}"
    payload = {
        "TicketID": int(ticket_id),
        "Details": note_text,
        "Note": note_text,
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

def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul het formulier hieronder in:",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": [
                    {"type": "Input.Text", "id": "name", "placeholder": "Naam"},
                    {"type": "Input.Text", "id": "email", "placeholder": "E-mailadres"},
                    {"type": "Input.Text", "id": "omschrijving", "isMultiline": True, "placeholder": "Probleemomschrijving"},
                    {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Sinds wanneer?"},
                    {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Wat werkt niet?"},
                    {"type": "Input.Text", "id": "zelfgeprobeerd", "isMultiline": True, "placeholder": "Zelf geprobeerd?"},
                    {"type": "Input.Text", "id": "impacttoelichting", "isMultiline": True, "placeholder": "Impact toelichting"},
                ],
                "actions": [{"type": "Action.Submit", "title": "Versturen"}]
            }
        }]}
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=card)

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    resource = data.get("resource")
    if resource == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS).json()
        text = msg.get("text", "").strip()
        room_id = msg.get("roomId")
        sender = msg.get("personEmail")
        if sender and sender.endswith("@webex.bot"):
            return {"status": "ignored"}
        if "nieuwe melding" in text.lower():
            send_adaptive_card(room_id)
            send_message(room_id, "📋 Vul het formulier hierboven in om een ticket te starten.")
        else:
            for t_id, rid in ticket_room_map.items():
                if rid == room_id:
                    add_note_to_ticket(t_id, text, sender, email=sender, room_id=room_id)

    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{action_id}",
                              headers=WEBEX_HEADERS).json().get("inputs", {})
        naam = inputs.get("name", "Onbekend")
        email = inputs.get("email", "")
        omschrijving = inputs.get("omschrijving", "")
        sindswanneer = inputs.get("sindswanneer", "")
        watwerktniet = inputs.get("watwerktniet", "")
        zelfgeprobeerd = inputs.get("zelfgeprobeerd", "")
        impacttoelichting = inputs.get("impacttoelichting", "")
        impact_id = inputs.get("impact", str(HALO_DEFAULT_IMPACT))
        urgency_id = inputs.get("urgency", str(HALO_DEFAULT_URGENCY))
        room_id = data["data"]["roomId"]
        summary = omschrijving or "Melding via Webex"

        ticket = create_halo_ticket(summary, naam, email,
                                    omschrijving, sindswanneer,
                                    watwerktniet, zelfgeprobeerd,
                                    impacttoelichting, impact_id, urgency_id,
                                    room_id=room_id)
        if ticket:
            ticket_room_map[ticket["id"]] = room_id
            send_message(room_id, f"✅ Ticket aangemaakt: **{ticket['ref']}**")
    return {"status": "ok"}

@app.route("/halo", methods=["POST"])
def halo_webhook():
    data = request.json
    t_id = data.get("TicketID") or data.get("Request", {}).get("ID")
    if not t_id or int(t_id) not in ticket_room_map:
        return {"status": "ignored"}
    h = get_halo_headers()

    # Status updates
    t_detail = requests.get(f"{HALO_API_BASE}/Tickets/{t_id}", headers=h)
    if t_detail.status_code == 200:
        status = t_detail.json().get("StatusName") or t_detail.json().get("Status")
        if status:
            send_message(ticket_room_map[int(t_id)], f"🔄 Status update: {status}")

    # Notes
    r = requests.get(f"{HALO_API_BASE}/Tickets/{t_id}/Actions", headers=h)
    if r.status_code == 200 and r.json():
        actions = r.json()
        last = sorted(actions, key=lambda x: x.get("ID", 0), reverse=True)[0]
        note = last.get("Details")
        created_by = last.get("User", {}).get("Name", "Onbekend")
        if note and not last.get("IsPrivate", False):
            send_message(ticket_room_map[int(t_id)], f"💬 Halo update door {created_by}:\n\n{note}")
    return {"status": "ok"}

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
