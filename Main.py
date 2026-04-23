import os
import logging
import tempfile
import threading
import time
from typing import Optional

import telebot
from telebot import types
import yt_dlp
import imageio_ffmpeg

# ─────────────── KONFIGURATSIYA ───────────────
# Sening shaxsiy tokening
BOT_TOKEN = "8654220408:AAFOQe0sx1lPQ4YcrP4T7tuSs0e26TfzDQs"

# Tizim sozlamalari
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
DOWNLOAD_DIR = tempfile.gettempdir()
TELEGRAM_LIMIT = 49 * 1024 * 1024  # 50MB cheklov

# Loglarni chiroyli qilish
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
log = logging.getLogger("MusicUzPro")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
bot.remove_webhook()

# ─────────────── YORDAMCHI FUNKSIYALAR ───────────────

def search_yt(query: str):
    """YouTube'dan ma'lumotlarni xavfsiz qidirish"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch1',
        'noplaylist': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info and len(info['entries']) > 0:
                return info['entries'][0]
            return None
        except Exception as e:
            log.error(f"Qidiruvda xatolik: {e}")
            return None

def download_file(url: str, mode: str, title: str):
    """Video yoki Audio yuklab olish"""
    file_id = str(int(time.time()))
    ext = "mp4" if mode == "video" else "mp3"
    out_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.{ext}")

    ydl_opts = {
        'format': 'best[ext=mp4][filesize<48M]/best[filesize<48M]' if mode == "video" else 'bestaudio/best',
        'outtmpl': out_path.replace(".mp3", ".%(ext)s") if mode == "audio" else out_path,
        'ffmpeg_location': FFMPEG_PATH,
        'quiet': True,
        'no_warnings': True,
    }

    if mode == "audio":
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    
    return out_path if mode == "video" else out_path

# ─────────────── BOT BUYRUQLARI ───────────────

@bot.message_handler(commands=['start'])
def start_cmd(message):
    welcome_text = (
        f"👋 <b>Salom, {message.from_user.first_name}!</b>\n\n"
        f"🎵 <b>Music Uz Pro Best Bot</b> xizmatiga xush kelibsiz!\n"
        f"Men orqali YouTube'dan istalgan musiqa va videoni topishingiz mumkin.\n\n"
        f"⌨️ <b>Qidirishni boshlash uchun qo'shiq nomini yozing:</b>"
    )
    bot.send_message(message.chat.id, welcome_text)

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    query = message.text.strip()
    if not query: return

    status = bot.send_message(message.chat.id, "🔍 <b>Qidirilmoqda...</b>")
    
    result = search_yt(query)
    
    if not result:
        bot.edit_message_text("❌ <b>Afsuski, hech narsa topilmadi.</b>\nIltimos, nomini aniqroq yozing.", message.chat.id, status.message_id)
        return

    v_id = result.get('id')
    v_title = result.get('title')
    v_url = result.get('webpage_url')
    v_duration = result.get('duration')
    v_views = result.get('view_count', 0)
    v_thumb = result.get('thumbnail')

    # Vaqtni formatlash (minut:sekund)
    mins, secs = divmod(v_duration, 60)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_audio = types.InlineKeyboardButton("🎵 MP3 Yuklash", callback_data=f"audio|{v_id}")
    btn_video = types.InlineKeyboardButton("🎬 Video Yuklash", callback_data=f"video|{v_id}")
    markup.add(btn_audio, btn_video)

    caption = (
        f"🎼 <b>Nomi:</b> {v_title}\n"
        f"⏱ <b>Davomiyligi:</b> {mins}:{secs:02d}\n"
        f"👁 <b>Ko'rishlar:</b> {v_views:,}\n"
        f"🔗 <a href='{v_url}'>YouTube manzili</a>\n\n"
        f"🔰 <b>Qanday formatda yuklamoqchisiz?</b>"
    )

    bot.delete_message(message.chat.id, status.message_id)
    if v_thumb:
        bot.send_photo(message.chat.id, v_thumb, caption=caption, reply_markup=markup)
    else:
        bot.send_message(message.chat.id, caption, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    mode, v_id = call.data.split("|")
    url = f"https://www.youtube.com/watch?v={v_id}"
    
    # Tugmani vaqtinchalik o'zgartirish
    bot.edit_message_caption(
        caption=call.message.caption + f"\n\n⏳ <b>{mode.capitalize()} tayyorlanmoqda...</b>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=None
    )

    try:
        file_path = download_file(url, mode, v_id)
        
        with open(file_path, 'rb') as f:
            if mode == "video":
                bot.send_video(call.message.chat.id, f, caption="✅ @MusicUzPro yuklab berdi")
            else:
                bot.send_audio(call.message.chat.id, f, caption="✅ @MusicUzPro yuklab berdi")
        
        # Faylni o'chirish (tozalash)
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ <b>Xatolik yuz berdi:</b> {str(e)[:100]}")
    
    # Xabarni o'chirish yoki yangilash
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

# ─────────────── ISHGA TUSHIRISH ───────────────

if __name__ == "__main__":
    log.info("🤖 Bot Render platformasida muvaffaqiyatli ishga tushdi!")
    bot.infinity_polling()
