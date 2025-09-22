import os, requests, urllib.parse, json
from flask import Flask, request
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN", "").strip()
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"}

HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE = os.getenv("HALO_API_BASE", "").strip()

HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", "55"))
HALO_TEAM_ID = int(os.getenv("HALO_TEAM_ID", "1"))
HALO_DEFAULT_IMPACT = int(os.getenv("HALO_IMPACT", "3"))
HALO_DEFAULT_URGENCY = int(os.getenv("HALO_URGENCY", "3"))

# ✅ Juiste ID van "Public / Customer Visible Note" uit Halo Config
HALO_ACTIONTYPE_PUBLIC = int(os.getenv("HALO_ACTIONTYPE_PUBLIC", "78"))

ticket_room_map = {}

# ------------------------------------------------------------------------------
# HALO Helpers
# ------------------------------------------------------------------------------
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    r = requests.post(HALO_AUTH_URL,
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data=urllib.parse.urlencode(payload))
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

def get_halo_user_by_email(email):
    if not email:
        return None, None, None
    h = get_halo_headers()
    r = requests.get(f"{HALO_API_BASE}/Users?$filter=Email eq '{email}'", headers=h)
    if r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0:
        user = r.json()[0]
        return user.get("ID"), user.get("CustomerID"), user.get("Name")
    return None, None, None

# ------------------------------------------------------------------------------
# Ticket creation
# ------------------------------------------------------------------------------
def create_halo_ticket(summary, naam, email,
                       omschrijving="", sindswanneer="", watwerktniet="",
                       zelfgeprobeerd="", impacttoelichting="",
                       impact_id=3, urgency_id=3):
    h = get_halo_headers()
    user_id, customer_id, _ = get_halo_user_by_email(email)

    ticket = {
        "Summary": summary,
        "Details": f"👤 Ticket aangemaakt door {naam} ({email})",
        "TypeID": HALO_TICKET_TYPE_ID,
        "TeamID": HALO_TEAM_ID,
        "Impact": int(impact_id),
        "Urgency": int(urgency_id),
        "CFReportedUser": f"{naam} ({email})",
        "CFReportedCompany": str(customer_id) if customer_id else ""
    }

    r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[ticket])
    print("🎫 Ticket response:", r.status_code, r.text[:200])
    r.raise_for_status()
    data = r.json()[0] if isinstance(r.json(), list) else r.json()
    ticket_id = data.get("id") or data.get("ID")

    # Reference ophalen
    ref = None
    if ticket_id:
        detail = requests.get(f"{HALO_API_BASE}/Tickets/{ticket_id}", headers=h)
        if detail.status_code == 200:
            td = detail.json()
            ref = td.get("ref") or td.get("ticketnumber")

        # Vragenlijst note toevoegen
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
            "ActionTypeID": HALO_ACTIONTYPE_PUBLIC,
            "IsPrivate": False,
            "VisibleToCustomer": True
        }
        if user_id:
            note_payload["UserID"] = user_id
        nr = requests.post(f"{HALO_API_BASE}/Actions", headers=h, json=note_payload)
        print("📝 Vragenlijst note:", nr.status_code, nr.text[:200])
        nr.raise_for_status()

    return {"id": ticket_id, "ref": ref or ticket_id}

# ------------------------------------------------------------------------------
# Notes
# ------------------------------------------------------------------------------
def add_note_to_ticket(ticket_id, text, sender="Webex", email=None):
    h = get_halo_headers()
    note_text = f"{sender} ({email}) schreef:\n{text}" if email else text
    payload = {
        "TicketID": int(ticket_id),
        "Details": note_text,
        "ActionTypeID": HALO_ACTIONTYPE_PUBLIC,
        "IsPrivate": False,
        "VisibleToCustomer": True
    }
    r = requests.post(f"{HALO_API_BASE}/Actions", headers=h, json=payload)
    print("💬 Note response:", r.status_code, r.text[:200])
    r.raise_for_status()

# ------------------------------------------------------------------------------
# Webex helpers
# ------------------------------------------------------------------------------
def send_message(room_id, text):
    r = requests.post("https://webexapis.com/v1/messages",
                      headers=WEBEX_HEADERS,
                      json={"roomId": room_id, "markdown": text})
    print("📤 Webex send:", r.status_code, r.text)

def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "📋 Nieuwe melding formulier",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.0",   # 👈 werkt altijd in Webex
                    "body": [
                        {"type": "TextBlock", "text": "📝 Vul de gegevens hieronder in om een melding te maken:", "weight": "Bolder", "size": "Medium", "wrap": True},
                        {"type": "TextBlock", "text": "Naam"}, {"type": "Input.Text", "id": "name", "placeholder": "Voor- en achternaam"},
                        {"type": "TextBlock", "text": "E-mailadres"}, {"type": "Input.Text", "id": "email", "placeholder": "naam@bedrijf.nl"},
                        {"type": "TextBlock", "text": "Probleemomschrijving"}, {"type": "Input.Text", "id": "omschrijving", "isMultiline": True, "placeholder": "Beschrijf het probleem"},
                        {"type": "TextBlock", "text": "Sinds wanneer?"}, {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Bijv: vandaag, gisteren..."},
                        {"type": "TextBlock", "text": "Wat werkt niet?"}, {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Bijv: inloggen, e-mail, etc."},
                        {"type": "TextBlock", "text": "Zelf geprobeerd?"}, {"type": "Input.Text", "id": "zelfgeprobeerd", "isMultiline": True, "placeholder": "Welke stappen al geprobeerd?"},
                        {"type": "TextBlock", "text": "Impact toelichting"}, {"type": "Input.Text", "id": "impacttoelichting", "isMultiline": True, "placeholder": "Wat is de impact?"},
                        {"type": "TextBlock", "text": "Impact (1-5)"}, {"type": "Input.Number", "id": "impact", "min": 1, "max": 5, "value": str(HALO_DEFAULT_IMPACT)},
                        {"type": "TextBlock", "text": "Urgentie (1-5)"}, {"type": "Input.Number", "id": "urgency", "min": 1, "max": 5, "value": str(HALO_DEFAULT_URGENCY)}
                    ],
                    "actions": [
                        {"type": "Action.Submit", "title": "✅ Versturen"}
                    ]
                }
            }
        ]
    }
    r = requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=card)
    print("📤 Adaptive card send:", r.status_code, r.text)
    r.raise_for_status()

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
        else:
            for t_id, rid in ticket_room_map.items():
                if rid == room_id:
                    add_note_to_ticket(t_id, text, sender, email=sender)

    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{action_id}", headers=WEBEX_HEADERS).json().get("inputs", {})
        
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
                                    impacttoelichting, impact_id, urgency_id)

        ticket_room_map[ticket["id"]] = room_id
        send_message(room_id, f"✅ Ticket aangemaakt: **{ticket['ref']}**\n\n**Onderwerp:** {summary}")

    return {"status": "ok"}

@app.route("/halo", methods=["POST"])
def halo_webhook():
    data = request.json
    print("📥 Halo webhook RAW:", json.dumps(data, indent=2))

    t_id = data.get("TicketID") or data.get("Request", {}).get("ID")
    if not t_id or int(t_id) not in ticket_room_map:
        return {"status": "ignored"}

    h = get_halo_headers()

    # Status ophalen en terugmelden
    t_detail = requests.get(f"{HALO_API_BASE}/Tickets/{t_id}", headers=h)
    if t_detail.status_code == 200:
        status = t_detail.json().get("StatusName") or t_detail.json().get("Status")
        if status:
            send_message(ticket_room_map[int(t_id)], f"🔄 **Status update voor ticket {t_id}:** {status}")

    # Notes (laatste action) ophalen
    r = requests.get(f"{HALO_API_BASE}/Tickets/{t_id}/Actions", headers=h)
    if r.status_code == 200 and r.json():
        actions = r.json()
        last = sorted(actions, key=lambda x: x.get("ID", 0), reverse=True)[0]
        note = last.get("Details") or last.get("Text") or last.get("Note")
        created_by = last.get("User", {}).get("Name", "Onbekend")
        is_private = last.get("IsPrivate", False)

        if note and not is_private:
            send_message(ticket_room_map[int(t_id)], f"💬 **Halo update door {created_by}:**\n\n{note}")

    return {"status": "ok"}

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Bot draait!"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
