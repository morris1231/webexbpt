import os
import requests
from flask import Flask, request
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
app = Flask(__name__)

# Env variabelen
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID")
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET")
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL")
HALO_API_BASE = os.getenv("HALO_API_BASE")

WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}

# ✅ HALO AUTH HEADERS OPHALEN
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

# ✅ TICKET MAKEN
def create_halo_ticket(summary, details, priority="Medium"):
    headers = get_halo_headers()
    payload = {
        "Summary": summary,
        "Details": details,
        "TypeID": 1,       # let op: aanpassen naar een geldige ticket type id in Halo
        "Priority": priority
    }
    resp = requests.post(f"{HALO_API_BASE}/Tickets", headers=headers, json=payload)
    print("🎫 Halo ticket resp:", resp.status_code, resp.text, flush=True)
    resp.raise_for_status()
    return resp.json()

# ✅ WEBEX BERICHT STUREN
def send_message(room_id, text):
    resp = requests.post("https://webexapis.com/v1/messages",
                         headers=WEBEX_HEADERS,
                         json={"roomId": room_id, "text": text})
    print("📤 Webex send message resp:", resp.status_code, resp.text, flush=True)

# ✅ ADAPTIVE CARD STUREN (NL)
def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul onderstaande velden in om een melding te maken:",
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
                        {
                            "type": "Action.Submit",
                            "title": "Versturen"
                        }
                    ]
                }
            }
        ]
    }
    resp = requests.post("https://webexapis.com/v1/messages",
                         headers=WEBEX_HEADERS, json=card)
    print("📤 Webex send card resp:", resp.status_code, resp.text, flush=True)

# ✅ WEBEX WEBHOOK
@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    print("🚀 Webex event:", data, flush=True)
    resource = data.get("resource")

    if resource == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}",
                           headers=WEBEX_HEADERS).json()
        text = msg.get("text", "").lower()
        room_id = msg["roomId"]
        sender = msg.get("personEmail")

        # Negeer eigen bot berichten
        if sender and sender.endswith("@webex.bot"):
            print("🤖 Bericht van bot genegeerd")
            return {"status": "ignored"}

        print("📩 Binnenkomende tekst:", text, flush=True)

        if "nieuwe melding" in text:   # triggerwoord
            send_adaptive_card(room_id)

    elif resource == "attachmentActions":
        # Formulier verzonden
        action_id = data["data"]["id"]
        form = requests.get(f"https://webexapis.com/v1/attachment/actions/{action_id}",
                            headers=WEBEX_HEADERS).json()
        inputs = form["inputs"]
        print("📥 Formulier data:", inputs, flush=True)

        naam = inputs.get("name", "Onbekend")
        omschrijving = inputs.get("omschrijving", "")

        # Ticket details samenstellen
        summary = "Melding via Webex"
        details = f"Naam: {naam}\n\nProbleem:\n{omschrijving}"

        ticket = create_halo_ticket(
            summary,
            details,
            priority="Medium"   # vast → helpdesk kan later aanpassen
        )

        send_message(data["data"]["roomId"],
                     f"✅ Ticket aangemaakt in Halo met ID: {ticket.get('ID', 'onbekend')}")

    return {"status": "ok"}

# ✅ HEALTHCHECK ENDPOINT
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Webex → Halo Bot draait"}

if __name__ == "__main__":   # goede Python check
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
