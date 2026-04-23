import os
import subprocess
import telebot
import threading
import json
import time
from telebot import types
from flask import Flask

# --- KONFIGURATSIYA ---
TOKEN = "8654220408:AAFOQe0sx1lPQ4YcrP4T7tuSs0e26TfzDQs"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__) # <-- TO'G'RILANDI: name emas, __name__ bo'lishi shart

# --- WEB-SERVER ---
@app.route('/')
def home():
    return "Bot 24/7 rejimida yoniq va ishlamoqda!"

def run_server():
    # Render portni avtomatik beradi, shuning uchun os.environ orqali olamiz
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- YOUTUBE QIDIRUV ---
def get_video_info(query):
    result = subprocess.run(
        ['yt-dlp', f'ytsearch1:{query}', '--dump-json',
         '--no-playlist', '--quiet', '--no-warnings'],
        capture_output=True, text=True, timeout=30
    )
    if not result.stdout.strip():
        raise Exception("Hech narsa topilmadi")
    return json.loads(result.stdout.strip())

# --- /START BUYRUG'I ---
@bot.message_handler(commands=['start'])
def start(message):
    text = (
        "╔══════════════════════╗\n"
        "║  🎵  VIDEO KLIP & MP3  🎵  ║\n"
        "╚══════════════════════╝\n\n"
        f"Salom, *{message.from_user.first_name}*! 👋🏻\n\n"
        "🔍 Qo'shiq yoki ijrochi nomini yozing\n"
        "📥 Men sizga video klip yoki MP3 topib beraman"
    )
    bot.reply_to(message, text, parse_mode='Markdown')

# --- ASOSIY QIDIRUV ---
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    msg = bot.reply_to(message, "🔍 *Qidirilmoqda...*", parse_mode='Markdown')
    try:
        info = get_video_info(message.text)
        url = info['webpage_url']
        title = info.get('title', "Noma'lum")
        duration = info.get('duration', 0)
        
        mins, secs = divmod(int(duration), 60)

        text = (
            "🎬 *Topildi!*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎵 *{title}*\n"
            f"⏱ Davomiylik: {mins}:{secs:02d}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⬇️ Tanlang:"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🎬 Video klip (480p)", callback_data=f"vid|{url}"),
            types.InlineKeyboardButton("🎵 MP3 yuklab olish", callback_data=f"aud|{url}")
        )

        bot.edit_message_text(text, message.chat.id, msg.message_id, reply_markup=markup, parse_mode='Markdown')
    except Exception:
        bot.edit_message_text("😔 *Topilmadi.* Boshqa nom bilan urinib ko'ring.", message.chat.id, msg.message_id, parse_mode='Markdown')

# --- YUKLASH VA O'CHIRISH ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    action, url = call.data.split('|', 1)
    temp_name = f"file_{int(time.time())}"
    final_path = None

    try:
        bot.answer_callback_query(call.id, "⏳ Tayyorlanmoqda...")
        status_msg = bot.send_message(call.message.chat.id, "🚚 *Fayl yuklanmoqda...*", parse_mode='Markdown')
        
        if action == "vid":
            final_path = f"{temp_name}.mp4"
            subprocess.run([
                'yt-dlp', url, '-f', 'best[height<=480]', 
                '-o', final_path, '--no-playlist', '--quiet'
            ], timeout=300)
            with open(final_path, 'rb') as f:
                bot.send_video(call.message.chat.id, f, caption="✅ Video yuborildi!")
        
        elif action == "aud":
            final_path = f"{temp_name}.mp3"
            subprocess.run([
                'yt-dlp', url, '-x', '--audio-format', 'mp3', 
                '-o', temp_name, '--no-playlist', '--quiet'
            ], timeout=300)
            if not os.path.exists(final_path) and os.path.exists(temp_name):
                final_path = temp_name
            with open(final_path, 'rb') as f:
                bot.send_audio(call.message.chat.id, f, caption="✅ MP3 yuborildi!")

        bot.delete_message(call.message.chat.id, status_msg.message_id)

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Xatolik: {e}")
    finally:
        # 🗑 Serverni tozalash
        if final_path and os.path.exists(final_path):
            try: os.remove(final_path)
            except: pass

# --- ISHGA TUSHIRISH ---
if __name__ == "__main__": # <-- TO'G'RILANDI: name == "main" emas, __name__ == "__main__"
    threading.Thread(target=run_server, daemon=True).start()
    print("🤖 Bot ishga tushdi...")
    bot.infinity_polling(timeout=60, skip_pending=True)
