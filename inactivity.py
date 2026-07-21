"""Проверка неактивности пользователей — оповещение админа и возврат брошенных."""
import asyncio
import logging
from datetime import datetime, timedelta

import database as db
import notifier
import keyboards as kb
import messages as msg
import takeover
from config import ADMIN_IDS, WEBSITE_URL

logger = logging.getLogger(__name__)

_INACTIVITY_MINUTES = 5
_CHECK_INTERVAL = 60

# Отслеживание отправленных напоминаний (in-memory, сбрасывается при рестарте)
_sent_1h: set[int] = set()
_sent_24h: set[int] = set()


async def run_inactivity_monitor():
    while True:
        try:
            await _check_inactive_users()
        except Exception as e:
            logger.error(f"Inactivity monitor error: {e}")
        await asyncio.sleep(_CHECK_INTERVAL)


async def _check_inactive_users():
    d = db.get_db()
    if not d:
        return
    now_utc = datetime.utcnow()
    cutoff_5m = (now_utc - timedelta(minutes=_INACTIVITY_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_1h = (now_utc - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_24h = (now_utc - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    rows = await d.fetch_all(
        "SELECT telegram_id, full_name, username, first_name, last_bot_message_at, platform "
        "FROM users "
        "WHERE last_bot_message_at IS NOT NULL "
        "AND stage NOT IN ('manager_takeover', 'completed') "
        "AND inactivity_notified = 0 "
        "AND last_bot_message_at <= ?",
        {"1": cutoff_5m}
    )

    for row in rows:
        uid = row["telegram_id"]
        name = row["full_name"] or row["first_name"] or row["username"] or f"ID:{uid}"
        username = row["username"] or ""

        platform = "ВКонтакте" if uid < 0 else "Telegram"

        text = (
            f"⏰ *Клиент замолчал — {_INACTIVITY_MINUTES}+ минут тишины*\n\n"
            f"👤 {takeover.escape(name)}"
            f"{' (@' + username + ')' if username else ''}\n"
            f"📱 {platform}\n\n"
            f"Нажми «Взять в работу» — бот замолчит, и клиент получит "
            f"твои сообщения от имени АСТРЕЙ 👇"
        )
        # Кнопка обязательна: без неё уведомление бесполезно —
        # подключиться к диалогу было физически нечем
        markup = kb.kb_notify_admin(uid, username)
        for admin_id in ADMIN_IDS:
            await notifier.send_to_admin(admin_id, text, markup)
        await db.update_user(uid, inactivity_notified=1)
        logger.info(f"Inactivity notified for {uid} ({name})")

    # ── Возврат брошенных: 1 час ──
    await _send_abandoned_reminder(d, cutoff_1h, 3600, "1h", _sent_1h,
                                   msg.ABANDONED_1H)

    # ── Возврат брошенных: 24 часа ──
    await _send_abandoned_reminder(d, cutoff_24h, 86400, "24h", _sent_24h,
                                   msg.ABANDONED_24H)


async def _send_abandoned_reminder(d, cutoff, seconds, label, sent_set, text_template):
    now_utc = datetime.utcnow()
    rows = await d.fetch_all(
        "SELECT telegram_id, last_bot_message_at, platform "
        "FROM users "
        "WHERE last_bot_message_at IS NOT NULL "
        "AND last_bot_message_at <= ? "
        "AND stage NOT IN ('manager_takeover', 'completed') "
        "AND inactivity_notified = 1",
        {"1": cutoff}
    )

    for row in rows:
        uid = row["telegram_id"]
        if uid in sent_set:
            continue
        # Проверяем что прошло достаточно времени
        last_time = row["last_bot_message_at"]
        if last_time:
            try:
                last_dt = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")
                if (now_utc - last_dt).total_seconds() < seconds - 60:
                    continue
            except ValueError:
                continue

        sent_set.add(uid)
        text = text_template.format(url=WEBSITE_URL)

        # Через takeover: он сам выберет TG или ВК. Раньше проверка
        # platform == "telegram" отсекала всех ВК-клиентов — до них
        # напоминания не доходили вообще.
        ok, err = await takeover.send_to_user(uid, text)
        if ok:
            logger.info(f"Abandoned {label} reminder sent to {uid}")
        else:
            logger.error(f"Abandoned {label} send error for {uid}: {err}")