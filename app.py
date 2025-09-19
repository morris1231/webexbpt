import os
import requests
import urllib.parse
from flask import Flask, request
from dotenv import load_dotenv

# 🔄 Load env vars
load_dotenv()
app = Flask(__name__)

# 🌐 Webex
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN", "").strip()
WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}

# 🌐 Halo Config
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE = os.getenv("HALO_API_BASE", "").strip()

# TicketType + IDs from .env
HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", "55"))
HALO_CUSTOMER_ID = int(os.getenv("HALO_CUSTOMER_ID", "986"))
HALO_TEAM_ID = int(os.getenv("HALO_TEAM_ID", "1"))
HALO_PRIORITY_ID = int(os.getenv("HALO_PRIORITY_ID", "1"))

# 🔑 Get Halo API Token
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    resp = requests.post(HALO_AUTH_URL, headers=headers, data=urllib.parse.urlencode(payload))
    print("🔑 Halo auth:", resp.status_code, resp.text[:200], flush=True)
    resp.raise_for_status()
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}", "Content-Type": "application/json"}

# 🎫 Create Halo Ticket
def create_halo_ticket(summary, details, impact_id, urgency_id):
    headers = get_halo_headers()

    payload = [
        {
            "Summary": summary,
            "Description": details,
            "TypeID": HALO_TICKET_TYPE_ID,
            "CustomerID": HALO_CUSTOMER_ID,
            "TeamID": HALO_TEAM_ID,
            "PriorityID": HALO_PRIORITY_ID,
            "ImpactID": int(impact_id),    # ✅ Correct integer IDs
            "UrgencyID": int(urgency_id),  # ✅ Correct integer IDs
            "Faults": []
        }
    ]

    print("📤 Halo Ticket Payload:", payload, flush=True)
    resp = requests.post(f"{HALO_API_BASE}/Tickets", headers=headers, json=payload)
    print("🎫 Halo ticket resp:", resp.status_code, resp.text[:500], flush=True)
    resp.raise_for_status()
    return resp.json()

# 💬 Webex: Send message
def send_message(room_id, text):
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS,
                  json={"roomId": room_id, "markdown": text})

# 📋 Webex: Adaptive Card with Impact & Urgency dropdowns
def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul je naam, omschrijving, impact en urgentie in om een melding te maken:",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {"type": "Input.Text", "id": "name", "placeholder": "Jouw naam"},
                        {
                            "type": "Input.Text", 
                            "id": "omschrijving", 
                            "isMultiline": True,
                            "placeholder": "Beschrijf hier je probleem"
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "id": "impact",
                            "style": "compact",
                            "value": "1",   # default ImpactID
                            "choices": [
                                {"title": "Single User Affected", "value": "3"},
                                {"title": "Multiple Users Affected", "value": "2"},
                                {"title": "Critical (System Down)", "value": "1"}
                            ]
                        },
                        {
                            "type": "Input.ChoiceSet",
                            "id": "urgency",
                            "style": "compact",
                            "value": "1",   # default UrgencyID
                            "choices": [
                                {"title": "Low", "value": "3"},
                                {"title": "Normal", "value": "2"},
                                {"title": "Immediate", "value": "1"}
                            ]
                        }
                    ],
                    "actions": [{"type": "Action.Submit", "title": "Versturen"}]
                }
            }
        ]
    }
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=card)

# 🔔 Webex: Webhook endpoint
@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    resource = data.get("resource")

    if resource == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS).json()
        text = msg.get("text", "").lower()
        room_id = msg.get("roomId")
        sender = msg.get("personEmail")

        if sender and sender.endswith("@webex.bot"):
            return {"status": "ignored"}

        if "nieuwe melding" in text:
            send_adaptive_card(room_id)

    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        form_resp = requests.get(
            f"https://webexapis.com/v1/attachment/actions/{action_id}",
            headers=WEBEX_HEADERS
        )
        inputs = form_resp.json().get("inputs", {})

        print("📥 Parsed inputs:", inputs, flush=True)
        naam = inputs.get("name", "Onbekend")
        omschrijving = inputs.get("omschrijving", "")

        impact_id = inputs.get("impact", "3")     # default to Single User Affected (ID 3)
        urgency_id = inputs.get("urgency", "3")  # default to Low (ID 3)

        summary = omschrijving if omschrijving else "Melding via Webex"
        details = f"Naam: {naam}\n\nOmschrijving:\n{omschrijving}"

        ticket = create_halo_ticket(summary, details, impact_id, urgency_id)
        ticket_id = ticket[0].get("ID", "onbekend")  # Halo returns array

        send_message(
            data["data"]["roomId"],
            f"✅ Ticket **#{ticket_id}** aangemaakt in Halo.\n\n**Onderwerp:** {summary}\n**ImpactID:** {impact_id}\n**UrgencyID:** {urgency_id}"
        )

    return {"status": "ok"}

# ❤️ Healthcheck
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Webex → Halo Bot draait"}

# ▶️ Run Flask
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
