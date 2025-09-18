import os
import requests
from flask import Flask, request
from dotenv import load_dotenv

# Load environment variables (.env of Render)
load_dotenv()
app = Flask(__name__)

# Lees environment vars en strip whitespace/aanhalingstekens
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN", "").strip().strip('"').strip("'")
HALO_CLIENT_ID = os.getenv("HALO_CLIENT_ID", "").strip().strip('"').strip("'")
HALO_CLIENT_SECRET = os.getenv("HALO_CLIENT_SECRET", "").strip().strip('"').strip("'")
HALO_AUTH_URL = os.getenv("HALO_AUTH_URL", "").strip().strip('"').strip("'")
HALO_API_BASE = os.getenv("HALO_API_BASE", "").strip().strip('"').strip("'")

WEBEX_HEADERS = {
    "Authorization": f"Bearer {WEBEX_TOKEN}",
    "Content-Type": "application/json"
}

# 🔑 Ophalen Halo token
def get_halo_headers():
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }

    # Debug info loggen
    print("⚙️ [Halo Auth Debug]", flush=True)
    print("  URL:", HALO_AUTH_URL, flush=True)
    print("  ClientID:", HALO_CLIENT_ID, flush=True)
    print("  Secret lengte:", len(HALO_CLIENT_SECRET), flush=True)
    print("  Payload:", payload, flush=True)

    try:
        resp = requests.post(HALO_AUTH_URL, headers=headers, data=payload, timeout=15)
    except Exception as e:
        print("❌ Request naar Halo fout:", str(e), flush=True)
        raise

    print("🔑 Halo auth raw response:", resp.status_code, resp.text[:500], flush=True)
    resp.raise_for_status()

    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("Halo gaf geen access_token terug.")
    return {"Authorization": f"Bearer {token}",
            "Content-Type": "application/json"}

# 🎫 Ticket in Halo aanmaken
def create_halo_ticket(summary, details, priority="Medium"):
    headers = get_halo_headers()
    payload = {
        "Summary": summary,
        "Details": details,
        "TypeID": 1,       # Pas dit aan naar jouw geldige TypeID in Halo
        "Priority": priority
    }
    resp = requests.post(f"{HALO_API_BASE}/Tickets", headers=headers, json=payload)
    print("🎫 Halo ticket resp:", resp.status_code, resp.text[:500], flush=True)
    resp.raise_for_status()
    return resp.json()

# 💬 Bericht terugsturen naar Webex
def send_message(room_id, text):
    resp = requests.post("https://webexapis.com/v1/messages",
                         headers=WEBEX_HEADERS,
                         json={"roomId": room_id, "markdown": text})
    print("📤 Webex message resp:", resp.status_code, resp.text, flush=True)

# 📋 Adaptive Card versturen (NL)
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
    resp = requests.post("https://webexapis.com/v1/messages",
                         headers=WEBEX_HEADERS, json=card)
    print("📤 Webex send card resp:", resp.status_code, resp.text, flush=True)

# 🔔 Webex webhook endpoint
@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    print("🚀 Webex event ontvangen:", data, flush=True)
    resource = data.get("resource")

    # 1️⃣ Tekstbericht opvangen
    if resource == "messages":
        msg_id = data["data"]["id"]
        msg
