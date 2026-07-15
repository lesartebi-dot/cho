import asyncio
import logging

import db

log = logging.getLogger("clawtech_bot.reminders")

CHECK_INTERVAL_SECONDS = 60 * 15   # проверять раз в 15 минут
REMIND_AFTER_HOURS = 2             # напомнить о брошенной заявке через 2 часа
PRE_VISIT_REMIND_HOURS = 3         # напомнить о визите за 3 часа
REVIEW_REQUEST_AFTER_HOURS = 24    # запросить отзыв через сутки после визита


async def reminder_loop(bot, config: dict):
    shop_name = config["shop_name"]
    while True:
        await _remind_abandoned(bot, shop_name)
        await _remind_pre_visit(bot, shop_name)
        await _request_reviews(bot, shop_name)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def _remind_abandoned(bot, shop_name: str):
    """Напоминание о заявке, которую так и не подтвердил администратор."""
    try:
        pending = db.get_pending_orders_older_than(REMIND_AFTER_HOURS)
        for order in pending:
            try:
                await bot.send_message(
                    order["user_id"],
                    f"Здравствуйте! Напоминаем — вы оставляли заявку в «{shop_name}»:\n"
                    f"«{order['summary']}»\n\n"
                    f"Всё ещё актуально? Если нужно что-то изменить — просто напишите здесь."
                )
                db.mark_reminded(order["id"])
                log.info(f"Abandoned reminder sent for order {order['id']}")
            except Exception:
                log.exception(f"Failed to send abandoned reminder for order {order['id']}")
    except Exception:
        log.exception("Abandoned reminder loop error")


async def _remind_pre_visit(bot, shop_name: str):
    """Напоминание за N часов до подтверждённого визита."""
    try:
        upcoming = db.get_appointments_needing_pre_visit_reminder(PRE_VISIT_REMIND_HOURS)
        for order in upcoming:
            try:
                await bot.send_message(
                    order["user_id"],
                    f"Напоминаем: ждём вас в «{shop_name}» {order['appointment_at']}.\n"
                    f"Услуга: {order['summary']}\n\n"
                    f"Если планы изменились — напишите здесь, перенесём."
                )
                db.mark_pre_visit_reminded(order["id"])
                log.info(f"Pre-visit reminder sent for order {order['id']}")
            except Exception:
                log.exception(f"Failed to send pre-visit reminder for order {order['id']}")
    except Exception:
        log.exception("Pre-visit reminder loop error")


async def _request_reviews(bot, shop_name: str):
    """Запрос отзыва через сутки после визита."""
    try:
        past = db.get_appointments_needing_review(REVIEW_REQUEST_AFTER_HOURS)
        for order in past:
            try:
                await bot.send_message(
                    order["user_id"],
                    f"Как вам результат в «{shop_name}»? Будем очень рады отзыву — "
                    f"пара слов и/или фото здесь в чате. Это помогает нам и будущим клиентам 🙂"
                )
                db.mark_review_requested(order["id"])
                log.info(f"Review request sent for order {order['id']}")
            except Exception:
                log.exception(f"Failed to send review request for order {order['id']}")
    except Exception:
        log.exception("Review request loop error")
