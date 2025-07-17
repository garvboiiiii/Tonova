# main.py
import os
import json
import time
import requests
from flask import Flask, request
from telebot import TeleBot, types
from threading import Thread
from datetime import datetime

# ========== CONFIGURATION ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Missing BOT_TOKEN env var")

bot = TeleBot(BOT_TOKEN, parse_mode='HTML')
app = Flask(__name__)

DATA_FILE = "data.json"
os.makedirs("uploads", exist_ok=True)

# ========== INITIALIZE DATA ==========
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({}, f)

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ========== UTILS ==========
MAX_STORAGE_BYTES = 10 * 1024 * 1024 * 1024  # 10GB


def get_user(user_id):
    data = load_data()
    return data.get(str(user_id), None)

def set_user(user_id, info):
    data = load_data()
    data[str(user_id)] = info
    save_data(data)


# ========== BOT HANDLERS ==========
@bot.message_handler(commands=['start'])
def start(m):
    user_id = str(m.from_user.id)
    data = load_data()
    if user_id not in data:
        data[user_id] = {
            "token": None,
            "files": [],
            "used": 0,
            "points": 0
        }
        save_data(data)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔐 Add API Token", "📤 Upload File")
    markup.row("📁 My Files", "📊 Usage")
    bot.send_message(m.chat.id, "👋 Welcome! Use the menu below:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🔐 Add API Token")
def add_token(m):
    bot.send_message(m.chat.id, "🔑 Send me your Web3.Storage API Token.")
    bot.register_next_step_handler(m, save_token)

def save_token(m):
    user = get_user(m.from_user.id)
    user["token"] = m.text.strip()
    set_user(m.from_user.id, user)
    bot.send_message(m.chat.id, "✅ Token saved!")

@bot.message_handler(func=lambda m: m.text == "📤 Upload File")
def request_file(m):
    user = get_user(m.from_user.id)
    if not user or not user.get("token"):
        return bot.send_message(m.chat.id, "❌ Please add your Web3.Storage token first (🔐 Add API Token).")
    bot.send_message(m.chat.id, "📎 Send the file now (max 100MB)")

@bot.message_handler(content_types=['document'])
def handle_file(m):
    user_id = str(m.from_user.id)
    user = get_user(user_id)
    if not user or not user.get("token"):
        return bot.send_message(m.chat.id, "❌ Missing token. Use 🔐 Add API Token")

    doc = m.document
    if doc.file_size > 100 * 1024 * 1024:
        return bot.send_message(m.chat.id, "❌ File too big (max 100MB)")

    if user["used"] + doc.file_size > MAX_STORAGE_BYTES:
        return bot.send_message(m.chat.id, "❌ Storage quota exceeded (10GB)")

    file_info = bot.get_file(doc.file_id)
    file_data = bot.download_file(file_info.file_path)
    local_path = f"uploads/{doc.file_name}"
    with open(local_path, "wb") as f:
        f.write(file_data)

    bot.send_message(m.chat.id, "⏳ Uploading to Web3.Storage...")
    headers = {"Authorization": f"Bearer {user['token']}", "Content-Type": "application/octet-stream"}
    with open(local_path, 'rb') as f:
        res = requests.post("https://api.web3.storage/upload", headers=headers, data=f)

    if res.status_code == 200:
        cid = res.json()['cid']
        user['files'].append({"name": doc.file_name, "size": doc.file_size, "cid": cid, "time": time.time()})
        user['used'] += doc.file_size
        user['points'] += 10
        set_user(user_id, user)
        bot.send_message(m.chat.id, f"✅ Uploaded! CID: <code>{cid}</code>\n🎉 +10 points!")
    else:
        bot.send_message(m.chat.id, "❌ Upload failed.")

@bot.message_handler(func=lambda m: m.text == "📁 My Files")
def list_files(m):
    user = get_user(m.from_user.id)
    if not user or not user.get("files"):
        return bot.send_message(m.chat.id, "📂 No files uploaded yet.")
    msg = "<b>Your Files:</b>\n"
    for f in user['files'][-5:]:
        size_mb = round(f['size'] / (1024 * 1024), 2)
        msg += f"- {f['name']} ({size_mb}MB): https://{f['cid']}.ipfs.dweb.link\n"
    bot.send_message(m.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == "📊 Usage")
def show_usage(m):
    user = get_user(m.from_user.id)
    used = user.get("used", 0)
    percent = round((used / MAX_STORAGE_BYTES) * 100, 2)
    gb_used = round(used / (1024**3), 2)
    points = user.get("points", 0)
    msg = f"🧠 Storage used: {gb_used} GB / 10 GB ({percent}%)\n💎 Points: {points}"
    bot.send_message(m.chat.id, msg)

# ========== WEB SERVER FOR RENDER ==========
@app.route('/')
def home():
    return "Bot is running."

# ========== RUN BOTH ==========
def run_bot():
    bot.infinity_polling()

def run_web():
    app.run(host="0.0.0.0", port=8080)

if __name__ == '__main__':
    Thread(target=run_bot).start()
    Thread(target=run_web).start()
