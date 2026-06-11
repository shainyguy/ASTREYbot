"""Общий сервис уведомлений — VK бот использует TG бота для оповещения админа."""
import logging
from typing import Optional, List
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)

_bot: Optional[Bot] = None


def set_bot(bot: Bot) -> None:
    global _bot
    _bot = bot


async def notify_admins(
    admin_ids: List[int],
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "Markdown",
) -> None:
    if not _bot:
        logger.warning("notifier: TG bot not set, skipping")
        return
    for admin_id in admin_ids:
        try:
            await _bot.send_message(
                admin_id, text,
                reply_markup=markup,
                parse_mode=parse_mode,
            )
        except Exception as e:
            logger.error(f"notify_admins → {admin_id}: {e}")
