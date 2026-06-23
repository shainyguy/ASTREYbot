"""Общий сервис уведомлений — отправляет админу и в TG, и в VK."""
import logging
from typing import Optional, List
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)

_bot: Optional[Bot] = None
_vk_api = None


def set_bot(bot: Bot) -> None:
    global _bot
    _bot = bot


def set_vk_api(api) -> None:
    global _vk_api
    _vk_api = api


async def notify_admins(
    admin_ids: List[int],
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "Markdown",
) -> None:
    # Telegram
    if _bot:
        for admin_id in admin_ids:
            try:
                await _bot.send_message(
                    admin_id, text,
                    reply_markup=markup,
                    parse_mode=parse_mode,
                )
            except Exception as e:
                logger.error(f"notify_admins TG → {admin_id}: {e}")
    else:
        logger.warning("notifier: TG bot not set, skipping TG notifications")

    # VK
    if _vk_api:
        from config import ADMIN_VK_IDS
        for vk_id in ADMIN_VK_IDS:
            try:
                vk_text = text.replace('*', '').replace('_', '').replace('`', '')
                await _vk_api.send_message(vk_id, vk_text)
            except Exception as e:
                logger.error(f"notify_admins VK → {vk_id}: {e}")
