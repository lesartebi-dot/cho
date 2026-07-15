from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# Тексты кнопок нижнего меню — используются и для построения клавиатуры,
# и как триггеры в bot.py (F.text == BTN_SERVICES и т.д.)
BTN_SERVICES = "💇 Услуги и цены"
BTN_MASTERS = "👩‍🎨 Мастера"
BTN_PORTFOLIO = "📸 Портфолио"
BTN_FAQ = "❓ Частые вопросы"
BTN_BOOK = "📅 Записаться"
BTN_CONTACTS = "📍 Контакты"


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SERVICES), KeyboardButton(text=BTN_MASTERS)],
            [KeyboardButton(text=BTN_PORTFOLIO), KeyboardButton(text=BTN_FAQ)],
            [KeyboardButton(text=BTN_BOOK), KeyboardButton(text=BTN_CONTACTS)],
        ],
        resize_keyboard=True
    )


def services_inline_kb(config: dict) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📅 {s['name']}", callback_data=f"book_service:{i}")]
        for i, s in enumerate(config["products"])
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def masters_inline_kb(config: dict) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📸 Работы {m['name']}", callback_data=f"portfolio:{m['name']}")]
        for m in config.get("masters", [])
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def portfolio_inline_kb(config: dict) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=key, callback_data=f"portfolio:{key}")]
        for key in config.get("portfolio", {})
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faq_inline_kb(config: dict) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f["q"], callback_data=f"faq:{i}")]
        for i, f in enumerate(config["faq"])
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
