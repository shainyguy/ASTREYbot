import asyncio
import logging

from config import VK_TOKEN, VK_GROUP_ID
from .api import VKAPI
from .longpoll import VKGroupLongPoll
from . import funnel as vk_funnel

logger = logging.getLogger(__name__)


api: VKAPI = None


async def run_vk_bot() -> None:
    """Запускает VK бот с автоматическим перезапуском при ошибках."""
    global api
    api = VKAPI(VK_TOKEN)
    _vk_instance = api

    # Передаём VK API в админ-хендлеры и notifier
    from handlers.admin import set_vk_api
    set_vk_api(_vk_instance)
    import notifier
    notifier.set_vk_api(_vk_instance)

    group_id = VK_GROUP_ID
    if not group_id:
        group_id = await _vk_instance.resolve_group_id("astrey.store")
        if not group_id:
            logger.error("Не удалось определить VK_GROUP_ID — VK бот не запущен")
            return
        logger.info(f"VK group_id auto-detected: {group_id}")

    retry_delay = 10
    while True:
        try:
            lp = VKGroupLongPoll(_vk_instance, group_id)
            logger.info(f"VK бот запущен (group_id={group_id})")
            async for message in lp.listen():
                asyncio.create_task(_handle_safe(message))
        except RuntimeError as e:
            if "longpoll for this group is not enabled" in str(e):
                logger.error(
                    "VK Long Poll API не включён в настройках сообщества!\n"
                    "Зайди: vk.com/astrey.store → Управление → Настройки → "
                    "Работа с API → Long Poll API → Включить (версия 5.2+)\n"
                    f"Повтор через {retry_delay}с..."
                )
            else:
                logger.error(f"VK ошибка: {e}")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 300)  # экспоненциальный backoff до 5 мин
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"VK неожиданная ошибка: {e}", exc_info=True)
            await asyncio.sleep(retry_delay)


async def _handle_safe(message) -> None:
    try:
        await vk_funnel.handle_message(message)
    except Exception as e:
        logger.error(f"VK handler error: {e}", exc_info=True)
