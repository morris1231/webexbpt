import os
import requests
import urllib.parse
from flask import Flask, request
from dotenv import load_dotenv

# 🔄 Load environment
load_dotenv()
app = Flask(__name__)

# 🌐 Environment variables
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN", "").strip()
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip()
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip()
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL", "").strip()
HALO_API_BASE = os.getenv("HALO_API_BASE", "").strip()

WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}

# 🔑 Halo token ophalen
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

# 🎫 Ticket aanmaken in Halo (with required/default fields)
def create_halo_ticket(summary, details):
    headers = get_halo_headers()
    payload = {
        "Summary": summary,
        "Details": details,
        "TypeID": 55,         # TODO: Replace with your actual Webex ticket type id
        "CustomerID": 986,    # Bossers & Cnossen
        "TeamID": 1,          # TODO: Replace with your Support Engineering team ID
        "AssignedAgentID": -1,  # -1 = Unassigned
        "CategoryID": 0,        # 0 = Not set
        "ImpactID": 1,          # TODO: Replace with valid ID from /api/Impacts
        "UrgencyID": 1          # TODO: Replace with valid ID from /api/Urgencies
    }
    print("📤 Halo Ticket Payload:", payload, flush=True)

    resp = requests.post(f"{HALO_API_BASE}/Tickets", headers=headers, json=payload)
    print("🎫 Halo ticket resp:", resp.status_code, resp.text[:500], flush=True)
    resp.raise_for_status()
    return resp.json()

# 💬 Bericht naar Webex sturen
def send_message(room_id, text):
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS,
                  json={"roomId": room_id, "markdown": text})

# 📋 Adaptive Card sturen
def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul je naam en probleemomschrijving in om een melding te maken:",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {"type": "Input.Text", "id": "name", "placeholder": "Jouw naam"},
                        {"type": "Input.Text", "id": "omschrijving", "isMultiline": True,
                         "placeholder": "Beschrijf hier je probleem"}
                    ],
                    "actions": [{"type": "Action.Submit", "title": "Versturen"}]
                }
            }
        ]
    }
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=card)

# 🔔 Webex webhook
@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    resource = data.get("resource")

    # 📩 Chat message
    if resource == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS).json()
        text = msg.get("text", "").lower()
        room_id = msg.get("roomId")
        sender = msg.get("personEmail")

        # Ignore messages from the bot itself
        if sender and sender.endswith("@webex.bot"):
            return {"status": "ignored"}

        if "nieuwe melding" in text:
            send_adaptive_card(room_id)

    # 📥 Adaptive Card submit
    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        form_resp = requests.get(f"https://webexapis.com/v1/attachment/actions/{action_id}", headers=WEBEX_HEADERS)
        inputs = form_resp.json().get("inputs", {})
        print("📥 Parsed inputs:", inputs, flush=True)

        naam = inputs.get("name", "Onbekend")
        omschrijving = inputs.get("omschrijving", "")
        summary = omschrijving if omschrijving else "Melding via Webex"
        details = f"Naam: {naam}\n\nOmschrijving:\n{omschrijving}"

        ticket = create_halo_ticket(summary, details)
        ticket_id = ticket.get("ID", "onbekend")

        send_message(data["data"]["roomId"],
                     f"✅ Ticket **#{ticket_id}** aangemaakt in Halo.\n\n**Onderwerp:** {summary}")

    return {"status": "ok"}

# ❤️ Healthcheck endpoint
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Webex → Halo Bot draait"}

# ▶️ Start Flask server
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
