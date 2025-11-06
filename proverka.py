from telegram.ext import (Application,
                          MessageHandler,
                          filters,
                          ContextTypes,
                          ConversationHandler,
                          CommandHandler,
                          CallbackQueryHandler,
                          JobQueue)
from telegram import (Update,
                      InlineKeyboardButton,
                      InlineKeyboardMarkup)
import logging
import random
import json
import atexit

DATA_FILE = "bot_data.json"

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

BOT_TOKEN = '8380364649:AAGwWL-TWrUFHbBqqIarApdzLEtcDqY2BKo'
OWNER_ID = 5210424158

ASKING_NAME = 1

# Ключи в bot_data
CORRECT_ANSWER_KEY = "correct_answer"
AWARDED_USERS_KEY = "awarded_users"
SCOREBOARD_KEY = "scoreboard"
USER_NAMES_KEY = "user_names"
KNOWN_USERS_KEY = "known_users"
GRANTEES_KEY = "answer_grantees"

QUIZ_QUESTION_KEY = "quiz_question"      # текст вопроса
QUIZ_OPTIONS_KEY = "quiz_options"        # список из 4 строк
QUIZ_CORRECT_INDEX_KEY = "quiz_correct_index"  # индекс правильного (0–3)
QUIZ_POINTS_KEY = "quiz_points"          # сколько баллов
QUIZ_TRIED_USERS_KEY = "quiz_tried_users" # set(user_id) — кто уже отвечал


def pluralize(n):
    if n % 10 == 1 and n % 100 != 11:
        return "балл"
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return "балла"
    else:
        return "баллов"
#============================================ЗГРУЗКА И ВЫГРУЗКА БАЗЫ ДАННЫХ=============================================

# сохранение базы
def save_data(bot_data):
    """Сохраняет bot_data в JSON-файл"""
    # Преобразуем set в list (JSON не поддерживает set)
    data_to_save = {}
    for key, value in bot_data.items():
        if isinstance(value, set):
            data_to_save[key] = list(value)
        elif isinstance(value, dict):
            # Для словарей проверим значения
            cleaned_dict = {}
            for k, v in value.items():
                # Ключи-ID могут быть int, но JSON требует str
                cleaned_dict[str(k)] = v
            data_to_save[key] = cleaned_dict
        else:
            data_to_save[key] = value

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    logging.info("✅ Данные сохранены в файл")

# выгрузка базы
def load_data(bot_data):
    """Загружает данные из JSON-файла в bot_data"""
    if not os.path.exists(DATA_FILE):
        logging.info("📁 Файл данных не найден. Создан новый.")
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Восстанавливаем set из list
        for key, value in data.items():
            if key in [
                "awarded_users", "known_users", "ready_users",
                "quiz_tried_users", "answer_grantees"
            ]:
                bot_data[key] = set(value)
            elif key in [
                "scoreboard", "user_names"
            ]:
                # Преобразуем ключи обратно в int (user_id)
                bot_data[key] = {int(k): v for k, v in value.items()}
            else:
                bot_data[key] = value

        logging.info("✅ Данные загружены из файла")
    except Exception as e:
        logging.error(f"❌ Ошибка при загрузке данных: {e}")

# автосохранения на случаи аварийно отключения
async def periodic_save(context: ContextTypes.DEFAULT_TYPE):
    save_data(context.application.bot_data)

#==================================================ТЕХНИЧЕСКИЕ ФУНКЦИИ==================================================

# логирование пользователей
async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    full_command = update.message.text
    logging.info(f"📥 Команда: {full_command} | Пользователь: {user.full_name} (ID: {user.id})")
    # Возвращаем None, чтобы обработка продолжилась дальше
    return None

# подушка безопасности
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Оке, в другой раз")
    return ConversationHandler.END

#===================================================ЗНАКОМСТВО С БОТОМ==================================================

# функция старта и запроса имени пользователя
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if USER_NAMES_KEY not in context.bot_data:
        context.bot_data[USER_NAMES_KEY] = {}

    if user_id in context.bot_data[USER_NAMES_KEY]:
        name = context.bot_data[USER_NAMES_KEY][user_id]
        await update.message.reply_text(f"{name}! \nс возращением родной 🥳")
        return ConversationHandler.END

    await update.message.reply_text("введи имя:")
    return ASKING_NAME

# регестрация пользователя и краткий инструктаж
async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    custom_name = update.message.text.strip()

    if USER_NAMES_KEY not in context.bot_data:
        context.bot_data[USER_NAMES_KEY] = {}
    context.bot_data[USER_NAMES_KEY][user_id] = custom_name

    await update.message.reply_text(f"бро «{custom_name}». зареган 😎 \n\n"
                                    f"краткий тутор пользования: \n"
                                    f"1. за каждый правильный ответ ты получаешь баллы💫\n"
                                    f"2. ты можешь получить только 1 раз за 1 задачу 🔐\n"
                                    f"3. как только сменится задача — придет уведомление 🛎\n\n"
                                    f"команды:\n"
                                    f"/setname <новое имя> - сменить имя 🔁\n"
                                    f"/leaderboard - показать таблицу балов 📊\n"
                                    f"остальные команды желательно не трогать 👿")
    await update.message.reply_text("как будешь готов — напиши любое текстовое сообщение, например: «готов», «понял» или что-то своё 💬")
    return ConversationHandler.END

#================================================ФУНКЦИИ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ==============================================

# изменить имя
async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /setname <ваше имя>")
        return

    new_name = " ".join(context.args).strip()
    if len(new_name) > 50:
        await update.message.reply_text("Имя слишком длинное (макс. 50 символов).")
        return

    user_id = update.effective_user.id
    if USER_NAMES_KEY not in context.bot_data:
        context.bot_data[USER_NAMES_KEY] = {}
    context.bot_data[USER_NAMES_KEY][user_id] = new_name
    await update.message.reply_text(f"имя изменено, «{new_name}» 😇")

# таблица лидеров
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scoreboard = context.bot_data.get(SCOREBOARD_KEY, {})
    user_names = context.bot_data.get(USER_NAMES_KEY, {})

    if not scoreboard:
        await update.message.reply_text("Никто пока не заработал баллы 😢")
        return

    sorted_users = sorted(scoreboard.items(), key=lambda x: x[1], reverse=True)
    top_list = []
    for i, (user_id, score) in enumerate(sorted_users, 1):
        if user_id in user_names:
            display_name = user_names[user_id]
        else:
            try:
                user = await context.bot.get_chat(user_id)
                display_name = user.full_name or f"ID {user_id}"
            except:
                display_name = f"ID {user_id}"
        top_list.append(f"{i}. {display_name} — {score} ✨")

    await update.message.reply_text("топ учеников:\n" + "\n".join(top_list))

#===================================================ФУНКЦИИ ДЛЯ ОВНЕРА==================================================

# занести ответ
async def set_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data[CORRECT_ANSWER_KEY] = None
    context.bot_data[AWARDED_USERS_KEY] = set()
    context.bot_data.pop(QUIZ_QUESTION_KEY, None)
    context.bot_data.pop(QUIZ_TRIED_USERS_KEY, None)
    user_id = update.effective_user.id
    grantees = context.bot_data.get(GRANTEES_KEY, set())
    if user_id != OWNER_ID and user_id not in grantees:
        await update.message.reply_text("⚜️а ну ка цыц! это не кнопка не для тебя⚜️")
        return

    context.bot_data[CORRECT_ANSWER_KEY] = None
    context.bot_data[AWARDED_USERS_KEY] = set()

    if not context.args:
        await update.message.reply_text("🔯 Ответ сброшен.")
        return

    args = context.args
    answer_parts = args
    points = 1

    if len(args) >= 2 and args[-1].isdigit():
        points = int(args[-1])
        answer_parts = args[:-1]

    correct = " ".join(answer_parts).strip()
    if not correct:
        await update.message.reply_text("❌ Ответ не может быть пустым.")
        return

    context.bot_data[CORRECT_ANSWER_KEY] = correct.lower()
    context.bot_data["current_answer_points"] = points

    await update.message.reply_text(
        f"🔯 Ответ установлен: «{correct}»\n"
        f"💰 Награда: {points} {pluralize(points)}"
    )

    known_users = context.bot_data.get(KNOWN_USERS_KEY, set())
    notified = 0
    failed = 0
    for user_id in known_users:
        if user_id == OWNER_ID:
            continue
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🔔 новая задача! принимаю новые ответы 🔯\n"
                     f"💰 Награда: {points} {pluralize(points)}"
            )
            notified += 1
        except Exception as e:
            logging.warning(f"Не удалось отправить {user_id}: {e}")
            failed += 1

    logging.info(f"Уведомление отправлено {notified} пользователям, {failed} ошибок.")

# количество готовых игроков
async def show_ready_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Только владелец может видеть статистику.")
        return

    ready_users = context.bot_data.get(KNOWN_USERS_KEY, set())
    total_ready = len(ready_users)
    await update.message.reply_text(f"👥 Готовых пользователей: {total_ready}")

async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ПОЛНАЯ очистка всех данных бота (всё сносится!)"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Только владелец может очищать базу данных.")
        return

    # Требуем подтверждение
    if not context.args or context.args[0] != "confirm":
        await update.message.reply_text(
            "⚠️ ВНИМАНИЕ: это удалит ВСЁ — пользователей, баллы, модераторов, задания!\n"
            "Чтобы подтвердить, напишите: /clear confirm"
        )
        return

    # Полная очистка bot_data
    context.bot_data.clear()

    await update.message.reply_text("🔥 Вся база данных ОЧИЩЕНА! Бот сброшен к начальному состоянию.")
    logging.info(f"💥 ПОЛНАЯ ОЧИСТКА БАЗЫ ВЫПОЛНЕНА владельцем {OWNER_ID}")

#=======================================================ВИКТОРИНА=======================================================

# создать викторину
async def set_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    grantees = context.bot_data.get(GRANTEES_KEY, set())
    if user_id != OWNER_ID and user_id not in grantees:
        await update.message.reply_text("⚜️а ну ка цыц! это не кнопка не для тебя⚜️")
        return

    if len(context.args) < 5:
        await update.message.reply_text(
            "Использование: /quiz <вопрос> / <правильный> / <ложный1> / <ложный2> / <ложный3> [баллы]\n"
            "❗ Первый вариант после вопроса — ПРАВИЛЬНЫЙ!"
        )
        return

    try:
        full_text = " ".join(context.args)
        parts = full_text.split(" / ")
        if len(parts) < 5:
            raise ValueError("Нужно минимум 5 частей")

        question = parts[0].strip()
        correct_answer = parts[1].strip()
        fake_answers = [opt.strip() for opt in parts[2:5]]
        points = int(parts[5]) if len(parts) >= 6 and parts[5].isdigit() else 1
    except Exception as e:
        await update.message.reply_text("❌ Неверный формат. Пример:\n/quiz Сколько будет 2+2? / 4 / 5 / 3 / 6 2")
        return

    # === РАНДОМИЗАЦИЯ ===
    all_options = [correct_answer] + fake_answers
    random.shuffle(all_options)
    correct_index = all_options.index(correct_answer)

    # Сохраняем
    context.bot_data[QUIZ_QUESTION_KEY] = question
    context.bot_data[QUIZ_OPTIONS_KEY] = all_options
    context.bot_data[QUIZ_CORRECT_INDEX_KEY] = correct_index
    context.bot_data[QUIZ_POINTS_KEY] = points
    context.bot_data[QUIZ_TRIED_USERS_KEY] = set()

    # Кнопки
    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"quiz_{i}")]
        for i, opt in enumerate(all_options)
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    # Рассылка
    known_users = context.bot_data.get(KNOWN_USERS_KEY, set())
    grantees = context.bot_data.get(GRANTEES_KEY, set())
    notified = 0
    for uid in known_users:
        if uid == OWNER_ID or uid in grantees:
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"🧠 Викторина!\n\n{question}",
                reply_markup=keyboard
            )
            notified += 1
        except Exception as e:
            logging.warning(f"Не удалось отправить викторину {uid}: {e}")

    await update.message.reply_text(f"✅ Викторина отправлена {notified} пользователям!")

# удержание и действие с кнопками
async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Убираем "часики"
    user = update.effective_user

    # Проверяем, есть ли активный вопрос
    if QUIZ_QUESTION_KEY not in context.bot_data:
        await query.edit_message_text("❌ Эта викторина уже завершена.")
        return

    # Проверяем, отвечал ли уже
    tried_users = context.bot_data.get(QUIZ_TRIED_USERS_KEY, set())
    if user.id in tried_users:
        await query.edit_message_text("🔒 Ты уже отвечал на этот вопрос!")
        return

    # Добавляем в попытки
    tried_users.add(user.id)
    context.bot_data[QUIZ_TRIED_USERS_KEY] = tried_users

    # Разбираем callback_data
    try:
        selected_index = int(query.data.split("_")[1])
    except:
        await query.edit_message_text("❌ Ошибка выбора.")
        return

    correct_index = context.bot_data[QUIZ_CORRECT_INDEX_KEY]
    points = context.bot_data.get(QUIZ_POINTS_KEY, 1)
    options = context.bot_data[QUIZ_OPTIONS_KEY]

    # Начисление баллов
    if SCOREBOARD_KEY not in context.bot_data:
        context.bot_data[SCOREBOARD_KEY] = {}

    if selected_index == correct_index:
        context.bot_data[SCOREBOARD_KEY][user.id] = context.bot_data[SCOREBOARD_KEY].get(user.id, 0) + points
        result_text = f"✅ Верно! +{points} {pluralize(points)}"
        # Уведомление владельцу
        try:
            await context.bot.send_message(OWNER_ID, f"✅ {user.full_name} угадал викторину!")
        except:
            pass
    else:
        correct_answer = options[correct_index]
        result_text = f"❌ Неверно."

    # Обновляем сообщение
    await query.edit_message_text(
        text=f"🧠 {context.bot_data[QUIZ_QUESTION_KEY]}\n\n{result_text}",
        parse_mode="Markdown"
    )

#==================================================РАБОТА С МОДЕРАЦИЕЙ==================================================

# назначение модера
async def grant_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Только владелец может выдавать доступ.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Использование: /grant <user_id>")
        return

    target_id = int(context.args[0])
    if GRANTEES_KEY not in context.bot_data:
        context.bot_data[GRANTEES_KEY] = set()
    context.bot_data[GRANTEES_KEY].add(target_id)

    await update.message.reply_text(f"✅ Пользователю {target_id} выдан доступ к /answer.")

# изъятие модера
async def revoke_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Только владелец может забирать доступ.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Использование: /revoke <user_id>")
        return

    target_id = int(context.args[0])
    grantees = context.bot_data.get(GRANTEES_KEY, set())
    if target_id in grantees:
        grantees.discard(target_id)
        context.bot_data[GRANTEES_KEY] = grantees
        await update.message.reply_text(f"❌ У пользователя {target_id} отобран доступ к /answer.")
    else:
        await update.message.reply_text(f"⚠️ Пользователь {target_id} не имел доступа.")

# просмотр списка модеров
async def list_grantees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Только владелец может просматривать список.")
        return

    grantees = context.bot_data.get(GRANTEES_KEY, set())
    if not grantees:
        await update.message.reply_text("🔓 Никому пока не выдан доступ к /answer.")
    else:
        grantees_list = "\n".join(str(uid) for uid in sorted(grantees))
        await update.message.reply_text(f"👥 Доверенные пользователи (/answer):\n{grantees_list}")

#==========================================УДЕРЖАНИЕ И ДЕЙСТВИЕ С СООБЩЕНИЯМИ===========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    text = message.text or "[не текст]"

    if KNOWN_USERS_KEY not in context.bot_data:
        context.bot_data[KNOWN_USERS_KEY] = set()
    context.bot_data[KNOWN_USERS_KEY].add(user.id)
    if SCOREBOARD_KEY not in context.bot_data:
        context.bot_data[SCOREBOARD_KEY] = {}
    if AWARDED_USERS_KEY not in context.bot_data:
        context.bot_data[AWARDED_USERS_KEY] = set()

    if user.id == OWNER_ID:
        if message.reply_to_message:
            original_text = message.reply_to_message.text or ""
            try:
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
            await message.reply_text("ℹ️ Чтобы ответить пользователю — нажмите «Ответить» на его сообщение.")
        return

    correct = context.bot_data.get(CORRECT_ANSWER_KEY)
    awarded_users = context.bot_data[AWARDED_USERS_KEY]
    scoreboard = context.bot_data[SCOREBOARD_KEY]

    if correct and text.strip().lower() == correct:
        if user.id not in awarded_users:
            points = context.bot_data.get("current_answer_points", 1)
            awarded_users.add(user.id)
            scoreboard[user.id] = scoreboard.get(user.id, 0) + points
            await update.message.reply_text("✅")
            try:
                await context.bot.send_message(chat_id=OWNER_ID, text="✅")
            except Exception as e:
                logging.error(f"Не удалось отправить владельцу: {e}")
        else:
            pass

    user_names = context.bot_data.get(USER_NAMES_KEY, {})
    custom_name = user_names.get(user.id)
    display_name = custom_name if custom_name else user.full_name

    info = (
        f"Имя: {display_name} {'(кастом)' if custom_name else ''}\n"
        f"ID: {user.id}\n"
        f"---\n"
        f"{text}"
    )
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=info)
    except Exception as e:
        logging.error(f"Не удалось отправить владельцу: {e}")

def main():
    print("✅ Бот запущен!")

    app = Application.builder().token(BOT_TOKEN).build()

    # 👇 ЛОГИРОВАНИЕ КОМАНД — САМЫЙ ПЕРВЫЙ ОБРАБОТЧИК
    app.add_handler(MessageHandler(filters.COMMAND, log_command), group=-1)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASKING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    load_data(app.bot_data)
    app.job_queue.run_repeating(periodic_save, interval=300, first=300)
    atexit.register(save_data, app.bot_data)
    app.add_handler(CommandHandler("set_name", set_name))
    app.add_handler(CommandHandler("answer", set_answer))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("grant", grant_access))
    app.add_handler(CommandHandler("revoke", revoke_access))
    app.add_handler(CommandHandler("grantees", list_grantees))
    app.add_handler(CommandHandler("quiz", set_quiz))
    app.add_handler(CommandHandler("ready", show_ready_count))
    app.add_handler(CommandHandler("clear", clear_data))
    app.add_handler(CallbackQueryHandler(handle_quiz_answer))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
