import asyncio
import logging
import os
import sys

# Гарантируем что Python видит папку проекта (нужно для Railway/Docker)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import database as db
import gigachat as gc
import notifier
from handlers import user, admin, funnel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения!")

    # ── База данных ──
    db.set_db_path(config.DATABASE_PATH)
    await db.init_db()
    logger.info(f"Database: {config.DATABASE_PATH}")

    # ── GigaChat ──
    auth_key = config.GIGACHAT_AUTH_KEY
    if not auth_key and config.GIGACHAT_CLIENT_ID and config.GIGACHAT_CLIENT_SECRET:
        import base64
        raw = f"{config.GIGACHAT_CLIENT_ID}:{config.GIGACHAT_CLIENT_SECRET}"
        auth_key = base64.b64encode(raw.encode()).decode()

    gigachat_instance = None
    if auth_key:
        gigachat_instance = gc.GigaChatClient(auth_key, config.GIGACHAT_SCOPE)
        funnel.gigachat_client = gigachat_instance
        logger.info("GigaChat: initialized")
    else:
        logger.warning("GigaChat: credentials missing — AI disabled")

    # ── Telegram бот ──
    tg_bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    notifier.set_bot(tg_bot)

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin.router)
    dp.include_router(funnel.router)
    dp.include_router(user.router)

    # ── VK бот ──
    vk_bot_instance = None
    if config.VK_TOKEN:
        try:
            from vk_bot.bot import create_vk_bot
            from vk_bot import funnel as vk_funnel
            if gigachat_instance:
                vk_funnel.gigachat_client = gigachat_instance
            vk_bot_instance = create_vk_bot()
            logger.info("VK bot: initialized")
        except Exception as e:
            logger.error(f"VK bot init failed: {e}")
    else:
        logger.warning("VK_TOKEN not set — VK bot disabled")

    # ── Уведомление о запуске ──
    platforms = "Telegram ✅" + (" | ВКонтакте ✅" if vk_bot_instance else " | ВКонтакте ❌ (нет токена)")
    for admin_id in config.ADMIN_IDS:
        try:
            await tg_bot.send_message(
                admin_id,
                f"🚀 *Бот АСТРЕЙ запущен!*\n\n{platforms}\n\n/admin — панель управления",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    # ── Запуск обоих ботов параллельно ──
    tasks = [dp.start_polling(tg_bot, allowed_updates=dp.resolve_used_update_types())]
    if vk_bot_instance:
        tasks.append(vk_bot_instance.run_polling())

    logger.info(f"Starting {len(tasks)} bot(s)...")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
