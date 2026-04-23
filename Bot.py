"""
🎵 Telegram Music Bot
YouTube'dan ashula nomi yoki ijrochi ismi bo'yicha qidirib,
foydalanuvchiga MP3 (audio) yoki Video klip ko'rinishida yuboradi.
"""

import asyncio
import logging
import os
import re
import uuid
from typing import Any, Dict, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from yt_dlp import YoutubeDL

# ============================================================
# Sozlamalar
# ============================================================
# TOKENINGIZ SHU YERGA QO'YILDI:
BOT_TOKEN = "8654220408:AAFOQe0sx1lPQ4YcrP4T7tuSs0e26TfzDQs"

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Telegram bot API limit: 50 MB upload
MAX_FILE_SIZE_MB = 49
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SEARCH_CACHE: Dict[str, Dict[str, Any]] = {}

# ============================================================
# Yordamchi funksiyalar (OS.REMOVE SHU YERDA)
# ============================================================
def safe_remove(path: Optional[str]) -> None:
    """Faylni xavfsiz o'chirish (os.remove)"""
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info("🗑 Fayl o'chirildi: %s", path)
    except Exception as e:
        logger.warning("Faylni o'chirishda xatolik: %s — %s", path, e)


def format_views(n: Optional[int]) -> str:
    if not n:
        return "—"
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def format_duration(sec: Optional[int]) -> str:
    if not sec:
        return "—"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def parse_upload_year(info: Dict[str, Any]) -> str:
    date = info.get("upload_date") or ""
    if len(date) >= 4 and date[:4].isdigit():
        return date[:4]
    return "—"


def search_youtube(query: str) -> Optional[Dict[str, Any]]:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "default_search": "ytsearch1",
        "extract_flat": False,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            data = ydl.extract_info(query, download=False)
            if not data:
                return None
            if "entries" in data:
                entries = [e for e in data["entries"] if e]
                if not entries:
                    return None
                return entries[0]
            return data
    except Exception as e:
        logger.error("Qidiruvda xatolik: %s", e)
        return None


def download_audio(video_id: str) -> Optional[str]:
    out_template = os.path.join(DOWNLOAD_DIR, f"{video_id}-{uuid.uuid4().hex}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=True
            )
            filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            mp3_path = base + ".mp3"
            return mp3_path if os.path.exists(mp3_path) else None
    except Exception as e:
        logger.error("Audio yuklashda xatolik: %s", e)
        return None


def download_video(video_id: str) -> Optional[str]:
    out_template = os.path.join(DOWNLOAD_DIR, f"{video_id}-{uuid.uuid4().hex}.%(ext)s")
    ydl_opts = {
        "format": (
            f"best[ext=mp4][filesize<{MAX_FILE_SIZE}]/"
            f"best[filesize<{MAX_FILE_SIZE}]/"
            "best[height<=480][ext=mp4]/best[height<=480]/best"
        ),
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=True
            )
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                base, _ = os.path.splitext(filename)
                for ext in (".mp4", ".mkv", ".webm"):
                    p = base + ext
                    if os.path.exists(p):
                        return p
                return None
            return filename
    except Exception as e:
        logger.error("Video yuklashda xatolik: %s", e)
        return None


def build_info_text(meta: Dict[str, Any]) -> str:
    title = meta.get("title", "—")
    uploader = meta.get("uploader", "—")
    views = format_views(meta.get("view_count"))
    year = meta.get("upload_year", "—")
    duration = format_duration(meta.get("duration"))

    return (
        f"🎶 <b>Topildi!</b>\n\n"
        f"🎤 <b>Ijrochi:</b> {uploader}\n"
        f"🎵 <b>Qo'shiq:</b> {title}\n"
        f"👁 <b>Ko'rishlar:</b> {views}\n"
        f"📅 <b>Joylangan yili:</b> {year}\n"
        f"⏱ <b>Davomiyligi:</b> {duration}\n\n"
        f"⬇️ Quyidagi tugmalardan birini tanlang:"
    )


def build_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎬 Video klip", callback_data=f"video|{token}"),
                InlineKeyboardButton("🎧 MP3 Audio", callback_data=f"audio|{token}"),
            ],
            [
                InlineKeyboardButton("🔁 Qayta qidirish", callback_data="search_again"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel"),
            ],
        ]
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🎵 Qo'shiq qidirish"],
            ["ℹ️ Bot haqida", "📞 Aloqa"],
        ],
        resize_keyboard=True,
    )


# ============================================================
# Handlers
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = (
        f"🎉 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
        "🎶 Men sizga YouTube'dan istalgan ashulani topib beraman.\n\n"
        "✍️ Iltimos, <b>ashula nomini</b> yoki <b>ijrochi ismini</b> yozing."
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard()
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()

    if text == "ℹ️ Bot haqida":
        return await update.message.reply_text("ℹ️ <b>Music Bot</b> - YouTube'dan MP3 va Videolar uchun.", parse_mode=ParseMode.HTML)
    if text == "📞 Aloqa":
        return await update.message.reply_text("📞 Admin: @username", parse_mode=ParseMode.HTML)
    if text == "🎵 Qo'shiq qidirish":
        return await update.message.reply_text("✍️ Ashula nomini yozing 🎶")

    if len(text) < 2:
        return await update.message.reply_text("⚠️ Kamida 2 ta belgi kiriting.")

    searching_msg = await update.message.reply_text("🔎 <b>Qidirilmoqda...</b> ⏳", parse_mode=ParseMode.HTML)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    info = await asyncio.to_thread(search_youtube, text)

    if not info or not info.get("id"):
        return await searching_msg.edit_text("😔 Hech narsa topilmadi.")

    meta = {
        "video_id": info.get("id"),
        "title": info.get("title", "—"),
        "uploader": info.get("uploader", "—"),
        "view_count": info.get("view_count"),
        "duration": info.get("duration"),
        "upload_year": parse_upload_year(info),
    }

    token = uuid.uuid4().hex[:12]
    SEARCH_CACHE[token] = meta
    await searching_msg.delete()

    await update.message.reply_text(
        build_info_text(meta),
        parse_mode=ParseMode.HTML,
        reply_markup=build_keyboard(token),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "cancel":
        return await query.edit_message_text("❌ Bekor qilindi.")
    if data == "search_again":
        return await query.edit_message_text("✍️ Ashula nomini yozing 🎶")

    action, token = data.split("|", 1)
    meta = SEARCH_CACHE.get(token)
    if not meta:
        return await query.edit_message_text("⚠️ Muddati o'tgan.")

    video_id, title, uploader = meta["video_id"], meta["title"], meta["uploader"]
    chat_id = query.message.chat_id

    status_msg = await context.bot.send_message(chat_id, "⏬ <b>Yuklanmoqda...</b> ⏳", parse_mode=ParseMode.HTML)
    file_path: Optional[str] = None

    try:
        if action == "audio":
            file_path = await asyncio.to_thread(download_audio, video_id)
            with open(file_path, "rb") as f:
                await context.bot.send_audio(chat_id=chat_id, audio=f, title=title, performer=uploader, caption=f"🎧 <b>{title}</b>", parse_mode=ParseMode.HTML)
        elif action == "video":
            file_path = await asyncio.to_thread(download_video, video_id)
            with open(file_path, "rb") as f:
                await context.bot.send_video(chat_id=chat_id, video=f, caption=f"🎬 <b>{title}</b>", parse_mode=ParseMode.HTML)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"😔 Xatolik: {e}")
    finally:
        safe_remove(file_path) # <--- Faylni o'chirish (OS.REMOVE)

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("🤖 Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
