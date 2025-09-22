import os, requests, urllib.parse, json
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# 🌐 Webex
WEBEX_TOKEN = os.getenv("WEBEX_BOT_TOKEN", "").strip()
WEBEX_HEADERS = {"Authorization": f"Bearer {WEBEX_TOKEN}", "Content-Type": "application/json"}

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

# 🔔 Public note Action Type ID (uit Halo Admin > Action Types)
HALO_ACTIONTYPE_PUBLIC = int(os.getenv("HALO_ACTIONTYPE_PUBLIC", "1"))

# TicketID ↔ RoomID mapping
ticket_room_map = {}


# 🔑 Halo API login
def get_halo_headers():
    payload = {"grant_type":"client_credentials","client_id":HALO_CLIENT_ID,
               "client_secret":HALO_CLIENT_SECRET,"scope":"all"}
    r = requests.post(HALO_AUTH_URL,
        headers={"Content-Type":"application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(payload))
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type":"application/json"}


# 🔎 Zoek UserID in Halo adhv email
def get_halo_user_id_by_email(email):
    if not email: return None
    h = get_halo_headers()
    r = requests.get(f"{HALO_API_BASE}/Users?$filter=Email eq '{email}'", headers=h)
    if r.status_code==200 and isinstance(r.json(), list) and len(r.json())>0:
        return r.json()[0].get("ID")
    return None


# 🎫 Ticket aanmaken
def create_halo_ticket(summary, naam, email,
                       omschrijving="", sindswanneer="", watwerktniet="",
                       zelfgeprobeerd="", impacttoelichting="",
                       impact_id=3, urgency_id=3):

    h = get_halo_headers()
    user_id = get_halo_user_id_by_email(email)

    # ✍️ Beschrijving met vragenlijst
    description = f"Ingediend door: {naam} ({email})\n\n"
    if omschrijving: description += f"Omschrijving: {omschrijving}\n\n"
    if sindswanneer: description += f"Sinds wanneer: {sindswanneer}\n"
    if watwerktniet: description += f"Wat werkt niet: {watwerktniet}\n"
    if zelfgeprobeerd: description += f"Zelf geprobeerd: {zelfgeprobeerd}\n"
    if impacttoelichting: description += f"Impact toelichting: {impacttoelichting}\n"

    ticket = {
        "Summary": summary,
        "Description": description,
        "TypeID": HALO_TICKET_TYPE_ID,
        "CustomerID": HALO_CUSTOMER_ID,
        "TeamID": HALO_TEAM_ID,
        "Impact": int(impact_id),
        "Urgency": int(urgency_id),
        "Faults": []
    }

    if user_id:
        ticket["CustomerUserID"] = user_id  # ✅ koppeling gebruiker

    r = requests.post(f"{HALO_API_BASE}/Tickets", headers=h, json=[ticket])
    r.raise_for_status()
    data = r.json()[0] if isinstance(r.json(), list) else r.json()
    ticket_id = data.get("id") or data.get("ID")

    # Ref ophalen (INC:0000xxx)
    ref = None
    if ticket_id:
        detail = requests.get(f"{HALO_API_BASE}/Tickets/{ticket_id}", headers=h)
        if detail.status_code==200:
            td = detail.json()
            ref = td.get("ref") or td.get("ticketnumber")

    return {"id": ticket_id, "ref": ref or ticket_id}


# 💬 Note toevoegen (Webex → Halo)
def add_note_to_ticket(ticket_id, text, sender="Webex user"):
    h = get_halo_headers()
    payload = [{
        "TicketID": ticket_id,
        "Note": f"{sender} schreef:\n{text}",
        "IsPrivate": False,
        "ActionTypeID": HALO_ACTIONTYPE_PUBLIC
    }]
    r = requests.post(f"{HALO_API_BASE}/Actions", headers=h, json=payload)
    print("💬 Note to Halo:", r.status_code, r.text[:200])


# 📤 Stuur bericht naar Webex
def send_message(room_id, text):
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS,
        json={"roomId": room_id, "markdown": text})


# 📋 Adaptive Card
def send_adaptive_card(room_id):
    card = {
        "roomId": room_id,
        "markdown": "✍ Vul onderstaande info in (email verplicht, rest optioneel):",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema":"http://adaptivecards.io/schemas/adaptive-card.json",
                "type":"AdaptiveCard","version":"1.2","body":[
                    {"type":"Input.Text","id":"name","placeholder":"Naam"},
                    {"type":"Input.Text","id":"email","placeholder":"Jouw emailadres"},
                    {"type":"Input.Text","id":"omschrijving","isMultiline":True,"placeholder":"Probleemomschrijving"},
                    {"type":"Input.Text","id":"sindswanneer","placeholder":"Sinds wanneer?"},
                    {"type":"Input.Text","id":"watwerktniet","placeholder":"Wat werkt niet?"},
                    {"type":"Input.Text","id":"zelfgeprobeerd","isMultiline":True,"placeholder":"Wat probeerde je al?"},
                    {"type":"Input.Text","id":"impacttoelichting","isMultiline":True,"placeholder":"Hoe ernstig is dit?"},
                    {"type":"Input.ChoiceSet","id":"impact","style":"compact","value":str(HALO_DEFAULT_IMPACT),
                     "choices":[{"title":"Company Wide","value":"1"},
                                {"title":"Multiple Users","value":"2"},
                                {"title":"Single User","value":"3"}]},
                    {"type":"Input.ChoiceSet","id":"urgency","style":"compact","value":str(HALO_DEFAULT_URGENCY),
                     "choices":[{"title":"High","value":"1"},
                                {"title":"Medium","value":"2"},
                                {"title":"Low","value":"3"}]}
                ],
                "actions":[{"type":"Action.Submit","title":"Versturen"}]
            }
        }]}
    requests.post("https://webexapis.com/v1/messages", headers=WEBEX_HEADERS, json=card)


# 🔔 Webex webhook
@app.route("/webex", methods=["POST"])
def webex_webhook():
    data = request.json
    resource = data.get("resource")

    # 1. Normaal tekstbericht uit Webex room
    if resource=="messages":
        msg_id = data["data"]["id"]
        msg = requests.get(f"https://webexapis.com/v1/messages/{msg_id}", headers=WEBEX_HEADERS).json()
        text = msg.get("text","").strip()
        room_id = msg.get("roomId")
        sender = msg.get("personEmail")
        if sender and sender.endswith("@webex.bot"):
            return {"status":"ignored"}

        if "nieuwe melding" in text.lower():
            send_adaptive_card(room_id)
        else:
            for t_id, rid in ticket_room_map.items():
                if rid==room_id:
                    add_note_to_ticket(t_id, text, sender)

    # 2. Adaptive Card ingevuld
    elif resource=="attachmentActions":
        action_id = data["data"]["id"]
        inputs = requests.get(f"https://webexapis.com/v1/attachment/actions/{action_id}",
                              headers=WEBEX_HEADERS).json().get("inputs", {})

        naam = inputs.get("name","Onbekend")
        email = inputs.get("email","")
        omschrijving = inputs.get("omschrijving","")
        sindswanneer = inputs.get("sindswanneer","")
        watwerktniet = inputs.get("watwerktniet","")
        zelfgeprobeerd = inputs.get("zelfgeprobeerd","")
        impact_toelichting = inputs.get("impacttoelichting","")
        impact_id = inputs.get("impact", str(HALO_DEFAULT_IMPACT))
        urgency_id = inputs.get("urgency", str(HALO_DEFAULT_URGENCY))
        room_id = data["data"]["roomId"]

        summary = omschrijving or "Melding via Webex"

        ticket = create_halo_ticket(summary, naam, email,
                                    omschrijving, sindswanneer,
                                    watwerktniet, zelfgeprobeerd,
                                    impact_toelichting,
                                    impact_id, urgency_id)

        ticket_room_map[ticket["id"]] = room_id
        ref = ticket["ref"]

        send_message(room_id,
            f"✅ Ticket **{ref}** aangemaakt in Halo.\n\n"
            f"**Onderwerp:** {summary}\n**Impact:** {impact_id}\n**Urgentie:** {urgency_id}")
    return {"status":"ok"}


# 📡 Halo webhook (Halo → Webex)
@app.route("/halo", methods=["POST"])
def halo_webhook():
    data = request.json
    print("Halo webhook:", json.dumps(data, indent=2))
    t_id = data.get("TicketID")
    event = data.get("Event", {})

    note = event.get("Text")
    created_by = event.get("User", {}).get("Name", "Onbekend")
    is_private = event.get("IsPrivate", False)

    if t_id and note and not is_private and t_id in ticket_room_map:
        send_message(ticket_room_map[t_id],
            f"💬 **Update vanuit Halo (#{t_id}) door {created_by}:**\n\n{note}")
    return {"status": "ok"}


@app.route("/", methods=["GET"])
def health():
    return {"status":"ok","message":"Webex ⇌ Halo bot draait"}

if __name__=="__main__":
    port=int(os.getenv("PORT",5000))
    app.run(host="0.0.0.0", port=port, debug=False)
