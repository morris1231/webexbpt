import os
import requests
from flask import Flask, request
from dotenv import load_dotenv

# Load env vars
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


def get_halo_headers():
    """Get OAuth bearer token for Halo"""
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


def create_halo_ticket(summary, details, priority="Medium", user=None):
    headers = get_halo_headers()
    payload = {"Summary": summary, "Details": details,
               "TypeID": 1, "Priority": priority}
    if user:
        payload["User"] = user
    resp = requests.post(f"{HALO_API_BASE}/Tickets",
                         headers=headers, json=payload)
    print("🎫 Halo ticket resp:", resp.status_code, resp.text, flush=True)
    resp.raise_for_status()
    return resp.json()


def send_message(room_id, text):
    requests.post("https://webexapis.com/v1/messages",
                  headers=WEBEX_HEADERS, json={"roomId": room_id, "text": text})


def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "📋 Please fill in the ticket form below:",  # ✅ fallback text/markdown required
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {"type": "Input.Text", "id": "name",
                            "placeholder": "Your name"},
                        {"type": "Input.Text", "id": "summary",
                            "placeholder": "Problem summary"},
                        {"type": "Input.Text", "id": "details",
                            "isMultiline": True, "placeholder": "Details"},
                        {
                            "type": "Input.ChoiceSet",
                            "id": "priority",
                            "choices": [
                                {"title": "Low", "value": "Low"},
                                {"title": "Medium", "value": "Medium"},
                                {"title": "High", "value": "High"}
                            ]
                        }
                    ],
                    "actions": [
                        {"type": "Action.Submit", "title": "Submit"}
                    ]
                }
            }
        ]
    }
    resp = requests.post("https://webexapis.com/v1/messages",
                         headers=WEBEX_HEADERS, json=card)
    print("📤 Webex send card resp:", resp.status_code,
          resp.text, flush=True)  # ✅ log response


@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    print("🚀 Webex event:", data, flush=True)
    resource = data.get("resource")

    if resource == "messages":
        msg_id = data["data"]["id"]
        msg = requests.get(
            f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS).json()
        text = msg.get("text", "").lower()
        room_id = msg["roomId"]
        sender = msg.get("personEmail")

        # Ignore bot’s own messages
        if sender and sender.endswith("@webex.bot"):
            print("🤖 Ignored bot’s own message")
            return {"status": "ignored"}

        print("📩 Message text:", text, flush=True)

        if "new ticket" in text:
            send_adaptive_card(room_id)
            print("📝 Sent Adaptive Card to:", room_id, flush=True)

    elif resource == "attachmentActions":
        action_id = data["data"]["id"]
        form = requests.get(
            f"https://webexapis.com/v1/attachment/actions/{action_id}",
            headers=WEBEX_HEADERS).json()
        inputs = form["inputs"]
        print("📥 Adaptive Card inputs:", inputs, flush=True)

        ticket = create_halo_ticket(
            inputs.get("summary"),
            inputs.get("details"),
            inputs.get("priority", "Medium"),
            inputs.get("name")
        )
        send_message(
            data["data"]["roomId"],
            f"✅ Halo ticket created with ID: {ticket.get('ID', 'unknown')}"
        )

    return {"status": "ok"}


@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Webex → Halo Bot running"}


if __name__ == "__main__":  # ✅ fixed
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
