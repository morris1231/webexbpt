import os
import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN")
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID")
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET")
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL")
HALO_API_BASE = os.getenv("HALO_API_BASE")

WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}

# ✅ OAuth token ophalen
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

# ✅ Nieuw ticket maken in Halo
def create_halo_ticket(summary, details, priority="Medium"):
    headers = get_halo_headers()
    payload = {
        "Summary": summary,
        "Details": details,
        "TypeID": 1,
        "Priority": priority
    }
    resp = requests.post(f"{HALO_API_BASE}/Tickets", headers=headers, json=payload)
    print("🎫 Halo ticket resp:", resp.status_code, resp.text, flush=True)
    resp.raise_for_status()
    return resp.json()

# ✅ Bericht sturen naar Webex
def send_message(room_id, text):
    resp = requests.post("https://webexapis.com/v1/messages",
                         headers=WEBEX_HEADERS,
                         json={"roomId": room_id, "markdown": text})
    print("📤 Webex message resp:", resp.status_code, resp.text, flush=True)

# ✅ Adaptive Card in NL
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
                        {"type": "Action.Submit", "title": "Versturen"}
                    ]
                }
            }
        ]
    }
    resp = requests.post("https://webexapis.com/v1/messages",
                         headers=WEBEX_HEADERS, json=card)
    print("📤 Webex card resp:", resp.status_code, resp.text, flush=True)

# ✅ Webex webhook entrypoint
@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    print("🚀 Webex event:", data, flush=True)
    resource = data.get("resource")

    if resource == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS).json()
        text = msg.get("text", "").lower()
        room_id = msg["roomId"]
        sender = msg.get("personEmail")

        # Eigen bot berichten negeren
        if sender and sender.endswith("@webex.bot"):
            return {"status": "ignored"}

        if "nieuwe melding" in text:
            send_adaptive_card(room_id)

    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        form = requests.get(
            f"https://webexapis.com/v1/attachment/actions/{action_id}",
            headers=WEBEX_HEADERS).json()
        inputs = form["inputs"]

        naam = inputs.get("name", "Onbekend")
        omschrijving = inputs.get("omschrijving", "")

        # Ticket details
        summary = omschrijving if omschrijving else "Melding via Webex"
        details = f"Naam: {naam}\n\nOmschrijving:\n{omschrijving}"

        # ✅ Ticket maken in Halo
        ticket = create_halo_ticket(summary, details, priority="Medium")
        ticket_id = ticket.get("ID", "onbekend")

        # ✅ Antwoord sturen in Webex
        send_message(data["data"]["roomId"],
                     f"✅ Ticket **#{ticket_id}** is aangemaakt in Halo.\n\nOnderwerp: {summary}")

    return {"status": "ok"}

@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Webex → Halo Bot draait"}

# ✅ Start
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
