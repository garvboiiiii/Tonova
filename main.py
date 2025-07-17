import os
import telebot
import requests
from db import (
    init_db, add_user, set_token, get_token,
    add_file, get_user_files, get_points,
    update_points, get_used_space
)

# Initialize DB
init_db()

# Setup Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Replace with actual token or use .env
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# Start
@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    name = message.from_user.first_name
    add_user(user_id, name)
    bot.send_message(
        message.chat.id,
        "👋 Welcome to the Web3 FileBot!\n\nUse /settoken <API_TOKEN> to link your Web3.Storage account.\nYou’ll earn points for every upload! 🚀"
    )

# Set API Token
@bot.message_handler(commands=['settoken'])
def settoken(message):
    parts = message.text.split(" ", 1)
    if len(parts) != 2:
        return bot.reply_to(message, "⚠️ Usage: /settoken <your-token>")
    user_id = str(message.from_user.id)
    token = parts[1].strip()
    set_token(user_id, token)
    bot.reply_to(message, "✅ Web3.Storage API token saved!")

# Upload command
@bot.message_handler(commands=['upload'])
def ask_file(message):
    bot.send_message(message.chat.id, "📎 Send me the file to upload (Max 100MB).")

# Handle file upload
@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = str(message.from_user.id)
    token = get_token(user_id)
    
    if not token:
        return bot.reply_to(message, "❌ You need to set your Web3.Storage token first with /settoken")

    used_space = get_used_space(user_id)
    max_space = 10 * 1024 * 1024 * 1024  # 10GB

    if used_space + message.document.file_size > max_space:
        return bot.reply_to(message, "🚫 Quota exceeded. You have 10GB limit.")

    # Download file
    file_info = bot.get_file(message.document.file_id)
    file_data = bot.download_file(file_info.file_path)

    # Upload to Web3.Storage
    files = {'file': (message.document.file_name, file_data)}
    headers = {'Authorization': f'Bearer {token}'}
    try:
        res = requests.post('https://api.web3.storage/upload', files=files, headers=headers)
    except Exception as e:
        return bot.reply_to(message, f"❌ Upload failed: {e}")

    if res.status_code == 200:
        cid = res.json().get("cid")
        add_file(user_id, message.document.file_name, cid, message.document.file_size)
        update_points(user_id, 10)
        bot.send_message(
            message.chat.id,
            f"✅ Uploaded successfully!\n\n🆔 CID: <code>{cid}</code>\n🔗 Link: https://{cid}.ipfs.dweb.link\n🎯 +10 points!"
        )
    else:
        bot.send_message(message.chat.id, "❌ Upload failed. Check your token or try again.")

# List user files
@bot.message_handler(commands=['files'])
def list_files(message):
    user_id = str(message.from_user.id)
    files = get_user_files(user_id)
    if not files:
        return bot.send_message(message.chat.id, "📂 No files uploaded yet.")
    
    msg = "<b>📁 Your Uploaded Files:</b>\n\n"
    for f in files:
        name, cid, size = f
        link = f"https://{cid}.ipfs.dweb.link"
        msg += f"• <b>{name}</b> ({round(size/1024, 2)} KB)\n🔗 {link}\n\n"

    bot.send_message(message.chat.id, msg)

# Show Points
@bot.message_handler(commands=['points'])
def show_points(message):
    user_id = str(message.from_user.id)
    points = get_points(user_id)
    bot.send_message(message.chat.id, f"🎯 You have <b>{points}</b> points.")

# Default fallback
@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.send_message(message.chat.id, "⚡ Commands:\n/settoken <token>\n/upload\n/files\n/points")

# Start polling
bot.infinity_polling()
