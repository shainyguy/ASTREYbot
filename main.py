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
import takeover
import inactivity
import reminder_scheduler
import followup_scheduler
from handlers import user, admin, funnel, order

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
    takeover.set_bot(tg_bot)
    reminder_scheduler.set_bot(tg_bot)
    followup_scheduler.set_bot(tg_bot)

    # Поднимаем незакрытые перехваты — иначе после рестарта Railway
    # менеджер молча терял все активные диалоги
    restored = await takeover.restore_from_db()

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin.router)
    dp.include_router(order.router)   # до funnel: шаги заказа важнее общего AI-чата
    dp.include_router(funnel.router)
    dp.include_router(user.router)

    # ── VK бот ──
    vk_enabled = False
    if config.VK_TOKEN:
        try:
            from vk_bot import funnel as vk_funnel
            from vk_bot.api import VKAPI
            if gigachat_instance:
                vk_funnel.gigachat_client = gigachat_instance
            # Подключаем VK API сразу: менеджер должен уметь отвечать в ВК,
            # даже если Long Poll ещё не поднялся
            vk_api = VKAPI(config.VK_TOKEN)
            takeover.set_vk_api(vk_api)
            notifier.set_vk_api(vk_api)
            vk_enabled = True
            logger.info("VK bot: ready")
        except Exception as e:
            logger.error(f"VK bot init failed: {e}")
    else:
        logger.warning("VK_TOKEN not set — VK bot disabled")

    # ── Уведомление о запуске ──
    platforms = "Telegram ✅" + (" | ВКонтакте ✅" if vk_enabled else " | ВКонтакте ❌ (нет токена)")
    restored_line = f"\n🎯 Восстановлено диалогов: {restored}" if restored else ""
    for admin_id in config.ADMIN_IDS:
        await notifier.send_to_admin(
            admin_id,
            f"🚀 *Бот АСТРЕЙ запущен*\n\n{platforms}{restored_line}\n\n/admin — панель управления",
        )

    # ── Монитор неактивности + напоминания ──
    tasks = [dp.start_polling(tg_bot, allowed_updates=dp.resolve_used_update_types())]
    tasks.append(inactivity.run_inactivity_monitor())
    tasks.append(reminder_scheduler.run_reminder_scheduler())
    tasks.append(followup_scheduler.run_followup())

    # ── HTTP API сервер ──
    if config.BOT_API_SECRET:
        from http_api import run_http_server
        tasks.append(run_http_server())
        logger.info("HTTP API: enabled")
    else:
        logger.warning("BOT_API_SECRET not set — HTTP API disabled")

    # ── Запуск VK бота ──
    if vk_enabled:
        from vk_bot.bot import run_vk_bot
        tasks.append(run_vk_bot())

    logger.info(f"Starting {len(tasks)} task(s)...")
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
