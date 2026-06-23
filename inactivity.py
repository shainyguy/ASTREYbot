"""Проверка неактивности пользователей — оповещение админа, если клиент молчит >5 мин."""
import asyncio
import logging
from datetime import datetime, timedelta

import aiosqlite
import config
import database as db
import notifier
from config import DATABASE_PATH, ADMIN_IDS

logger = logging.getLogger(__name__)

_INACTIVITY_MINUTES = 5
_CHECK_INTERVAL = 60  # Проверяем каждые 60 секунд


async def run_inactivity_monitor():
    """Фоновая задача: проверяет users с last_bot_message_at > 5 мин назад."""
    while True:
        try:
            await _check_inactive_users()
        except Exception as e:
            logger.error(f"Inactivity monitor error: {e}")
        await asyncio.sleep(_CHECK_INTERVAL)


async def _check_inactive_users():
    cutoff = (datetime.utcnow() - timedelta(minutes=_INACTIVITY_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DATABASE_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute(
            """SELECT telegram_id, full_name, username, first_name, last_bot_message_at
               FROM users
               WHERE last_bot_message_at IS NOT NULL
                 AND last_bot_message_at <= ?
                 AND stage NOT IN ('manager_takeover', 'completed')
                 AND inactivity_notified = 0""",
            (cutoff,)
        ) as c:
            rows = await c.fetchall()

    for row in rows:
        uid = row["telegram_id"]
        name = row["full_name"] or row["first_name"] or row["username"] or f"ID:{uid}"
        username = row["username"] or ""

        # Определяем платформу по ID (отрицательный = VK)
        platform = "VK" if uid < 0 else "Telegram"
        profile_link = f"vk.com/id{abs(uid)}" if uid < 0 else f"tg://user?id={uid}"
        admin_link = f"🔗 {profile_link}" if uid < 0 else f"🔗 tg://user?id={uid}"

        text = (
            f"⏰ *Клиент не отвечает {_INACTIVITY_MINUTES}+ минут!*\n\n"
            f"👤 {name}"
            f"{' (@' + username + ')' if username else ''}\n"
            f"📱 Платформа: {platform}\n"
            f"{admin_link}\n\n"
            f"Возможно, нужно подключиться и уточнить, всё ли в порядке."
        )
        await notifier.notify_admins(ADMIN_IDS, text)

        # Отмечаем, что уже оповестили
        await db.update_user(uid, inactivity_notified=1)
        logger.info(f"Inactivity notified for {uid} ({name})")
