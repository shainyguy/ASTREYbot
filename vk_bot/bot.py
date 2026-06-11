import asyncio
import logging

from config import VK_TOKEN, VK_GROUP_ID
from .api import VKAPI
from .longpoll import VKGroupLongPoll
from . import funnel as vk_funnel

logger = logging.getLogger(__name__)


async def run_vk_bot() -> None:
    api = VKAPI(VK_TOKEN)

    # Определяем group_id: из env или авто-резолв
    group_id = VK_GROUP_ID
    if not group_id:
        group_id = await api.resolve_group_id("astrey.store")
        if not group_id:
            raise RuntimeError(
                "Не удалось определить VK_GROUP_ID. "
                "Добавь VK_GROUP_ID в переменные окружения."
            )
        logger.info(f"VK group_id auto-detected: {group_id}")

    lp = VKGroupLongPoll(api, group_id)
    logger.info(f"VK бот запущен (group_id={group_id})")

    async for message in lp.listen():
        asyncio.create_task(_handle_safe(message))


async def _handle_safe(message) -> None:
    try:
        await vk_funnel.handle_message(message)
    except Exception as e:
        logger.error(f"VK handler error: {e}", exc_info=True)
