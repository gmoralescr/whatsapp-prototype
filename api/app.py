import os, tempfile, json, requests
from datetime import date
from flask import Flask, request
import whisper
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(".env")           # ← copy .env.sample and fill in values

# ── Config ──────────────────────────────────────────────────────────
VERIFY_TOKEN   = os.getenv("VERIFY_TOKEN")
WA_TOKEN       = os.getenv("WA_TOKEN")
PHONE_NUMBER_ID= os.getenv("PHONE_NUMBER_ID")
LLAMA_PARSE_URL= os.getenv("LLAMA_PARSE_URL", "http://parse:8000/parse")
DB_URI         = os.getenv("DB_URI", "postgresql://user:pass@db:5432/wa")

whisper_model  = whisper.load_model("tiny")

engine = create_engine(DB_URI, pool_pre_ping=True, future=True)
app = Flask(__name__)

# ── Helpers ─────────────────────────────────────────────────────────
def send_whatsapp_text(to: str, body: str):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": body}
    }
    requests.post(url, headers=headers, json=payload, timeout=10)

def save_row(fields: dict, confirmed: bool):
    with engine.begin() as con:
        con.execute(text("""
            INSERT INTO fact_interaction (
                customer_id, visit_date, salesperson_id,
                desired_model, intent_window_days, test_drive_flag,
                test_drive_score, stock_flag, financing_flag,
                objection_codes, outcome, competitor_brand,
                confirmed
            ) VALUES (
                :customer_id, :visit_date, :salesperson_id,
                :desired_model, :intent_window_days, :test_drive_flag,
                :test_drive_score, :stock_flag, :financing_flag,
                :objection_codes, :outcome, :competitor_brand,
                :confirmed)
        """), dict(fields, visit_date=date.today(),
                   objection_codes=json.dumps(fields.get("objection_codes", [])),
                   confirmed=confirmed))

def confirmation_message(fields: dict) -> str:
    obj = ", ".join(fields.get("objection_codes", [])) or "None"
    return (
        "*Please confirm the interaction details:* \n"
        f"• Model: {fields.get('desired_model')}\n"
        f"• Test drive: {fields.get('test_drive_flag')}\n"
        f"• Intent window: {fields.get('intent_window_days')} days\n"
        f"• Objections: {obj}\n\n"
        "Reply 👍 to confirm or type corrections."
    )

# ── Core audio → data pipeline ──────────────────────────────────────
def process_audio(msg):
    sender = msg["from"]
    audio_id = msg["audio"]["id"]

    # 1 Download
    info = requests.get(
        f"https://graph.facebook.com/v19.0/{audio_id}",
        headers={"Authorization": f"Bearer {WA_TOKEN}"}, timeout=10
    ).json()
    audio_url = info["url"]
    audio_bytes = requests.get(audio_url,
                               headers={"Authorization": f"Bearer {WA_TOKEN}"}, timeout=30).content

    with tempfile.NamedTemporaryFile(suffix=".ogg") as f:
        f.write(audio_bytes); f.flush()
        # 2 Whisper
        transcript = whisper_model.transcribe(f.name)["text"]

    # 3 Llama parse
    fields = requests.post(LLAMA_PARSE_URL,
                           json={"text": transcript, "sender": sender},
                           timeout=15).json()
    fields["customer_id"] = sender  # simple unique key

    # 4 Preview & save provisional
    send_whatsapp_text(sender, confirmation_message(fields))
    save_row(fields, confirmed=False)

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Unauthorized", 403

    data = request.json
    change = data["entry"][0]["changes"][0]["value"]

    for msg in change.get("messages", []):
        if msg["type"] == "audio":
            process_audio(msg)
        elif msg["type"] == "text" and msg["text"]["body"].strip() in ("👍", "ok", "OK"):
            # Mark last unconfirmed row as confirmed
            sender = msg["from"]
            with engine.begin() as con:
                con.execute(text("""
                    UPDATE fact_interaction
                    SET confirmed = true
                    WHERE customer_id=:cid
                      AND confirmed=false
                    ORDER BY interaction_id DESC
                    LIMIT 1
                """), {"cid": sender})
            send_whatsapp_text(sender, "✅ Saved. Thank you!")
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000)

