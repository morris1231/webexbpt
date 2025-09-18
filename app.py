import os
import requests
import urllib.parse
from flask import Flask, request
from dotenv import load_dotenv

# 🔄 Load .env
load_dotenv()
app = Flask(__name__)

# 🌐 Environment variables
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN", "").strip().strip('"').strip("'")
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip().strip('"').strip("'")
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip().strip('"').strip("'")
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL", "").strip().strip('"').strip("'")
HALO_API_BASE = os.getenv("HALO_API_BASE", "").strip().strip('"').strip("'")

WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}

# 🔑 Halo Access Token ophalen
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }

    encoded = urllib.parse.urlencode(payload)
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}

    resp = requests.post(HALO_AUTH_URL, headers=headers, data=encoded.encode("utf-8"), timeout=15)
    print("🔑 Halo auth raw resp:", resp.status_code, resp.text[:200], flush=True)
    resp.raise_for_status()
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}", "Content-Type": "application/json"}


# ⚡ Slim beslissen welk TypeID / PriorityID
def decide_ticket_type_and_priority(omschrijving: str):
    text = omschrijving.lower()

    # Default
    type_id = 1        # Incident
    priority_id = None # Laat Halo default pakken

    if any(word in text for word in ["wachtwoord", "password", "reset", "inloggen", "unlock"]):
        type_id = 38   # Password reset
        priority_id = 3

    elif any(word in text for word in ["storing", "server down", "crash", "internet werkt niet", "niet bereikbaar"]):
        type_id = 1
        priority_id = 1  # urgent

    return type_id, priority_id


# 🎫 Ticket aanmaken in Halo
def create_halo_ticket(summary, details, omschrijving):
    headers = get_halo_headers()
    type_id, priority_id = decide_ticket_type_and_priority(omschrijving)

    payload = {
        "Summary": summary,
        "Details": details,
        "TypeID": type_id
    }
    if priority_id:
        payload["PriorityID"] = priority_id

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

    # Nieuw bericht
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

    # AdaptiveCard submit
    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        form_resp = requests.get(f"https://webexapis.com/v1/attachment/actions/{action_id}", headers=WEBEX_HEADERS)
        inputs = form_resp.json().get("inputs", {})

        naam = inputs.get("name", "Onbekend")
        omschrijving = inputs.get("omschrijving", "")

        summary = omschrijving if omschrijving else "Melding via Webex"
        details = f"Naam: {naam}\n\nOmschrijving:\n{omschrijving}"

        ticket = create_halo_ticket(summary, details, omschrijving)
        ticket_id = ticket.get("ID", "onbekend")

        send_message(data["data"]["roomId"],
                     f"✅ Ticket **#{ticket_id}** aangemaakt in Halo.\n\n**Onderwerp:** {summary}")

    return {"status": "ok"}


# ❤️ Health endpoint
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Webex → Halo Bot draait"}


# ▶️ Start Flask server
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
