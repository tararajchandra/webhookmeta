import os
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests

app = Flask(__name__)

# Use DATABASE_URL for Render PostgreSQL, or fallback to local SQLite for testing
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///cloud_webhook.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Replace these with environment variables in Render
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'mytoken')
WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN', '')
PHONE_NUMBER_ID = os.environ.get('PHONE_NUMBER_ID', '')

class InboxMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(255), unique=True, nullable=False)
    phone_number = db.Column(db.String(50), nullable=False)
    sender_name = db.Column(db.String(100))
    message_text = db.Column(db.Text)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_from_us = db.Column(db.Boolean, default=False) # True if we sent it from Web UI

class RepliedContact(db.Model):
    phone_number = db.Column(db.String(50), primary_key=True)
    sender_name = db.Column(db.String(100))
    last_replied_at = db.Column(db.DateTime, default=datetime.utcnow)

class FailedMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(255), unique=True, nullable=False)
    phone_number = db.Column(db.String(50))
    status = db.Column(db.String(50))
    error_title = db.Column(db.String(255))
    error_details = db.Column(db.Text)
    failed_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/contacts')
def get_contacts():
    contacts = RepliedContact.query.order_by(RepliedContact.last_replied_at.desc()).all()
    return jsonify([{
        "phone_number": c.phone_number,
        "sender_name": c.sender_name,
        "last_replied_at": c.last_replied_at.strftime("%Y-%m-%d %H:%M:%S")
    } for c in contacts])

@app.route('/api/messages/<phone_number>')
def get_messages(phone_number):
    messages = InboxMessage.query.filter_by(phone_number=phone_number).order_by(InboxMessage.received_at.asc()).all()
    return jsonify([{
        "id": m.id,
        "message_text": m.message_text,
        "received_at": m.received_at.strftime("%Y-%m-%d %H:%M:%S"),
        "is_from_us": m.is_from_us
    } for m in messages])

@app.route('/api/failed_messages')
def get_failed_messages():
    failed = FailedMessage.query.order_by(FailedMessage.failed_at.desc()).all()
    return jsonify([{
        "phone_number": f.phone_number,
        "status": f.status,
        "error_title": f.error_title,
        "error_details": f.error_details,
        "failed_at": f.failed_at.strftime("%Y-%m-%d %H:%M:%S")
    } for f in failed])

@app.route('/api/send_message', methods=['POST'])
def send_reply():
    data = request.json
    phone_number = data.get('phone_number')
    message_text = data.get('message_text')
    
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        return jsonify({"status": "error", "message": "WhatsApp API tokens not configured in environment."}), 400

    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message_text}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            # Log our reply in the database
            msg = InboxMessage(
                message_id=f"sent_{datetime.utcnow().timestamp()}",
                phone_number=phone_number,
                sender_name="Us",
                message_text=message_text,
                is_from_us=True
            )
            db.session.add(msg)
            db.session.commit()
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": response.text}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Forbidden", 403
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def receive_message():
    try:
        data = request.json
        if data.get("object"):
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        for msg in value["messages"]:
                            message_id = msg.get("id")
                            from_number = msg.get("from")
                            
                            sender_name = "Unknown"
                            if "contacts" in value:
                                for contact in value["contacts"]:
                                    if contact.get("wa_id") == from_number:
                                        sender_name = contact.get("profile", {}).get("name", "Unknown")
                            
                            msg_type = msg.get("type")
                            message_text = f"[{msg_type} message]"
                            
                            if msg_type == "text":
                                message_text = msg.get("text", {}).get("body", "")
                            elif msg_type == "button":
                                message_text = msg.get("button", {}).get("text", "")
                            elif msg_type == "interactive":
                                interactive = msg.get("interactive", {})
                                int_type = interactive.get("type")
                                if int_type == "button_reply":
                                    message_text = interactive.get("button_reply", {}).get("title", "")
                                elif int_type == "list_reply":
                                    message_text = interactive.get("list_reply", {}).get("title", "")

                            # Save to Inbox
                            existing = InboxMessage.query.filter_by(message_id=message_id).first()
                            if not existing:
                                new_msg = InboxMessage(
                                    message_id=message_id,
                                    phone_number=from_number,
                                    sender_name=sender_name,
                                    message_text=message_text,
                                    is_from_us=False
                                )
                                db.session.add(new_msg)
                                
                                # Update Replied Contacts
                                contact = RepliedContact.query.get(from_number)
                                if contact:
                                    contact.sender_name = sender_name
                                    contact.last_replied_at = datetime.utcnow()
                                else:
                                    new_contact = RepliedContact(
                                        phone_number=from_number,
                                        sender_name=sender_name,
                                        last_replied_at=datetime.utcnow()
                                    )
                                    db.session.add(new_contact)
                                
                                db.session.commit()
                    
                    if "statuses" in value:
                        for status in value["statuses"]:
                            msg_status = status.get("status")
                            recipient_id = status.get("recipient_id")
                            message_id = status.get("id")
                            
                            if msg_status in ["failed", "undelivered"]:
                                errors = status.get("errors", [])
                                error_title = "Unknown Error"
                                error_details = ""
                                if errors:
                                    error_title = errors[0].get("title", "Unknown Error")
                                    error_details = errors[0].get("error_data", {}).get("details", "")
                                
                                # Save failed message
                                existing = FailedMessage.query.filter_by(message_id=message_id).first()
                                if not existing:
                                    failed_msg = FailedMessage(
                                        message_id=message_id,
                                        phone_number=recipient_id,
                                        status=msg_status,
                                        error_title=error_title,
                                        error_details=error_details
                                    )
                                    db.session.add(failed_msg)
                                    db.session.commit()

            return jsonify({"status": "success"}), 200
        return "Not a WhatsApp API event", 404
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
