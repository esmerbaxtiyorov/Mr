"""
🎵 Telegram Music & Video Bot
Render.com'ga 100% mos. Tashqi tizim kutubxonalari kerak emas
(ffmpeg imageio-ffmpeg orqali Python paket sifatida o'rnatiladi).
"""

import os
import re
import logging
import tempfile
import threading
from typing import Optional

import telebot
from telebot import types
import yt_dlp
import imageio_ffmpeg

# ─────────────── Konfiguratsiya ───────────────
# BOT_TOKEN ni to'g'ridan-to'g'ri shu yerga joylashtirdim:
BOT_TOKEN = "8654220408:AAFOQe0sx1lPQ4YcrP4T7tuSs0e26TfzDQs"

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
DOWNLOAD_DIR = tempfile.gettempdir()
TELEGRAM_LIMIT = 49 * 1024 * 1024  # 49 MB (Telegram bot upload chegarasi 50 MB)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("music-bot")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Foydalanuvchi -> oxirgi qidiruv natijasi (callback uchun kichik ID kerak)
user_cache: dict[int, dict] = {}
cache_lock = threading.Lock()


# ─────────────── Yordamchilar ───────────────
def safe_remove(path: Optional[str]) -> None:
    """os.remove – xatolik bo'lsa ham yiqilmaydi."""
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
            log.info("🧹 O'chirildi: %s", path)
    except Exception as e:
        log.warning("Faylni o'chirib bo'lmadi (%s): %s", path, e)


def format_views(n: int) -> str:
    if n is None:
        return "—"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def search_youtube(query: str) -> dict:
    """YouTube'da qidirish (faqat metadata)."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "default_search": "ytsearch1",
        "noplaylist": True,
        "extract_flat": False,
        "socket_timeout": 15,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=False)
    if "entries" in info:
        if not info["entries"]:
            raise ValueError("Hech narsa topilmadi")
        info = info["entries"][0]
    return info


def download_video(video_id: str) -> tuple[str, dict]:
    """Videoklipni MP4 formatida yuklab olish."""
    out = os.path.join(DOWNLOAD_DIR, f"{video_id}_video.%(ext)s")
    opts = {
        "format": (
            "best[ext=mp4][filesize<48M]/"
            "best[filesize<48M]/"
            "worst[ext=mp4]"
        ),
        "outtmpl": out,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "ffmpeg_location": FFMPEG_PATH,
        "socket_timeout": 30,
        "retries": 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}", download=True
        )
        path = ydl.prepare_filename(info)
    return path, info


def download_audio(video_id: str) -> tuple[str, dict]:
    """Audio ni MP3 formatida yuklab olish."""
    out_template = os.path.join(DOWNLOAD_DIR, f"{video_id}_audio.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "ffmpeg_location": FFMPEG_PATH,
        "socket_timeout": 30,
        "retries": 3,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}", download=True
        )
    final = os.path.join(DOWNLOAD_DIR, f"{video_id}_audio.mp3")
    return final, info


# ─────────────── Buyruqlar ───────────────
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    name = msg.from_user.first_name or "doʻst"
    text = (
        f"👋 Salom, <b>{name}</b>! 🎶✨\n\n"
        f"🎤 Iltimos, <b>ashulachi ismini</b> yoki <b>ashula nomini</b> yozing.\n"
        f"⚡️ Men siz uchun YouTube'dan eng tezkor tarzda topib beraman!\n\n"
        f"🎬 Videoklipni yuklab olish — <b>Videoklip</b> tugmasi\n"
        f"🎵 MP3 audioni yuklab olish — <b>MP3</b> tugmasi\n\n"
        f"💡 /help — yordam"
    )
    bot.send_message(msg.chat.id, text)


@bot.message_handler(commands=["help"])
def cmd_help(msg):
    bot.send_message(
        msg.chat.id,
        "ℹ️ <b>Yordam menyusi</b>\n\n"
        "🔍 Qidiruv: shunchaki ashula nomi yoki ijrochi nomini yuboring\n"
        "🎬 <b>Videoklip</b> — to'liq videoni yuklaydi\n"
        "🎵 <b>MP3</b> — toza audio (192 kbps) yuklaydi\n"
        "👁 Ko'rishlar soni va 📅 yili ham ko'rsatiladi\n\n"
        "⚠️ Telegram cheklovi: 50 MB. Juda uzun videolar yuklanmasligi mumkin.",
    )


# ─────────────── Qidiruv ───────────────
@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(msg):
    query = (msg.text or "").strip()
    if not query or query.startswith("/"):
        return

    waiting = bot.send_message(msg.chat.id, "🔎 Qidirilmoqda... ⏳✨")

    try:
        info = search_youtube(query)
    except Exception as e:
        log.exception("Qidirishda xatolik: %s", e)
        bot.edit_message_text(
            "⚠️ Hech narsa topilmadi. Boshqa nom bilan urinib ko'ring. 🙏",
            msg.chat.id,
            waiting.message_id,
        )
        return

    video_id = info.get("id", "")
    title = info.get("title", "Nomaʼlum")
    uploader = info.get("uploader") or info.get("channel") or "Nomaʼlum"
    views = info.get("view_count") or 0
    upload_date = info.get("upload_date") or ""
    year = upload_date[:4] if len(upload_date) >= 4 else "—"
    duration = info.get("duration") or 0
    mins, secs = divmod(int(duration), 60)

    with cache_lock:
        user_cache[msg.from_user.id] = {
            "video_id": video_id,
            "title": title,
            "uploader": uploader,
        }

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🎬 Videoklip", callback_data=f"v:{video_id}"),
        types.InlineKeyboardButton("🎵 MP3", callback_data=f"a:{video_id}"),
    )
    kb.add(
        types.InlineKeyboardButton(
            f"👁 {format_views(views)} koʻrishlar", callback_data="noop"
        )
    )
    kb.add(
        types.InlineKeyboardButton(
            f"🎤 {uploader} — {title}"[:64], callback_data="noop"
        )
    )
    kb.add(
        types.InlineKeyboardButton(
            f"📅 YouTube'ga joylangan: {year}-yil", callback_data="noop"
        )
    )

    caption = (
        f"✅ <b>Topildi!</b> 🎉\n\n"
        f"🎶 <b>{title}</b>\n"
        f"🎤 <i>{uploader}</i>\n"
        f"⏱ {mins}:{secs:02d}\n"
        f"👁 {format_views(views)} ko'rishlar\n"
        f"📅 {year}-yil\n\n"
        f"👇 Quyidagi tugmalardan birini tanlang:"
    )

    try:
        bot.delete_message(msg.chat.id, waiting.message_id)
    except Exception:
        pass

    thumb = info.get("thumbnail")
    if thumb:
        try:
            bot.send_photo(msg.chat.id, thumb, caption=caption, reply_markup=kb)
            return
        except Exception:
            pass
    bot.send_message(msg.chat.id, caption, reply_markup=kb)


# ─────────────── Callback'lar ───────────────
@bot.callback_query_handler(func=lambda c: c.data == "noop")
def cb_noop(c):
    bot.answer_callback_query(c.id, "ℹ️ Bu maʼlumot uchun tugma")


@bot.callback_query_handler(func=lambda c: c.data.startswith("v:"))
def cb_video(c):
    video_id = c.data.split(":", 1)[1]
    bot.answer_callback_query(c.id, "🎬 Videoklip yuklanmoqda... ⏳")
    status = bot.send_message(
        c.message.chat.id, "🎬 Videoklip yuklanmoqda... ⚡️\nIltimos, biroz kuting..."
    )
    path: Optional[str] = None
    try:
        path, info = download_video(video_id)
        if not os.path.exists(path):
            raise FileNotFoundError("Yuklab bo'lmadi")
        size = os.path.getsize(path)
        if size > TELEGRAM_LIMIT:
            raise ValueError(
                f"Video juda katta ({size / 1024 / 1024:.1f} MB). "
                f"Telegram cheklovi 50 MB."
            )
        title = info.get("title", "")
        uploader = info.get("uploader") or info.get("channel") or ""
        with open(path, "rb") as f:
            bot.send_video(
                c.message.chat.id,
                f,
                caption=(
                    f"🎬 <b>{title}</b>\n"
                    f"🎤 <i>{uploader}</i>\n\n"
                    f"✨ Yana qoʻshiq qidirish uchun nom yuboring 🎶"
                ),
                supports_streaming=True,
                timeout=120,
            )
        bot.delete_message(c.message.chat.id, status.message_id)
    except Exception as e:
        log.exception("Video yuklashda xatolik")
        try:
            bot.edit_message_text(
                f"⚠️ Videoni yuklab boʻlmadi 😔\n<code>{str(e)[:200]}</code>",
                c.message.chat.id,
                status.message_id,
            )
        except Exception:
            pass
    finally:
        safe_remove(path)


@bot.callback_query_handler(func=lambda c: c.data.startswith("a:"))
def cb_audio(c):
    video_id = c.data.split(":", 1)[1]
    bot.answer_callback_query(c.id, "🎵 MP3 yuklanmoqda... ⏳")
    status = bot.send_message(
        c.message.chat.id, "🎵 MP3 yuklanmoqda... ⚡️\nIltimos, biroz kuting..."
    )
    path: Optional[str] = None
    intermediate_files: list[str] = []
    try:
        path, info = download_audio(video_id)
        # MP3 ga aylantirilgandan keyin asl bestaudio fayllar qoldiq bo'lishi mumkin
        for ext in ("webm", "m4a", "opus", "mp4", "ogg"):
            intermediate_files.append(
                os.path.join(DOWNLOAD_DIR, f"{video_id}_audio.{ext}")
            )
        if not os.path.exists(path):
            raise FileNotFoundError("MP3 yaratilmadi")
        size = os.path.getsize(path)
        if size > TELEGRAM_LIMIT:
            raise ValueError(
                f"Audio juda katta ({size / 1024 / 1024:.1f} MB)."
            )
        title = info.get("title", "")
        uploader = info.get("uploader") or info.get("channel") or ""
        duration = int(info.get("duration") or 0)
        with open(path, "rb") as f:
            bot.send_audio(
                c.message.chat.id,
                f,
                title=title,
                performer=uploader,
                duration=duration,
                caption=(
                    f"🎵 <b>{title}</b>\n"
                    f"🎤 <i>{uploader}</i>\n\n"
                    f"✨ Yana qoʻshiq qidirish uchun nom yuboring 🎶"
                ),
                timeout=120,
            )
        bot.delete_message(c.message.chat.id, status.message_id)
    except Exception as e:
        log.exception("Audio yuklashda xatolik")
        try:
            bot.edit_message_text(
                f"⚠️ Audioni yuklab boʻlmadi 😔\n<code>{str(e)[:200]}</code>",
                c.message.chat.id,
                status.message_id,
            )
        except Exception:
            pass
    finally:
        safe_remove(path)
        for f in intermediate_files:
            safe_remove(f)


# ─────────────── Xatolik ushlovchi ───────────────
@bot.message_handler(func=lambda m: True)
def fallback(msg):
    bot.send_message(
        msg.chat.id,
        "🤔 Tushunmadim. Qoʻshiq nomi yoki ijrochi nomini yuboring 🎵",
    )


# ─────────────── Ishga tushirish ───────────────
if __name__ == "__main__":
    log.info("🤖 Bot ishga tushmoqda... ffmpeg: %s", FFMPEG_PATH)
    while True:
        try:
            bot.infinity_polling(
                skip_pending=True, timeout=30, long_polling_timeout=30
            )
        except Exception as e:
            log.exception("Polling xatoligi, qayta ulanish: %s", e)
