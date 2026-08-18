# WhatsApp Web CRM for Render

This is a standalone Cloud Webhook and CRM for your WhatsApp Business API. 
It replaces the desktop `webhook_server.py` and allows you to view and reply to customers from a webpage 24/7.

## Local Testing
1. Open a terminal in this folder.
2. Run `pip install -r requirements.txt`
3. Run `python app.py`
4. Open `http://localhost:5000` in your browser. (It will use a local SQLite database for testing).

## How to Deploy to Render
1. Upload this entire `webhook_webapp` folder to a new **GitHub repository**.
2. Go to [Render.com](https://render.com) and sign in.
3. Click **New +** -> **PostgreSQL**.
   - Name it `whatsapp-crm-db`.
   - Click Create.
   - Once created, copy the **Internal Database URL**.
4. Click **New +** -> **Web Service**.
   - Connect your GitHub repository.
   - Set Build Command: `pip install -r requirements.txt`
   - Set Start Command: `gunicorn app:app`
   - Scroll down to **Environment Variables** and add:
     - `DATABASE_URL`: (Paste the Internal Database URL you copied earlier)
     - `VERIFY_TOKEN`: (e.g., `mytoken`)
     - `WHATSAPP_TOKEN`: (Your permanent or temporary Facebook Graph API Access Token)
     - `PHONE_NUMBER_ID`: (Your WhatsApp Phone Number ID)
5. Click **Create Web Service**.
6. Render will give you a public URL like `https://your-app.onrender.com`.

## Update WhatsApp Webhook Configuration
1. Go to your Meta Developer Dashboard -> WhatsApp -> Configuration.
2. Click **Edit** next to Webhook.
3. Paste your Render URL: `https://your-app.onrender.com/webhook`
4. Enter the `VERIFY_TOKEN` you used.
5. Click Verify and Save.

You can now open `https://your-app.onrender.com` anytime to chat with customers!
