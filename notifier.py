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


def strip_md(text: str) -> str:
    return (text or "").replace("*", "").replace("_", "").replace("`", "")


async def send_to_admin(
    admin_id: int,
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    """Отправляет админу с тройной подстраховкой.

    Уведомление админа терять нельзя, поэтому если Telegram отклонил сообщение —
    пробуем без разметки, потом вообще без клавиатуры. Раньше любая ошибка
    (кривой Markdown или запрещённая tg://user кнопка) молча съедала уведомление.
    """
    if not _bot:
        logger.warning("notifier: TG bot не задан — уведомление потеряно")
        return False

    # 1. Как задумано — Markdown + кнопки
    try:
        await _bot.send_message(admin_id, text, reply_markup=markup, parse_mode="Markdown")
        return True
    except Exception as e:
        logger.warning(f"notify {admin_id}: Markdown отклонён ({e}) — шлю без разметки")

    # 2. Без разметки, но с кнопками
    try:
        await _bot.send_message(admin_id, strip_md(text), reply_markup=markup, parse_mode=None)
        return True
    except Exception as e:
        logger.warning(f"notify {admin_id}: с кнопками не прошло ({e}) — шлю голый текст")

    # 3. Голый текст — последний шанс
    try:
        await _bot.send_message(admin_id, strip_md(text), parse_mode=None)
        return True
    except Exception as e:
        logger.error(f"notify {admin_id}: уведомление доставить не удалось — {e}")
        return False


async def notify_admins(
    admin_ids: List[int],
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "Markdown",
) -> None:
    for admin_id in admin_ids:
        await send_to_admin(admin_id, text, markup)

    if _vk_api:
        from config import ADMIN_VK_IDS
        for vk_id in ADMIN_VK_IDS:
            try:
                await _vk_api.send_message(vk_id, strip_md(text))
            except Exception as e:
                logger.error(f"notify_admins VK → {vk_id}: {e}")
