"""Дожим клиентов, которые остановились на полпути.

Три сценария, где деньги утекают молча:
  1. Заказ собран, ссылка на оплату отправлена — но не оплачено
  2. Клиент бросил оформление на середине (застрял на вопросе)
  3. Макет отправлен, но клиент его не смотрит

Каждому заказу считаем nudge_level, чтобы после рестарта Railway не
начать дожимать заново по второму кругу.
"""
import asyncio
import logging
from datetime import datetime, timedelta

import database as db
import keyboards as kb
import messages as msg
import notifier
import takeover
from config import ADMIN_IDS, format_info

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 600  # раз в 10 минут

# Ступени дожима неоплаченного заказа: (уровень, часов прошло, текст)
PAYMENT_NUDGES = (
    (1, 2, "ORDER_NUDGE_2H"),
    (2, 24, "ORDER_NUDGE_24H"),
    (3, 72, "ORDER_NUDGE_72H"),
)

# Брошенное оформление: клиент в stage='ordering' и молчит
ORDERING_STALL_MINUTES = 30

# Макет отправлен, но клиент не отреагировал
MOCKUP_SILENT_HOURS = 12

_stall_nudged: set[int] = set()


async def run_nudges() -> None:
    logger.info("Дожим клиентов запущен")
    while True:
        try:
            await _check_unpaid_orders()
            await _check_stalled_ordering()
            await _check_silent_mockups()
        except Exception as e:
            logger.error(f"Ошибка дожима: {e}", exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL)


def _hours_since(value: str) -> float:
    """Сколько часов прошло. Большое число, если распарсить не удалось."""
    if not value:
        return 0.0
    raw = str(value).split(".")[0].replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return (datetime.utcnow() - datetime.strptime(raw, fmt)).total_seconds() / 3600
        except ValueError:
            continue
    return 0.0


# ─────────────────────────────────────────────
#  1. НЕОПЛАЧЕННЫЕ ЗАКАЗЫ
# ─────────────────────────────────────────────

async def _check_unpaid_orders() -> None:
    d = db.get_db()
    if not d:
        return

    rows = await d.fetch_all(
        "SELECT * FROM orders WHERE status = 'awaiting_payment' AND nudge_level < 3"
    )

    for order in rows:
        hours = _hours_since(order.get("created_at"))
        level = order.get("nudge_level") or 0

        target = None
        for lvl, need_hours, text_key in PAYMENT_NUDGES:
            if lvl > level and hours >= need_hours:
                target = (lvl, text_key)
        if not target:
            continue

        lvl, text_key = target
        uid = order["telegram_id"]
        fmt_name, price, pay_url = format_info(order.get("format", "electronic"))

        text = getattr(msg, text_key).format(
            format_name=fmt_name,
            amount=price,
            event_date=order.get("event_date") or "",
        )
        markup = kb.kb_order_pay(pay_url, order["id"]) if uid > 0 else None

        ok = await _deliver(uid, text, markup, pay_url)
        await db.update_order(order["id"], nudge_level=lvl)

        if ok:
            logger.info(f"Дожим оплаты #{order['id']} уровень {lvl} → {uid}")

        # На последней ступени зовём менеджера — дальше нужен человек
        if lvl == 3:
            name, source = await takeover.describe_user(uid)
            for admin_id in ADMIN_IDS:
                await notifier.send_to_admin(
                    admin_id,
                    f"💸 *Заказ #{order['id']} висит без оплаты 3 суток*\n\n"
                    f"👤 {takeover.escape(name)} {source}\n"
                    f"🎁 {fmt_name} — {price}₽\n\n"
                    f"Бот напомнил трижды. Дальше нужен ты 👇",
                    kb.kb_admin_order(order["id"], uid),
                )


# ─────────────────────────────────────────────
#  2. БРОШЕННОЕ ОФОРМЛЕНИЕ
# ─────────────────────────────────────────────

async def _check_stalled_ordering() -> None:
    d = db.get_db()
    if not d:
        return

    cutoff = (datetime.utcnow() - timedelta(minutes=ORDERING_STALL_MINUTES)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    rows = await d.fetch_all(
        "SELECT telegram_id, first_name, full_name FROM users "
        "WHERE stage = 'ordering' AND last_bot_message_at IS NOT NULL "
        "AND last_bot_message_at <= ?",
        {"1": cutoff},
    )

    for row in rows:
        uid = row["telegram_id"]
        if uid in _stall_nudged:
            continue
        _stall_nudged.add(uid)

        ok, _ = await takeover.send_to_user(uid, msg.ORDER_STALLED_NUDGE)
        if ok:
            logger.info(f"Дожим брошенного оформления → {uid}")


# ─────────────────────────────────────────────
#  3. МАКЕТ БЕЗ РЕАКЦИИ
# ─────────────────────────────────────────────

async def _check_silent_mockups() -> None:
    d = db.get_db()
    if not d:
        return

    rows = await d.fetch_all("SELECT * FROM orders WHERE status = 'mockup_sent'")
    for order in rows:
        if _hours_since(order.get("updated_at")) < MOCKUP_SILENT_HOURS:
            continue
        if (order.get("nudge_level") or 0) >= 10:  # 10+ = дожим по макету отправлен
            continue

        uid = order["telegram_id"]
        await db.update_order(order["id"], nudge_level=10)
        markup = kb.kb_mockup_review(order["id"]) if uid > 0 else None
        await _deliver(uid, msg.MOCKUP_SILENT_NUDGE, markup, None)
        logger.info(f"Дожим по макету #{order['id']} → {uid}")


# ─────────────────────────────────────────────

async def _deliver(uid: int, text: str, markup, pay_url: str) -> bool:
    """Telegram — с кнопками, ВК — текстом со ссылкой внутри."""
    if uid > 0 and markup is not None and notifier._bot:
        try:
            await notifier._bot.send_message(uid, text, reply_markup=markup,
                                             parse_mode="Markdown")
            return True
        except Exception as e:
            logger.error(f"Дожим → TG {uid}: {e}")
            return False

    if pay_url:
        text = f"{text}\n\n👉 {pay_url}"
    ok, _ = await takeover.send_to_user(uid, text)
    return ok
