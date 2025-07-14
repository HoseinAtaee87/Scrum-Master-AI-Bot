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
import re

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
WHISPER_API_URL = "https://router.huggingface.co/hf-inference/models/openai/whisper-large-v3-turbo"
CHAT_API_URL = "https://router.huggingface.co/sambanova/v1/chat/completions"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 سلام! خوش آمدید.\n"
        "🔹 برای کار با هوش مصنوعی، هر متنی بفرستید و منتظر پاسخ بمانید."
    )

def speech_to_text_api(audio_bytes: bytes) -> str:
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "audio/wav"
    }

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ogg_file:
        ogg_file.write(audio_bytes)
        ogg_path = ogg_file.name

    wav_path = ogg_path.replace(".ogg", ".wav")
    
    subprocess.run([
        "ffmpeg", "-y",
        "-i", ogg_path,
        "-ar", "16000",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        wav_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    with open(wav_path, "rb") as wav_file:
        resp = requests.post(WHISPER_API_URL, headers=headers, data=wav_file, timeout=60)
    
    os.remove(ogg_path)
    os.remove(wav_path)
    
    resp.raise_for_status()
    return resp.json().get("text", "")

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = await update.message.voice.get_file()
    bio = await voice.download_as_bytearray()
    await update.message.reply_text("⏳ در حال پردازش ویس...")

    try:
        loop = asyncio.get_running_loop()
        transcribed_text = await loop.run_in_executor(
            None,
            lambda: speech_to_text_api(bytes(bio))
        )

        if not transcribed_text or not transcribed_text.strip():
            await update.message.reply_text("❌ متنی از صدا استخراج نشد.")
            return

        # مرحله دوم: ارسال متن به مدل چت
        await update.message.reply_text("🤖 در حال دریافت پاسخ از AI...")

        payload = {
            "model": "DeepSeek-R1",
            "messages": [{"role": "user", "content": transcribed_text}]
        }
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}

        response = requests.post(CHAT_API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                raw_reply = data["choices"][0]["message"]["content"]
                cleaned_reply = re.sub(r"<think>.*?</think>", "", raw_reply, flags=re.DOTALL).strip()
                await update.message.reply_text(cleaned_reply if cleaned_reply else "❗ مدل پاسخی نداد.")
            else:
                await update.message.reply_text("❌ پاسخ نامعتبر از مدل دریافت شد.")
        else:
            await update.message.reply_text(f"❌ خطا در ارتباط با API: کد {response.status_code}")

    except Exception as e:
        logging.error("Error in voice_handler", exc_info=e)
        await update.message.reply_text(f"⚠️ خطا در پردازش ویس یا دریافت پاسخ:\n{e}")


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    if user_message.startswith('/'):
        return
    
    if len(user_message) > 300:
        await update.message.reply_text("❗ پیام خیلی طولانی است، لطفاً خلاصه‌تر بنویسید.")
        return

    await update.message.reply_text("⏳ در حال دریافت پاسخ...")

    payload = {
        "model": "DeepSeek-R1",
        "messages": [{"role": "user", "content": user_message}]
    }

    headers = {"Authorization": f"Bearer {HF_TOKEN}"}

    try:
        response = requests.post(CHAT_API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                raw_reply = data["choices"][0]["message"]["content"]
                cleaned_reply = re.sub(r"<think>.*?</think>", "", raw_reply, flags=re.DOTALL).strip()
                await update.message.reply_text(cleaned_reply if cleaned_reply else "❗ مدل پاسخی نداد.")
            else:
                await update.message.reply_text("❌ پاسخ نامعتبر از مدل دریافت شد.")
        else:
            await update.message.reply_text(f"❌ خطا در ارتباط با API: کد {response.status_code}")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در پردازش پیام: {str(e)}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    logging.info("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()