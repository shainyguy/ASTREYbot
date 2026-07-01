"""Планировщик напоминаний — проверяет раз в час, отправляет за N дней до события."""
import asyncio
import logging
from datetime import date, datetime

import database as db
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

_bot = None  # Telegram Bot instance


def set_bot(bot) -> None:
    global _bot
    _bot = bot


def _parse_event_date(event_date: str) -> tuple[int, int] | None:
    """Возвращает (day, month). Поддерживает ДД.ММ и ДД.ММ.ГГГГ."""
    parts = event_date.strip().split(".")
    if len(parts) >= 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None
    return None


def _days_until(day: int, month: int, today: date) -> int:
    """Количество дней до ближайшего наступления даты."""
    try:
        target = date(today.year, month, day)
    except ValueError:
        return 999
    if target < today:
        try:
            target = date(today.year + 1, month, day)
        except ValueError:
            return 999
    return (target - today).days


GIFT_IDEAS = {
    "день рождения": (
        "🎂 *День рождения уже скоро!*\n\n"
        "У нас есть потрясающие идеи подарков:\n"
        "✨ Карта звёздного неба на дату рождения\n"
        "📜 Именная карта — с именем и пожеланием\n"
        "🎁 Подарочный набор с гравировкой\n\n"
        "👉 [Выбрать подарок на astreys.ru](https://astreys.ru)"
    ),
    "годовщина": (
        "💑 *Годовщина уже скоро!*\n\n"
        "Самые романтичные подарки:\n"
        "⭐ Карта звёздного неба на дату знакомства\n"
        "💌 Именная карта с вашей историей любви\n"
        "🌹 Персональный набор для двоих\n\n"
        "👉 [Выбрать подарок на astreys.ru](https://astreys.ru)"
    ),
    "свадьба": (
        "💍 *Свадьба уже скоро!*\n\n"
        "Незабываемые подарки молодожёнам:\n"
        "🌟 Карта звёздного неба на дату свадьбы\n"
        "📋 Именная карта «Наша история»\n"
        "🎊 Премиальный подарочный набор\n\n"
        "👉 [Выбрать подарок на astreys.ru](https://astreys.ru)"
    ),
}

_DEFAULT_GIFT_TEXT = (
    "🎁 *Важная дата уже скоро!*\n\n"
    "Не забудь про подарок 😊\n\n"
    "У нас на astreys.ru есть прекрасные варианты:\n"
    "⭐ Карта звёздного неба\n"
    "📜 Именная карта\n"
    "🎀 Персональный подарочный набор\n\n"
    "👉 [Выбрать подарок](https://astreys.ru)"
)


def _build_reminder_text(reminder: dict, days_left: int) -> str:
    event = reminder["event_name"]
    event_lower = event.lower()
    for key, text in GIFT_IDEAS.items():
        if key in event_lower:
            header = f"⏰ *Напоминание: {event}* — через {days_left} дн.!\n\n"
            return header + text.split("\n\n", 1)[1] if "\n\n" in text else text
    days_str = f"через {days_left} дн." if days_left > 0 else "сегодня!"
    return (
        f"⏰ *Напоминание!*\n\n"
        f"📅 Событие: *{event}*\n"
        f"📆 Дата: *{reminder['event_date']}*\n"
        f"🗓 Осталось: *{days_str}*\n\n"
        + _DEFAULT_GIFT_TEXT.split("🎁 *Важная дата уже скоро!*\n\n")[1]
    )


async def _check_and_send() -> None:
    if not _bot:
        return

    today = date.today()
    reminders = await db.get_active_reminders()

    for r in reminders:
        parsed = _parse_event_date(r["event_date"])
        if not parsed:
            continue
        day, month = parsed
        days_left = _days_until(day, month, today)

        if days_left != r["remind_days_before"]:
            continue

        # Проверяем — уже отправляли в этом году?
        year_str = str(today.year)
        reminded_years = r.get("reminded_years") or ""
        if year_str in reminded_years.split(","):
            continue

        telegram_id = r["telegram_id"]
        platform = r.get("platform", "telegram")
        text = _build_reminder_text(r, days_left)

        try:
            if platform == "telegram" and telegram_id > 0:
                await _bot.send_message(telegram_id, text, parse_mode="Markdown",
                                        disable_web_page_preview=True)
                await db.mark_reminder_sent(r["id"], today.year)
                logger.info(f"Reminder sent to TG user {telegram_id}: {r['event_name']}")
            elif platform == "vk":
                # VK напоминания пока логируем (отправка через notifier)
                import notifier
                vk_user_id = abs(telegram_id)  # VK ID хранится как отрицательный
                await notifier.notify_admins(
                    ADMIN_IDS,
                    f"⏰ Пользователю ВК [vk.com/id{vk_user_id}] пора напомнить о: "
                    f"*{r['event_name']}* ({r['event_date']})\n"
                    f"Осталось {days_left} дн."
                )
                await db.mark_reminder_sent(r["id"], today.year)
        except Exception as e:
            logger.error(f"Failed to send reminder {r['id']}: {e}")


async def run_reminder_scheduler() -> None:
    logger.info("Reminder scheduler started")
    while True:
        try:
            await _check_and_send()
        except Exception as e:
            logger.error(f"Reminder scheduler error: {e}")
        await asyncio.sleep(3600)  # проверяем раз в час
