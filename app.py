import os
import requests
import urllib.parse
import json
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

HALO_TICKET_TYPE_ID = int(os.getenv("HALO_TICKET_TYPE_ID", "55"))
HALO_CUSTOMER_ID = int(os.getenv("HALO_CUSTOMER_ID", "986"))
HALO_TEAM_ID = int(os.getenv("HALO_TEAM_ID", "1"))

HALO_DEFAULT_IMPACT = int(os.getenv("HALO_IMPACT", "3"))
HALO_DEFAULT_URGENCY = int(os.getenv("HALO_URGENCY", "3"))


# 🔑 Halo API Token
def get_halo_headers():
    payload = {
        "grant_type": "client_credentials",
        "client_id": HALO_CLIENT_ID,
        "client_secret": HALO_CLIENT_SECRET,
        "scope": "all"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    resp = requests.post(HALO_AUTH_URL, headers=headers, data=urllib.parse.urlencode(payload))
    resp.raise_for_status()
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}", "Content-Type": "application/json"}


# 🔎 Zoek UserID in Halo adhv email
def get_halo_user_id_by_email(email):
    if not email:
        return None
    headers = get_halo_headers()
    url = f"{HALO_API_BASE}/Users?$filter=Email eq '{email}'"
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0].get("ID")
    return None


# 🎫 Create Halo Ticket
def create_halo_ticket(summary, details, impact_id, urgency_id, room_id=None, naam="Onbekend", email=None):
    headers = get_halo_headers()

    user_id = get_halo_user_id_by_email(email)

    ticket = {
        "Summary": summary,
        "Description": f"Ingediend door: {naam} ({email})\n\n{details}",
        "TypeID": HALO_TICKET_TYPE_ID,
        "CustomerID": HALO_CUSTOMER_ID,
        "TeamID": HALO_TEAM_ID,
        "Impact": int(impact_id),
        "Urgency": int(urgency_id),
        "Faults": []
    }
    if user_id:
        ticket["UserID"] = user_id

    payload = [ticket]

    resp = requests.post(f"{HALO_API_BASE}/Tickets", headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, list):
        new_ticket = data[0]
    else:
        new_ticket = data
    ticket_id = new_ticket.get("id") or new_ticket.get("ID")

    # 🔄 Extra API call to fetch proper reference number (INC:0000329)
    ref = None
    if ticket_id:
        detail_resp = requests.get(f"{HALO_API_BASE}/Tickets/{ticket_id}", headers=headers)
        if detail_resp.status_code == 200:
            tdata = detail_resp.json()
            ref = tdata.get("ref") or tdata.get("ticketnumber") or ticket_id

    return {"id": ticket_id, "ref": ref or ticket_id}


# 💬 Webex: Send message
def send_message(room_id, text):
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS,
                  json={"roomId": room_id, "markdown": text})


# 📋 Webex Adaptive Card met extra vragenlijst
def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul de onderstaande velden in om een melding te maken (**niet alles is verplicht**):",
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
                         "placeholder": "Beschrijf hier je probleem"},
                        {"type": "Input.Text", "id": "sindswanneer", "placeholder": "Sinds wanneer speelt dit probleem?"},
                        {"type": "Input.Text", "id": "watwerktniet", "placeholder": "Wat werkt er niet (specifiek)?"},
                        {"type": "Input.Text", "id": "zelfgeprobeerd", "isMultiline": True,
                         "placeholder": "Wat heb je zelf al geprobeerd?"},
                        {"type": "Input.Text", "id": "impacttoelichting", "isMultiline": True,
                         "placeholder": "Hoe ernstig is dit voor jou/het team?"},
                        # Impact dropdown
                        {"type": "Input.ChoiceSet", "id": "impact", "style": "compact",
                         "value": str(HALO_DEFAULT_IMPACT),
                         "choices": [
                             {"title": "Company Wide", "value": "1"},
                             {"title": "Multiple Users Affected", "value": "2"},
                             {"title": "Single User Affected", "value": "3"}
                         ]},
                        # Urgency dropdown
                        {"type": "Input.ChoiceSet", "id": "urgency", "style": "compact",
                         "value": str(HALO_DEFAULT_URGENCY),
                         "choices": [
                             {"title": "High", "value": "1"},
                             {"title": "Medium", "value": "2"},
                             {"title": "Low", "value": "3"}
                         ]}
                    ],
                    "actions": [{"type": "Action.Submit", "title": "Versturen"}]
                }
            }
        ]
    }
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=card)


# 🔔 Webex Endpoint
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

        naam = inputs.get("name", "Onbekend")
        omschrijving = inputs.get("omschrijving", "")
        sindswanneer = inputs.get("sindswanneer", "")
        watwerktniet = inputs.get("watwerktniet", "")
        zelfgeprobeerd = inputs.get("zelfgeprobeerd", "")
        impact_toelichting = inputs.get("impacttoelichting", "")

        impact_id = inputs.get("impact", str(HALO_DEFAULT_IMPACT))
        urgency_id = inputs.get("urgency", str(HALO_DEFAULT_URGENCY))
        room_id = data["data"]["roomId"]

        summary = omschrijving if omschrijving else "Melding via Webex"

        # Description samenstellen, velden alleen toevoegen als ze ingevuld zijn
        details = f"Naam: {naam}\n\n"
        if omschrijving: details += f"Omschrijving: {omschrijving}\n\n"
        if sindswanneer: details += f"Sinds wanneer: {sindswanneer}\n"
        if watwerktniet: details += f"Wat werkt niet: {watwerktniet}\n"
        if zelfgeprobeerd: details += f"Zelf geprobeerd: {zelfgeprobeerd}\n"
        if impact_toelichting: details += f"Impact toelichting: {impact_toelichting}\n"

        sender_email = request.json["data"].get("personEmail", None)

        ticket = create_halo_ticket(
            summary, details, impact_id, urgency_id,
            room_id=room_id, naam=naam, email=sender_email
        )

        ref = ticket["ref"]

        send_message(
            room_id,
            f"✅ Ticket **{ref}** aangemaakt in Halo.\n\n"
            f"**Onderwerp:** {summary}\n**Impact:** {impact_id}\n**Urgentie:** {urgency_id}"
        )
    return {"status": "ok"}


# ❤️ Healthcheck
@app.route("/", methods=["GET"])
def health():
    return {"status": "ok", "message": "Webex ⇌ Halo Bot draait"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
