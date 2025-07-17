import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import sqlite3
import os
from flask import Flask, request, render_template, jsonify
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEB3_API_BASE = "https://api.web3.storage"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- Database Setup ---
conn = sqlite3.connect("data.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, token TEXT, points INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS files (user_id INTEGER, cid TEXT, name TEXT, size INTEGER)''')
conn.commit()

# --- Bot Buttons ---
def main_buttons(user_id):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("📤 Upload File", callback_data="upload"),
        InlineKeyboardButton("📁 My Files", callback_data="files"),
        InlineKeyboardButton("🔐 Add Web3 Token", callback_data="token"),
        InlineKeyboardButton("📊 Dashboard", web_app=WebAppInfo(url=f"{WEBHOOK_URL}/dashboard/{user_id}"))
    )
    return markup

# --- Bot Commands ---
@bot.message_handler(commands=['start'])
def welcome(message):
    user_id = message.from_user.id
    username = message.from_user.first_name or "there"
    c.execute("INSERT OR IGNORE INTO users (id, points) VALUES (?, 0)", (user_id,))
    conn.commit()
    welcome_text = (
        f"👋 Welcome, {username}, to *Tonova* — a next-gen cloud powered by Web3.Storage!\n\n"
        "🚀 Here's what you can do:\n"
        "📤 Upload files securely to IPFS\n"
        "📎 Share links and manage your uploads\n"
        "📥 Download anytime — all decentralized\n\n"
        "🔐 Your data is end-to-end encrypted, powered by your personal API token.\n"
        "👇 Use the buttons below to get started!"
    )

    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=main_buttons(user_id),
        parse_mode="Markdown"
    )

# --- Handle Buttons ---
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    user_id = call.from_user.id

    if call.data == "upload":
        bot.send_message(user_id, "Send me a file to upload (max 100MB).")
    elif call.data == "files":
        c.execute("SELECT cid, name FROM files WHERE user_id = ?", (user_id,))
        rows = c.fetchall()
        if not rows:
            bot.send_message(user_id, "No files found.")
        else:
            msg = "📁 *Your Files:*\n"
            for cid, name in rows:
                msg += f"\n🔗 [{name}](https://{cid}.ipfs.w3s.link)"
            bot.send_message(user_id, msg, parse_mode='Markdown')
    elif call.data == "token":
        bot.send_message(user_id, "Please paste your Web3.Storage API token. Create one here: https://web3.storage/account")

@bot.message_handler(content_types=['document'])
def upload_file(message):
    user_id = message.from_user.id
    c.execute("SELECT token FROM users WHERE id = ?", (user_id,))
    result = c.fetchone()

    if not result or not result[0]:
        bot.reply_to(message, "⚠️ You need to set your Web3.Storage API token first.")
        return

    token = result[0]
    file_info = bot.get_file(message.document.file_id)
    file_bytes = bot.download_file(file_info.file_path)

    quota = get_storage_usage(token)
    if quota >= 10 * 1024 * 1024 * 1024:
        bot.reply_to(message, "🚫 Storage quota exceeded.")
        return

    files = {"file": (message.document.file_name, file_bytes)}
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(f"{WEB3_API_BASE}/upload", headers=headers, files=files)

    if res.status_code == 200:
        cid = res.json()["cid"]
        c.execute("INSERT INTO files (user_id, cid, name, size) VALUES (?, ?, ?, ?)",
                  (user_id, cid, message.document.file_name, message.document.file_size))
        c.execute("UPDATE users SET points = points + 10 WHERE id = ?", (user_id,))
        conn.commit()
        bot.send_message(user_id, f"✅ File uploaded! [Link](https://{cid}.ipfs.w3s.link)", parse_mode='Markdown')
    else:
        bot.send_message(user_id, "❌ Upload failed.")

@bot.message_handler(func=lambda m: True)
def handle_token(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if "eyJ" in text and len(text) > 20:
        c.execute("UPDATE users SET token = ? WHERE id = ?", (text, user_id))
        conn.commit()
        bot.reply_to(message, "✅ API token saved.")
    else:
        bot.reply_to(message, "❌ Invalid token. Please enter a valid Web3.Storage token.")

# --- Helper ---
def get_storage_usage(token):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{WEB3_API_BASE}/user/uploads", headers=headers)
    if res.status_code != 200:
        return 0
    data = res.json()
    return sum(f.get("dagSize", 0) for f in data)

# --- Dashboard ---
@app.route("/dashboard/<int:user_id>")
def dashboard(user_id):
    c.execute("SELECT token, points FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    c.execute("SELECT name, cid, size FROM files WHERE user_id = ?", (user_id,))
    files = c.fetchall()

    quota = get_storage_usage(user[0]) if user and user[0] else 0
    used_mb = round(quota / (1024 * 1024), 2)

    return render_template("dashboard.html", files=[
        {"name": name, "cid": cid, "size": size}
        for name, cid, size in files
    ], points=user[1], used_mb=used_mb)

# --- Webhook ---
@app.route("/" + BOT_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "", 200

@app.route("/")
def index():
    return "🤖 Bot running."

# --- Start ---
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)

    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(debug=True,host='0.0.0.0', port=5000)
