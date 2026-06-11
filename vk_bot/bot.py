import logging
from vkbottle.bot import Bot, Message

from config import VK_TOKEN
from . import funnel as vk_funnel

logger = logging.getLogger(__name__)


def create_vk_bot() -> Bot:
    bot = Bot(token=VK_TOKEN)

    @bot.on.message()
    async def universal_handler(message: Message) -> None:
        try:
            await vk_funnel.handle_message(message)
        except Exception as e:
            logger.error(f"VK handler error: {e}", exc_info=True)

    return bot
