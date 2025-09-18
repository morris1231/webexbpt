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

# 🔑 Halo Access Token ophalen met DEBUG
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        # Gebruik exacte scope zoals je Postman teruggeeft
        "scope": "openid email profile offline_access roles all"
    }

    encoded = urllib.parse.urlencode(payload)
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }

    # 🔎 Debug: wat sturen we precies naar Halo?
    print("⚙️ HALO AUTH DEBUG", flush=True)
    print("  URL:", HALO_AUTH_URL, flush=True)
    print("  client_id:", HALO_CLIENT_ID, flush=True)
    print("  secret length:", len(HALO_CLIENT_SECRET), flush=True)
    print("  encoded payload:", encoded, flush=True)

    resp = requests.post(
        HALO_AUTH_URL,
        headers=headers,
        data=encoded.encode("utf-8"),  # stuur raw urlencoded string
        timeout=15
    )

    print("🔑 Halo auth raw resp:", resp.status_code, resp.text[:500], flush=True)
    resp.raise_for_status()

    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"Halo gaf geen access_token terug! Response={data}")

    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# 🎫 Ticket aanmaken in Halo
def create_halo_ticket(summary, details, priority="Medium"):
    headers = get_halo_headers()
    payload = {
        "Summary": summary,
        "Details": details,
        "TypeID": 1,  # pas aan naar geldige TypeID in jouw Halo config
        "Priority": priority
    }
    resp = requests.post(f"{HALO_API_BASE}/Tickets", headers=headers, json=payload)
    print("🎫 Halo ticket resp:", resp.status_code, resp.text[:500], flush=True)
    resp.raise_for_status()
    return resp.json()


# 💬 Bericht sturen naar Webex
def send_message(room_id, text):
    resp = requests.post(
        "https://webexapis.com/v1/messages",
        headers=WEBEX_HEADERS,
        json={"roomId": room_id, "markdown": text}
    )
    print("📤 Webex msg resp:", resp.status_code, resp.text, flush=True)


# 📋 AdaptiveCard sturen
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
    resp = requests.post(
        "https://webexapis.com/v1/messages",
        headers=WEBEX_HEADERS,
        json=card
    )
    print("📤 Webex card resp:", resp.status_code, resp.text, flush=True)


# 🔔 Webex webhook
@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    print("🚀 Webex event ontvangen:", data, flush=True)

    resource = data.get("resource")
    event_type = data.get("event")
    print(f"📡 Resource={resource}, Event={event_type}", flush=True)

    # 1️⃣ Tekstbericht
    if resource == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}",
                           headers=WEBEX_HEADERS).json()
        print("📩 Message details:", msg, flush=True)

        text = msg.get("text", "").lower()
        room_id = msg.get("roomId")
        sender = msg.get("personEmail")

        if sender and sender.endswith("@webex.bot"):
            return {"status": "ignored"}

        if "nieuwe melding" in text:
            send_adaptive_card(room_id)

    # 2️⃣ Adaptive Card ingestuurd
    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        print(f"📌 Adaptive submit ontvangen, ID={action_id}", flush=True)

        form_resp = requests.get(
            f"https://webexapis.com/v1/attachment/actions/{action_id}",
            headers=WEBEX_HEADERS
        )
        print("📥 Form raw:", form_resp.status_code, form_resp.text[:300], flush=True)

        if not form_resp.ok:
            return {"status": "error", "reason": "kon formulier niet ophalen"}, 400

        form = form_resp.json()
        inputs = form.get("inputs", {})
        print("📥 Parsed inputs:", inputs, flush=True)

        naam = inputs.get("name", "Onbekend")
        omschrijving = inputs.get("omschrijving", "")

        summary = omschrijving if omschrijving else "Melding via Webex"
        details = f"Naam: {naam}\n\nOmschrijving:\n{omschrijving}"

        ticket = create_halo_ticket(summary, details, priority="Medium")
        ticket_id = ticket.get("ID", "onbekend")

        send_message(
            data["data"]["roomId"],
            f"✅ Ticket **#{ticket_id}** aangemaakt in Halo.\n\n**Onderwerp:** {summary}"
        )

    return {"status": "ok"}


# ❤️ Health endpoint
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Webex → Halo Bot draait"}


# ▶️ Start Flask server
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
