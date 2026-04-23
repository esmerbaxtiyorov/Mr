import os
import subprocess
import telebot
import json
import time
from telebot import types
from flask import Flask, request, abort

# --- KONFIGURATSIYA ---
# Tokenni Render Dashboard'da "BOT_TOKEN" deb nomlang
TOKEN = os.getenv("BOT_TOKEN", "8654220408:AAFOQe0sx1lPQ4YcrP4T7tuSs0e26TfzDQs")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Render manzilingizni avtomatik aniqlash yoki Dashboard'da "RENDER_EXTERNAL_URL" deb yozing
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://mr-1-4sqq.onrender.com")
WEBHOOK_URL = f"{BASE_URL}/webhook"

# --- WEB-SERVER ---
@app.route('/')
def home():
    return {"status": "online", "message": "Music Bot is running! 🎵"}

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data(as_text=True)
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'ok', 200
    abort(403)

# --- YOUTUBE QIDIRUV FUNKSIYASI ---
def get_video_info(query):
    cmd = [
        'yt-dlp', f'ytsearch1:{query}', '--dump-json', 
        '--no-playlist', '--quiet', '--force-ipv4'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if not result.stdout.strip():
        raise Exception("Hech narsa topilmadi")
    return json.loads(result.stdout.strip())

# --- /START BUYRUG'I ---
@bot.message_handler(commands=['start'])
def start(message):
    welcome_text = (
        "👋 *Assalomu alaykum!* \n\n"
        "✨ Men eng tezkor yuklovchi botman! \n"
        "🎙 *Ashulachi ismi* yoki 🎵 *Qo'shiq nomini* yozing...\n\n"
        "🚀 Men sizga eng sara video va MP3larni topib beraman!"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown')

# --- ASOSIY QIDIRUV ---
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    processing_msg = bot.reply_to(message, "🔍 *Qidirilmoqda... biroz kuting...* ⏳", parse_mode='Markdown')
    try:
        info = get_video_info(message.text)
        url = info['webpage_url']
        title = info.get('title', 'Noma\'lum')
        views = info.get('view_count', 0)
        upload_date = info.get('upload_date', '00000000')
        year = upload_date[:4]
        uploader = info.get('uploader', 'Noma\'lum ijrochi')

        info_text = (
            f"🎬 *Topildi:* {title}\n\n"
            f"👤 *Ijrochi:* {uploader}\n"
            f"👁 *Ko'rishlar:* {views:,}\n"
            f"📅 *Joylandi:* {year}-yil\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 *Yuklash uchun formatni tanlang:*"
        )

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🎬 Video Klip", callback_data=f"vid|{url}"),
            types.InlineKeyboardButton("🎵 MP3 Audio", callback_data=f"aud|{url}")
        )
        
        bot.edit_message_text(info_text, message.chat.id, processing_msg.message_id, reply_markup=markup, parse_mode='Markdown')
    
    except Exception as e:
        bot.edit_message_text("😔 *Hech narsa topilmadi...* \nIltimos, nomni aniqroq yozing! ✍️", message.chat.id, processing_msg.message_id, parse_mode='Markdown')

# --- YUKLASH VA O'CHIRISH ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    action, url = call.data.split('|', 1)
    # Fayl nomiga vaqt belgisini qo'shish (to'qnashuv bo'lmasligi uchun)
    temp_id = int(time.time())
    final_path = None
    
    bot.answer_callback_query(call.id, "🚀 Tayyorlanmoqda...")
    status_msg = bot.send_message(call.message.chat.id, "🚚 *Fayl yuborilmoqda...* 📤", parse_mode='Markdown')

    try:
        if action == "vid":
            final_path = f"video_{temp_id}.mp4"
            # Video yuklash
            subprocess.run(['yt-dlp', '-f', 'best[height<=480]', '-o', final_path, url], timeout=300)
            with open(final_path, 'rb') as f:
                bot.send_video(call.message.chat.id, f, caption="✅ *Video yuklab olindi!* @Video_Klip_Bot", parse_mode='Markdown')
        
        elif action == "aud":
            final_path = f"audio_{temp_id}.mp3"
            # MP3 yuklash (%(ext)s yt-dlp tomonidan avtomatik almashtiriladi)
            subprocess.run(['yt-dlp', '-x', '--audio-format', 'mp3', '-o', f"audio_{temp_id}.%(ext)s", url], timeout=300)
            with open(final_path, 'rb') as f:
                bot.send_audio(call.message.chat.id, f, caption="✅ *MP3 yuklab olindi!* @Video_Klip_Bot", parse_mode='Markdown')

        bot.delete_message(call.message.chat.id, status_msg.message_id)

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ *Xatolik yuz berdi:* Server band yoki fayl juda katta.")

    finally:
        # Faylni o'chirish (disk to'lib qolmasligi uchun)
        if final_path and os.path.exists(final_path):
            try:
                os.remove(final_path)
            except:
                pass

# --- ISHGA TUSHIRISH ---
if __name__ == "__main__":
    # Webhookni yangilash
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEBHOOK_URL)
    
    # Render PORTni avtomatik beradi
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
