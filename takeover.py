"""Единый сервис перехвата диалогов — работает одинаково для Telegram и ВКонтакте.

Соглашение по ID:
    user_db_id > 0  → клиент в Telegram (это его telegram_id)
    user_db_id < 0  → клиент во ВКонтакте (это -vk_id)

Админ всегда сидит в Telegram — независимо от того, откуда пишет клиент.
"""
import logging
from typing import Optional

import database as db

logger = logging.getLogger(__name__)

_bot = None      # aiogram Bot
_vk_api = None   # vk_bot.api.VKAPI

# admin_id -> user_db_id  (кто какой диалог держит)
_active: dict[int, int] = {}
# user_db_id -> admin_id  (обратный индекс)
_by_user: dict[int, int] = {}


def set_bot(bot) -> None:
    global _bot
    _bot = bot


def set_vk_api(api) -> None:
    global _vk_api
    _vk_api = api


def is_vk(user_db_id: int) -> bool:
    return user_db_id < 0


def admin_of(user_db_id: int) -> Optional[int]:
    """Какой админ ведёт этого клиента (None — никакой)."""
    return _by_user.get(user_db_id)


def user_of(admin_id: int) -> Optional[int]:
    """Какого клиента ведёт этот админ (None — никакого)."""
    return _active.get(admin_id)


def active_count() -> int:
    return len(_active)


# ─────────────────────────────────────────────
#  ВОССТАНОВЛЕНИЕ ПОСЛЕ РЕСТАРТА
# ─────────────────────────────────────────────

async def restore_from_db() -> int:
    """Поднимает незакрытые перехваты из БД — переживает рестарт Railway."""
    try:
        rows = await db.get_active_takeovers()
    except Exception as e:
        logger.error(f"takeover.restore_from_db: {e}")
        return 0

    for row in rows:
        admin_id = row.get("admin_id")
        user_id = row.get("user_id")
        if admin_id and user_id:
            _active[admin_id] = user_id
            _by_user[user_id] = admin_id
    if _active:
        logger.info(f"Восстановлено активных перехватов: {len(_active)}")
    return len(_active)


# ─────────────────────────────────────────────
#  ВЗЯТЬ / ЗАВЕРШИТЬ
# ─────────────────────────────────────────────

async def start(admin_id: int, user_db_id: int) -> Optional[int]:
    """Админ берёт диалог. Возвращает id прошлого клиента, если тот был отпущен."""
    released = None
    previous = _active.get(admin_id)
    if previous is not None and previous != user_db_id:
        await stop(admin_id, notify_user=True)
        released = previous

    # Если клиента вёл другой админ — забираем
    other_admin = _by_user.get(user_db_id)
    if other_admin is not None and other_admin != admin_id:
        _active.pop(other_admin, None)

    _active[admin_id] = user_db_id
    _by_user[user_db_id] = admin_id

    await db.start_takeover(admin_id, user_db_id)
    await db.update_user(user_db_id, stage="manager_takeover")

    if is_vk(user_db_id):
        from vk_bot import states as vk_states
        vk_states.set_state(abs(user_db_id), vk_states.MANAGER_TAKEOVER)

    return released


async def stop(admin_id: int, notify_user: bool = True) -> Optional[int]:
    """Админ завершает диалог, клиент возвращается к боту."""
    user_db_id = _active.pop(admin_id, None)
    if user_db_id is None:
        return None
    _by_user.pop(user_db_id, None)

    try:
        await db.end_takeover(admin_id, user_db_id)
        await db.update_user(user_db_id, stage="ai_chat")
    except Exception as e:
        logger.error(f"takeover.stop db: {e}")

    if is_vk(user_db_id):
        from vk_bot import states as vk_states
        vk_states.set_state(abs(user_db_id), vk_states.AI_CHAT)

    if notify_user:
        import messages as msg
        await send_to_user(user_db_id, msg.TAKEOVER_ENDED_USER)

    return user_db_id


# ─────────────────────────────────────────────
#  ДОСТАВКА СООБЩЕНИЙ
# ─────────────────────────────────────────────

async def send_to_user(user_db_id: int, text: str) -> tuple[bool, str]:
    """Отправляет текст клиенту в его мессенджер. → (успех, описание ошибки)."""
    if is_vk(user_db_id):
        if not _vk_api:
            return False, "VK API не инициализирован (ВК-бот не запущен)"
        try:
            await _vk_api.send_message(abs(user_db_id), _strip_md(text))
            return True, ""
        except Exception as e:
            logger.error(f"takeover → VK {user_db_id}: {e}")
            return False, str(e)

    if not _bot:
        return False, "Telegram bot не инициализирован"
    try:
        await _bot.send_message(user_db_id, text)
        return True, ""
    except Exception as e:
        logger.error(f"takeover → TG {user_db_id}: {e}")
        return False, str(e)


async def relay_to_admin(user_db_id: int, text: str) -> bool:
    """Сообщение клиента → ведущему админу. False, если диалог никто не держит."""
    admin_id = _by_user.get(user_db_id)
    if admin_id is None:
        return False

    name, source = await describe_user(user_db_id)
    import notifier
    return await notifier.send_to_admin(
        admin_id,
        f"💬 *{_escape(name)}* {source}\n\n{_escape(text)}",
    )


async def notify_admins_waiting(user_db_id: int, reason: str) -> None:
    """Клиент ждёт менеджера — рассылаем всем админам с кнопкой «Взять в работу»."""
    import notifier
    import keyboards as kb
    from config import ADMIN_IDS

    name, source = await describe_user(user_db_id)
    user = await db.get_user(user_db_id) or {}
    username = user.get("username") or ""

    text = (
        f"🆘 *Клиенту нужен менеджер*\n\n"
        f"👤 *{_escape(name)}* {source}\n"
        f"💬 {_escape(reason)}\n\n"
        f"Нажми «Взять в работу» — и всё, что ты напишешь, "
        f"уйдёт клиенту от имени АСТРЕЙ 👇"
    )
    markup = kb.kb_notify_admin(user_db_id, username)

    for admin_id in ADMIN_IDS:
        await notifier.send_to_admin(admin_id, text, markup)


async def describe_user(user_db_id: int) -> tuple[str, str]:
    """→ (отображаемое имя, откуда пишет)."""
    user = await db.get_user(user_db_id) or {}
    name = (
        user.get("full_name")
        or " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x).strip()
        or user.get("username")
        or f"ID {abs(user_db_id)}"
    )
    if is_vk(user_db_id):
        return name, f"— ВКонтакте (vk.com/id{abs(user_db_id)})"
    username = user.get("username")
    return name, f"— Telegram (@{username})" if username else "— Telegram"


def escape(text: str) -> str:
    """Экранирование под legacy Markdown — только _ * ` [ ."""
    import re
    return re.sub(r"([_*`\[])", r"\\\1", text or "")


_escape = escape  # старое имя, оставлено для совместимости


def _strip_md(text: str) -> str:
    return (text or "").replace("*", "").replace("_", "").replace("`", "")
