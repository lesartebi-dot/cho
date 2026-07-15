import os
import json
import asyncio
import logging
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.filters import CommandStart, Command

import db
import keyboards as kb
from grok_client import ask_grok
from reminders import reminder_loop

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("clawtech_bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ---------- /start ----------

@dp.message(CommandStart())
async def start_handler(message: Message):
    text = (
        f"Здравствуйте! Это чат-бот салона «{CONFIG['shop_name']}».\n"
        f"Режим работы: {CONFIG['working_hours']}\n\n"
        f"Выберите нужное в меню ниже 👇 или просто напишите вопрос словами — тоже отвечу."
    )
    await message.answer(text, reply_markup=kb.main_menu_kb())
    db.save_message(message.from_user.id, "assistant", text)


# ---------- Кнопки нижнего меню (быстрые, без обращения к Grok) ----------

@dp.message(F.text == kb.BTN_SERVICES)
async def services_handler(message: Message):
    text = "Наши услуги:\n\n" + "\n".join(
        f"• {s['name']} — {s['price']}" for s in CONFIG["products"]
    )
    await message.answer(text, reply_markup=kb.services_inline_kb(CONFIG))


@dp.message(F.text == kb.BTN_MASTERS)
async def masters_handler(message: Message):
    masters = CONFIG.get("masters", [])
    if not masters:
        await message.answer("Информация о мастерах пока не добавлена.")
        return
    text = "Наши мастера:\n\n" + "\n".join(
        f"• {m['name']} — {m.get('specialty', '')}" for m in masters
    )
    await message.answer(text, reply_markup=kb.masters_inline_kb(CONFIG))


@dp.message(F.text == kb.BTN_PORTFOLIO)
async def portfolio_menu_handler(message: Message):
    if not CONFIG.get("portfolio"):
        await message.answer("Портфолио пока не добавлено.")
        return
    await message.answer("Что хотите посмотреть?", reply_markup=kb.portfolio_inline_kb(CONFIG))


@dp.message(F.text == kb.BTN_FAQ)
async def faq_handler(message: Message):
    await message.answer("Частые вопросы — выберите:", reply_markup=kb.faq_inline_kb(CONFIG))


@dp.message(F.text == kb.BTN_CONTACTS)
async def contacts_handler(message: Message):
    text = (
        f"📍 {CONFIG['address']}\n"
        f"🕒 {CONFIG['working_hours']}\n\n"
        f"Есть вопрос — просто напишите его здесь."
    )
    await message.answer(text)


@dp.message(F.text == kb.BTN_BOOK)
async def book_handler(message: Message):
    await message.answer(
        "Выберите услугу из списка — и я оформлю запись:",
        reply_markup=kb.services_inline_kb(CONFIG)
    )


# ---------- Инлайн-кнопки (callback) ----------

@dp.callback_query(F.data.startswith("book_service:"))
async def cb_book_service(callback: CallbackQuery):
    idx = int(callback.data.split(":", 1)[1])
    service = CONFIG["products"][idx]
    await callback.answer()
    synthetic_text = f"Хочу записаться на «{service['name']}»"
    await process_user_text(
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        username=callback.from_user.username or callback.from_user.full_name,
        text=synthetic_text
    )


@dp.callback_query(F.data.startswith("portfolio:"))
async def cb_portfolio(callback: CallbackQuery):
    category = callback.data.split(":", 1)[1]
    await callback.answer()
    await send_portfolio(callback.message.chat.id, category)


@dp.callback_query(F.data.startswith("faq:"))
async def cb_faq(callback: CallbackQuery):
    idx = int(callback.data.split(":", 1)[1])
    item = CONFIG["faq"][idx]
    await callback.answer()
    await callback.message.answer(f"❓ {item['q']}\n\n{item['a']}")


# ---------- Свободный текст -> Grok ----------

@dp.message(F.text)
async def message_handler(message: Message):
    await process_user_text(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        username=message.from_user.username or message.from_user.full_name,
        text=message.text
    )


async def process_user_text(chat_id: int, user_id: int, username: str, text: str):
    """Общая логика: и обычные сообщения, и кнопки 'Записаться на X' идут через этот путь."""
    db.save_message(user_id, "user", text)
    history = db.get_history(user_id, limit=12)[:-1]  # без только что сохранённого

    try:
        reply_text, tool_calls = ask_grok(CONFIG, history, text)
    except Exception:
        log.exception("Grok API error")
        await bot.send_message(chat_id, "Секунду, небольшая техническая заминка — попробуйте написать ещё раз чуть позже.")
        return

    for call in tool_calls:
        if call["name"] == "save_order":
            summary = call["input"].get("summary", "")
            contact = call["input"].get("contact")
            appointment_at = call["input"].get("appointment_at") or None
            order_id = db.save_order(user_id, username, summary, contact, appointment_at)
            log.info(f"Order #{order_id} saved for user {user_id}: {summary}")

            admin_id = CONFIG.get("admin_chat_id")
            if admin_id:
                confirm_hint = (
                    f"\n\nЧтобы подтвердить точное время визита и включить напоминания, "
                    f"отправьте: /confirm {order_id} ГГГГ-ММ-ДД ЧЧ:ММ"
                )
                await bot.send_message(
                    admin_id,
                    f"🛒 Новая заявка #{order_id} от @{username} (id {user_id}):\n{summary}"
                    + (f"\nКонтакт: {contact}" if contact else "")
                    + (f"\nЖелаемое время: {appointment_at}" if appointment_at else "")
                    + confirm_hint
                )

        elif call["name"] == "escalate_to_human":
            reason = call["input"].get("reason", "")
            log.info(f"Escalation for user {user_id}: {reason}")

            admin_id = CONFIG.get("admin_chat_id")
            if admin_id:
                await bot.send_message(
                    admin_id,
                    f"🙋 Требуется человек в диалоге с @{username} (id {user_id}):\n{reason}"
                )

        elif call["name"] == "show_portfolio":
            category = call["input"].get("category", "")
            await send_portfolio(chat_id, category)

    if not reply_text:
        reply_text = "Передал ваш вопрос сотруднику, скоро с вами свяжутся."

    await bot.send_message(chat_id, reply_text)
    db.save_message(user_id, "assistant", reply_text)


async def send_portfolio(chat_id: int, category: str):
    portfolio = CONFIG.get("portfolio", {})
    # ищем категорию без учёта регистра, по частичному совпадению
    key = next((k for k in portfolio if k.lower() in category.lower() or category.lower() in k.lower()), None)

    if not key:
        await bot.send_message(chat_id, "Пока нет фото именно по этому запросу, но можем обсудить в общих чертах.")
        return

    photos = portfolio[key]
    files_sent = 0
    for path in photos:
        if os.path.exists(path):
            await bot.send_photo(chat_id, FSInputFile(path))
            files_sent += 1

    if files_sent == 0:
        await bot.send_message(chat_id, f"Фото по категории «{key}» пока не загружены в бота — уточните у администратора.")


# ---------- Админ ----------

@dp.message(Command("confirm"))
async def confirm_handler(message: Message):
    """Админская команда: /confirm <order_id> <YYYY-MM-DD HH:MM> — подтверждает точное время визита."""
    admin_id = CONFIG.get("admin_chat_id")
    if not admin_id or message.from_user.id != admin_id:
        return  # тихо игнорируем, если не админ

    parts = message.text.split(maxsplit=1)
    try:
        _, rest = parts
        order_id_str, dt_str = rest.split(" ", 1)
        order_id = int(order_id_str)
        datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M")
    except Exception:
        await message.answer("Формат: /confirm 5 2026-07-20 15:00")
        return

    order = db.get_order(order_id)
    if not order:
        await message.answer(f"Заявка #{order_id} не найдена.")
        return

    db.set_appointment(order_id, dt_str.strip())
    await message.answer(f"Заявка #{order_id} подтверждена на {dt_str.strip()}. Клиенту придёт напоминание перед визитом.")

    try:
        await bot.send_message(
            order["user_id"],
            f"Ваша запись подтверждена: {dt_str.strip()}. Ждём вас! Если планы изменятся — напишите здесь."
        )
    except Exception:
        log.exception(f"Failed to notify user about confirmed order {order_id}")


async def main():
    db.init_db()
    asyncio.create_task(reminder_loop(bot, CONFIG))
    log.info(f"Бот «{CONFIG['shop_name']}» запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
