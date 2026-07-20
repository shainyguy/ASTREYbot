"""Планировщик повторных касаний: через 3 дня после контакта без покупки."""
import asyncio
import logging
from datetime import datetime, timedelta

import database as db
import messages as msg
from config import ADMIN_IDS, WEBSITE_URL

logger = logging.getLogger(__name__)

_bot = None
_CHECK_INTERVAL = 3600  # раз в час
_reminded: set[int] = set()  # in-memory, сбрасывается при рестарте


def set_bot(bot) -> None:
    global _bot
    _bot = bot


async def run_followup():
    logger.info("Follow-up scheduler started")
    while True:
        try:
            await _check_followups()
        except Exception as e:
            logger.error(f"Follow-up error: {e}")
        await asyncio.sleep(_CHECK_INTERVAL)


async def _check_followups():
    if not _bot:
        return

    cutoff = (datetime.utcnow() - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")

    rows = await db.get_db().fetch_all(
        "SELECT telegram_id, full_name, username, phone, created_at "
        "FROM leads "
        "WHERE phone IS NOT NULL AND phone != '' "
        "AND status != 'converted' "
        "AND created_at <= ?",
        {"1": cutoff}
    )

    for row in rows:
        uid = row["telegram_id"]
        if uid in _reminded:
            continue
        _reminded.add(uid)

        text = msg.FOLLOWUP_3D.format(url=WEBSITE_URL)
        try:
            if uid > 0:
                await _bot.send_message(uid, text, parse_mode="Markdown")
                logger.info(f"Follow-up 3d sent to user {uid}")
            await db.update_user(uid, inactivity_notified=1)
        except Exception as e:
            logger.error(f"Follow-up send error for {uid}: {e}")