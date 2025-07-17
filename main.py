import os
import sqlite3
import requests
import json
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIG ---
API_URL = "https://api.web3.storage"
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = "https://<your-render-subdomain>.onrender.com/"  # TODO: Replace this

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# --- DB SETUP ---
conn = sqlite3.connect("data.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, token TEXT, points INTEGER DEFAULT 0)''')
c.execute('''CREATE TABLE IF NOT EXISTS files (user_id INTEGER, name TEXT, cid TEXT, size INTEGER)''')
conn.commit()

# --- HELPERS ---
def get_user(user_id):
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return c.fetchone()

def add_user(user_id):
    c.execute("INSERT OR IGNORE INTO users (id, points) VALUES (?, 0)", (user_id,))
    conn.commit()

def set_token(user_id, token):
    c.execute("UPDATE users SET token = ? WHERE id = ?", (token, user_id))
    conn.commit()

def add_points(user_id, pts):
    c.execute("UPDATE users SET points = points + ? WHERE id = ?", (pts, user_id))
    conn.commit()

def add_file(user_id, name, cid, size):
    c.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (user_id, name, cid, size))
    conn.commit()

def get_user_files(user_id):
    c.execute("SELECT name, cid, size FROM files WHERE user_id = ?", (user_id,))
    return c.fetchall()

def get_storage_used(token):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{API_URL}/user/uploads", headers=headers)
    total = sum(f['dagSize'] for f in resp.json())
    return total

# --- COMMANDS ---
@bot.message_handler(commands=["start"])
def start(msg):
    user_id = msg.from_user.id
    add_user(user_id)
    bot.send_message(user_id, "👋 Welcome! Please set your Web3.Storage token using /token <your_token>\nDon't have one? Sign up at https://web3.storage and get your token.")

@bot.message_handler(commands=["token"])
def set_user_token(msg):
    token = msg.text.split(" ", 1)[-1].strip()
    if len(token) < 10:
        bot.send_message(msg.chat.id, "❌ Invalid token.")
        return
    set_token(msg.from_user.id, token)
    bot.send_message(msg.chat.id, "✅ Token saved! Now send a file to upload.")

@bot.message_handler(content_types=['document'])
def upload_file(msg):
    user = get_user(msg.from_user.id)
    if not user or not user[1]:
        bot.send_message(msg.chat.id, "⚠️ Please set your Web3 token first using /token.")
        return

    token = user[1]
    used = get_storage_used(token)
    if used >= 10 * 1024**3:
        bot.send_message(msg.chat.id, "🚫 You have reached your 10GB storage limit.")
        return

    file_info = bot.get_file(msg.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    filename = msg.document.file_name

    files = {"file": (filename, downloaded_file)}
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(f"{API_URL}/upload", files=files, headers=headers)

    if res.status_code == 200:
        cid = res.json()["cid"]
        add_file(msg.from_user.id, filename, cid, msg.document.file_size)
        add_points(msg.from_user.id, 10)
        bot.send_message(msg.chat.id, f"✅ File uploaded: {cid}\nEarned 10 points.")
    else:
        bot.send_message(msg.chat.id, "❌ Upload failed.")

@bot.message_handler(commands=["files"])
def show_files(msg):
    files = get_user_files(msg.from_user.id)
    if not files:
        bot.send_message(msg.chat.id, "📁 No files uploaded yet.")
        return
    text = "📂 Your Files:\n\n"
    for name, cid, size in files:
        text += f"🗂️ {name} — {round(size/1024, 2)} KB\n🔗 https://{cid}.ipfs.w3s.link\n\n"
    bot.send_message(msg.chat.id, text)

@bot.message_handler(commands=["points"])
def show_points(msg):
    user = get_user(msg.from_user.id)
    bot.send_message(msg.chat.id, f"🏆 Your Points: {user[2]}")

@bot.message_handler(commands=["dashboard"])
def dashboard(msg):
    user = get_user(msg.from_user.id)
    if not user:
        return
    files = get_user_files(msg.from_user.id)
    points = user[2]
    token = user[1]
    used = get_storage_used(token) if token else 0
    quota = 10 * 1024**3

    text = f"📊 Dashboard:\n\n"
    text += f"🔐 Token set: {'✅' if token else '❌'}\n"
    text += f"🧾 Files: {len(files)}\n"
    text += f"💾 Storage used: {round(used / (1024**2), 2)} MB / 10240 MB\n"
    text += f"🏆 Points: {points}"
    bot.send_message(msg.chat.id, text)

# --- WEBHOOK SETUP ---
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "ok"

@app.route("/")
def index():
    return "Bot Running"

if __name__ == '__main__':
    import logging
    import sys
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + BOT_TOKEN)
    app.run(host="0.0.0.0", port=10000)
