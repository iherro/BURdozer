from telegram.ext import Application, MessageHandler, filters, ContextTypes, ConversationHandler, CommandHandler
from telegram import Update
import logging
import os

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
if not BOT_TOKEN or not OWNER_ID:
    raise ValueError("❌ BOT_TOKEN и OWNER_ID обязательны!")

ASKING_NAME = 1

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Оке, в другой раз")
    return ConversationHandler.END
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if 'custom_name' in context.user_data:
        name = context.user_data['custom_name']
        await update.message.reply_text(f"{name}! \n с возращением родной")
        return ConversationHandler.END

    await update.message.reply_text("Имя сюда клацать:")
    return ASKING_NAME
async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    custom_name = update.message.text.strip()
    context.user_data['custom_name'] = custom_name
    await update.message.reply_text(f"бро «{custom_name}». зареган ")
    return ConversationHandler.END
#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /setname <ваше имя>")
        return

    new_name = " ".join(context.args).strip()
    if len(new_name) > 50:
        await update.message.reply_text("Имя слишком длинное (макс. 50 символов).")
        return

    context.user_data['custom_name'] = new_name
    await update.message.reply_text(f"бро «{new_name}» зареган ✅.")
async def set_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("а ну ка цыц! ты явно не Артём, я это для него кнопка")
        return
    if not context.args:
        context.bot_data["correct_answer"] = None
        await update.message.reply_text("✅ Ответ сброшен.")
        return
    correct = " ".join(context.args).strip()
    context.bot_data["correct_answer"] = correct.lower()
    await update.message.reply_text(f"✅ Ответ установлен: «{correct}»")
#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    text = message.text or "[не текст]"

    # проверка я ли это
    if user.id == OWNER_ID:
        # проверка ответ ли это
        if message.reply_to_message:
            original_text = message.reply_to_message.text or ""
            try:
                # поиск ID
                for line in original_text.split("\n"):
                    if line.startswith("ID: "):
                        target_id = int(line.split("ID: ")[1].strip())
                        await context.bot.send_message(chat_id=target_id, text=text)
                        await message.reply_text("✅ Ответ отправлен!")
                        return
                raise ValueError("ID not found")
            except (ValueError, IndexError):
                await message.reply_text("❌ Не удалось определить получателя. Ответьте на сообщение от бота.")
        else:
            # Владелец пишет без ответа — можно игнорировать или отправить себе
            await message.reply_text("ℹ️ Чтобы ответить пользователю — нажмите «Ответить» на его сообщение.")
        return

    correct = context.bot_data.get("correct_answer")

    if text.strip().lower() == correct:
        # ✅ Пользователю
        await update.message.reply_text("✅")

        # ✅ Владельцу
        username = f"@{user.username}" if user.username else f"ID {user.id}"
        full_name = f"{user.first_name} {user.last_name or ''}".strip()
        msg_for_owner = (
            f"✅\n"
            f"Имя: {full_name}\n"
            f"Username: {username}\n"
        )
        try:
            await context.bot.send_message(chat_id=OWNER_ID, text=msg_for_owner)
        except Exception as e:
            logging.error(f"Не удалось отправить владельцу: {e}")

    info = (
        f"Имя: {user.full_name}\n"
        f"ID: {user.id}\n"
        f"---\n"
        f"{text}"
    )
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=info)
    except Exception as e:
        print(f"Не удалось отправить владельцу: {e}")

def main():
    print("✅ Бот запущен!")

    app = Application.builder().token(BOT_TOKEN).build()

    # Обработчики
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASKING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("setname", setname))
    app.add_handler(CommandHandler("answer", set_answer))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()

