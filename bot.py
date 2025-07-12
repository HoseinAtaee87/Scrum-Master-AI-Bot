import logging
import os
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import asyncio
import tempfile
import subprocess

logging.basicConfig(level=logging.INFO)

BOT_TOKEN   = os.getenv("BOT_TOKEN")
HF_TOKEN    = os.getenv("HF_TOKEN")
HF_API_URL  = "https://router.huggingface.co/hf-inference/models/openai/whisper-large-v3-turbo"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام! خوش آمدید.\n"
        "🎙 لطفاً یک ویس (پیام صوتی) ارسال کنید تا به متن تبدیل شود."
    )

def speech_to_text_api(audio_bytes: bytes) -> str:
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "audio/wav"  # تغییر اینجا
    }

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
        ogg_file.write(audio_bytes)
        ogg_path = ogg_file.name

    wav_path = ogg_path.replace(".ogg", ".wav")
    
    # تبدیل به WAV با کیفیت مناسب
    subprocess.run([
        "ffmpeg", "-y",
        "-i", ogg_path,
        "-ar", "16000",
        "-ac", "1",
        "-acodec", "pcm_s16le",  # اضافه کردن کدک صحیح
        wav_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    with open(wav_path, "rb") as wav_file:
        resp = requests.post(HF_API_URL, headers=headers, data=wav_file, timeout=60)
    
    os.remove(ogg_path)
    os.remove(wav_path)
    
    resp.raise_for_status()
    return resp.json().get("text", "")

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # دریافت فایل و دانلودش
    voice = await update.message.voice.get_file()
    bio = await voice.download_as_bytearray()
    await update.message.reply_text("⏳ در حال تبدیل به متن... لطفاً صبر کنید.")

    try:
        # استفاده از asyncio برای اجرای sync API call در executor
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(
            None,
            lambda: speech_to_text_api(bytes(bio))
        )

        if not text or not text.strip():
            await update.message.reply_text("❌ متنی از صدا استخراج نشد.")
        else:
            await update.message.reply_text(f"📝 متن استخراج‌شده:\n\n{text}")
    except Exception as e:
        logging.error("Error in speech_to_text_api", exc_info=e)
        await update.message.reply_text(f"⚠️ خطا در تبدیل صدا به متن:\n{e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if name == "main":
    main()
