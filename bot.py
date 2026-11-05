import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)
from openai import OpenAI

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "ТОКЕН_ОТ_BOTFATHER"

# --- Твой шлюз reformboss ---
BASE_URL = "https://api.reformboss.com/v1"
API_KEY  = "sk-6ca46564cca5dc7ddff1c978dc426f6ce044876a2f85645c"
MODEL    = "deepseek-v4.1-flash"   # ← замени на модель из твоей панели

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

logging.basicConfig(level=logging.INFO)

SYSTEM_PROMPT = """Ты — дружелюбный техспециалист поддержки. Помогаешь подключить
фрагмент кода к проекту. Объясняй пошагово, нумерованными пунктами, с командами
и примерами кода. Предупреждай о частых ошибках. Кратко, но полно (до 1500 символов).
В конце спрашивай: "Получилось? Если нет — напиши ошибку"."""

# ================= ИИ =================
def ask_ai(messages):
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=1200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Ошибка API: {e}"

# ================= СОСТОЯНИЯ =================
ASK_PROJECT, ASK_FRAGMENT, FOLLOWUP = range(3)
user_data = {}

def build_messages(uid):
    d = user_data.setdefault(uid, {"history": []})
    return [{"role": "system", "content": SYSTEM_PROMPT}] + d["history"][-10:]

def save(uid, role, content):
    d = user_data.setdefault(uid, {"history": []})
    d["history"].append({"role": role, "content": content})
    d["history"] = d["history"][-10:]

# ================= ДИАЛОГ =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid] = {"history": []}
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👋\n\n"
        "Помогу подключить фрагмент кода к проекту.\n\n"
        "❓ *Вопрос 1:* Что за проект?\n"
        "_(Telegram-бот на Python, сайт на React, скрипт на Node.js...)_",
        parse_mode="Markdown",
    )
    return ASK_PROJECT

async def got_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data.setdefault(uid, {"history": []})["project"] = update.message.text
    await update.message.reply_text(
        "Отлично! 📝\n\n❓ *Вопрос 2:* Опиши фрагмент — что делает?\n"
        "_(можно вставить код или ссылку)_",
        parse_mode="Markdown",
    )
    return ASK_FRAGMENT

async def got_fragment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    d = user_data.setdefault(uid, {"history": []})
    d["fragment"] = update.message.text

    prompt = (
        f"Проект: {d.get('project')}\n"
        f"Фрагмент: {d.get('fragment')}\n\n"
        "Дай пошаговую инструкцию: 1) что установить, 2) куда положить, "
        "3) что дописать, 4) как проверить, 5) частые ошибки."
    )
    save(uid, "user", prompt)

    thinking = await update.message.reply_text("🤔 Готовлю инструкцию...")
    answer = ask_ai(build_messages(uid))
    save(uid, "assistant", answer)
    await thinking.edit_text(answer[:4000])
    await update.message.reply_text(
        "Готово ✅ Если ошибка — напиши сюда. Заново — /start"
    )
    return FOLLOWUP

async def followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    save(uid, "user", update.message.text)
    thinking = await update.message.reply_text("🤔 Думаю...")
    answer = ask_ai(build_messages(uid))
    save(uid, "assistant", answer)
    await thinking.edit_text(answer[:4000])
    return FOLLOWUP

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data.pop(update.effective_user.id, None)
    await update.message.reply_text("Ок, отменил. /start — заново")
    return ConversationHandler.END

# ================= ЗАПУСК =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_PROJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_project)],
            ASK_FRAGMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_fragment)],
            FOLLOWUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, followup)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    print("✅ Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()