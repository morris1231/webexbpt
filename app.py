import os
import requests
from flask import Flask, request
from dotenv import load_dotenv

# Load environment vars
load_dotenv()
app = Flask(__name__)

# 🌐 Environment variables
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID")
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET")
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL")        # bv: https://jouwdomein.halopsa.com/auth/token
HALO_API_BASE = os.getenv("HALO_API_BASE")        # bv: https://jouwdomein.halopsa.com/api

WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}

# 🔑 HALO ACCESS TOKEN ophalen
def get_halo_headers():
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    resp = requests.post(HALO_AUTH_URL, headers=headers, data=payload)
    print("🔑 Halo auth resp:", resp.status_code, resp.text, flush=True)
    resp.raise_for_status()
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# 🎫 TICKET AANMAKEN IN HALO
def create_halo_ticket(summary, details, priority="Medium"):
    headers = get_halo_headers()
    payload = {
        "Summary": summary,
        "Details": details,
        "TypeID": 1,   # pas eventueel aan naar jouw geldige TypeID in Halo configuratie
        "Priority": priority
    }
    resp = requests.post(f"{HALO_API_BASE}/Tickets", headers=headers, json=payload)
    print("🎫 Halo ticket resp:", resp.status_code, resp.text, flush=True)
    resp.raise_for_status()
    return resp.json()

# 💬 BERICHT STUREN NAAR WEBEX
def send_message(room_id, text):
    resp = requests.post("https://webexapis.com/v1/messages",
                         headers=WEBEX_HEADERS,
                         json={"roomId": room_id, "markdown": text})
    print("📤 Webex send message resp:", resp.status_code, resp.text, flush=True)

# 📝 ADAPTIVE CARD STUREN
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
                        {
                            "type": "Input.Text",
                            "id": "name",
                            "placeholder": "Jouw naam"
                        },
                        {
                            "type": "Input.Text",
                            "id": "omschrijving",
                            "isMultiline": True,
                            "placeholder": "Beschrijf hier je probleem"
                        }
                    ],
                    "actions": [
                        {"type": "Action.Submit", "title": "Versturen"}
                    ]
                }
            }
        ]
    }
    resp = requests.post("https://webexapis.com/v1/messages",
                         headers=WEBEX_HEADERS, json=card)
    print("📤 Webex send card resp:", resp.status_code, resp.text, flush=True)

# 🔔 WEBEX WEBHOOK HANDLER
@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    print("🚀 Webex event ontvangen:", data, flush=True)
    resource = data.get("resource")

    # ✅ 1. Nieuw bericht ontvangen
    if resource == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}",
                           headers=WEBEX_HEADERS).json()
        text = msg.get("text", "").lower()
        room_id = msg["roomId"]
        sender = msg.get("personEmail")

        # Negeer bot eigen berichten
        if sender and sender.endswith("@webex.bot"):
            print("🤖 Eigen bot bericht genegeerd")
            return {"status": "ignored"}

        print("📩 Bericht tekst:", text, flush=True)

        if "nieuwe melding" in text:
            send_adaptive_card(room_id)

    # ✅ 2. Formulier ingestuurd (Adaptive Card Submit)
    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        form_resp = requests.get(f"https://webexapis.com/v1/attachment/actions/{action_id}",
                                 headers=WEBEX_HEADERS)
        print("📥 Form response raw:", form_resp.status_code, form_resp.text, flush=True)

        form = form_resp.json()
        inputs = form.get("inputs", {})
        print("📥 Parsed inputs:", inputs, flush=True)

        naam = inputs.get("name", "Onbekend")
        omschrijving = inputs.get("omschrijving", "")

        summary = omschrijving if omschrijving else "Melding via Webex"
        details = f"Naam: {naam}\n\nOmschrijving:\n{omschrijving}"

        ticket = create_halo_ticket(summary, details, priority="Medium")
        ticket_id = ticket.get("ID", "onbekend")

        # ✅ terugmelden in Webex
        send_message(data["data"]["roomId"],
                     f"✅ Ticket **#{ticket_id}** aangemaakt in Halo.\n\n**Onderwerp:** {summary}")

    return {"status": "ok"}

# ❤️ HEALTH ENDPOINT
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Webex → Halo Bot draait"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
