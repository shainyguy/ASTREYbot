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
from handlers import user, admin, funnel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в переменных окружения!")

    # Инициализация БД
    db.set_db_path(config.DATABASE_PATH)
    await db.init_db()
    logger.info(f"Database initialized at {config.DATABASE_PATH}")

    # Инициализация GigaChat
    auth_key = config.GIGACHAT_AUTH_KEY
    if not auth_key and config.GIGACHAT_CLIENT_ID and config.GIGACHAT_CLIENT_SECRET:
        import base64
        raw = f"{config.GIGACHAT_CLIENT_ID}:{config.GIGACHAT_CLIENT_SECRET}"
        auth_key = base64.b64encode(raw.encode()).decode()

    if auth_key:
        funnel.gigachat_client = gc.GigaChatClient(auth_key, config.GIGACHAT_SCOPE)
        logger.info("GigaChat client initialized")
    else:
        logger.warning("GigaChat credentials not provided — AI responses disabled")

    # Инициализация бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрация роутеров (порядок важен!)
    dp.include_router(admin.router)
    dp.include_router(funnel.router)
    dp.include_router(user.router)

    # Уведомление админов о запуске
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🚀 *Бот АСТРЕЙ запущен!*\n\nВсе системы работают нормально.\n/admin — панель управления",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    logger.info("Bot started polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
