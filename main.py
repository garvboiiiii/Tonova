import os
import json
import requests
from flask import Flask, request
from telebot import TeleBot, types
from datetime import datetime

API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("Missing BOT_TOKEN")

bot = TeleBot(API_TOKEN, parse_mode='HTML')
app = Flask(__name__)

DATA_FILE = "users.json"
FILES_FILE = "files.json"
os.makedirs("uploads", exist_ok=True)

# Initialize files if not exist
for f, default in [(DATA_FILE, {}), (FILES_FILE, {})]:
    if not os.path.exists(f):
        with open(f, 'w') as file:
            json.dump(default, file)

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

@bot.message_handler(commands=['start'])
def start(m):
    user_id = str(m.from_user.id)
    users = load_json(DATA_FILE)
    if user_id not in users:
        users[user_id] = {"name": m.from_user.first_name, "token": None, "points": 0}
        save_json(DATA_FILE, users)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔐 Add Web3.Storage API Token", "📤 Upload File")
    markup.row("📁 My Files", "🏆 My Points")
    markup.row("🌐 Create Web3.Storage Account")
    bot.send_message(m.chat.id, "👋 Welcome to your decentralized storage bot!", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🔐 Add Web3.Storage API Token")
def ask_api_token(m):
    bot.send_message(m.chat.id, "🔑 Please send your Web3.Storage API token. You can get one from https://web3.storage/account/")
    bot.register_next_step_handler(m, save_token)

def save_token(m):
    user_id = str(m.from_user.id)
    token = m.text.strip()
    # Validate token
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get("https://api.web3.storage/user/uploads", headers=headers)
    if res.status_code == 200:
        users = load_json(DATA_FILE)
        users[user_id]["token"] = token
        save_json(DATA_FILE, users)
        bot.send_message(m.chat.id, "✅ Token saved successfully!")
    else:
        bot.send_message(m.chat.id, "❌ Invalid API token. Please try again.")

@bot.message_handler(func=lambda m: m.text == "🌐 Create Web3.Storage Account")
def send_account_link(m):
    bot.send_message(m.chat.id, "🔗 Create an account here: https://web3.storage/account/")

@bot.message_handler(func=lambda m: m.text == "📤 Upload File")
def prompt_upload(m):
    user_id = str(m.from_user.id)
    users = load_json(DATA_FILE)
    if users[user_id].get("token"):
        bot.send_message(m.chat.id, "📎 Please send the file (max 100MB).")
    else:
        bot.send_message(m.chat.id, "❗ You need to set your Web3.Storage token first by clicking '🔐 Add Web3.Storage API Token'.")

@bot.message_handler(content_types=['document'])
def handle_file(m):
    user_id = str(m.from_user.id)
    users = load_json(DATA_FILE)
    token = users.get(user_id, {}).get("token")
    if not token:
        return bot.send_message(m.chat.id, "❗ You must add your Web3.Storage token first.")

    file_info = bot.get_file(m.document.file_id)
    file_data = bot.download_file(file_info.file_path)
    temp_path = os.path.join("uploads", m.document.file_name)

    with open(temp_path, "wb") as f:
        f.write(file_data)

    headers = {
        "Authorization": f"Bearer {token}"
    }
    files = {
        'file': (m.document.file_name, open(temp_path, 'rb'))
    }

    res = requests.post("https://api.web3.storage/upload", headers=headers, files=files)

    if res.status_code == 200:
        cid = res.json()["cid"]
        files_map = load_json(FILES_FILE)
        files_map.setdefault(user_id, []).append({
            "name": m.document.file_name,
            "cid": cid,
            "size": m.document.file_size,
            "uploaded_at": datetime.utcnow().isoformat()
        })
        save_json(FILES_FILE, files_map)

        users[user_id]["points"] += 10
        save_json(DATA_FILE, users)

        bot.send_message(m.chat.id, f"✅ Uploaded!
🧾 CID: <code>{cid}</code>
🎉 +10 points!")
    else:
        bot.send_message(m.chat.id, "❌ Upload failed. Please check your token or try again later.")

@bot.message_handler(func=lambda m: m.text == "📁 My Files")
def list_files(m):
    user_id = str(m.from_user.id)
    files_map = load_json(FILES_FILE)
    files = files_map.get(user_id, [])
    if not files:
        return bot.send_message(m.chat.id, "📭 No files uploaded yet.")
    msg = "📁 <b>Your Files:</b>\n"
    for f in files:
        link = f"https://{f['cid']}.ipfs.w3s.link"
        msg += f"🔹 <b>{f['name']}</b> ({round(f['size']/1024,1)} KB)\n🔗 <a href='{link}'>Access</a>\n"
    bot.send_message(m.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == "🏆 My Points")
def show_points(m):
    user_id = str(m.from_user.id)
    users = load_json(DATA_FILE)
    points = users[user_id].get("points", 0)
    bot.send_message(m.chat.id, f"🏆 <b>You have {points} points!</b>")

if __name__ == "__main__":
    from threading import Thread
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    print("🤖 Bot is running...")
    bot.infinity_polling()
