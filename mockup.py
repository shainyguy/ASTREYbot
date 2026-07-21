"""Доставка макета клиенту — в Telegram и во ВКонтакте.

Замыкает цикл, который раньше был разорван: бот обещал «пришлём макет
сюда», но технически этого не умел — менеджер досылал вручную.
"""
import logging
import re

import database as db
import keyboards as kb
import messages as msg
import notifier
import takeover
from config import ADMIN_IDS, format_info

logger = logging.getLogger(__name__)


def next_step_text(order: dict) -> str:
    """Что произойдёт после утверждения — зависит от формата и доставки."""
    fmt = (order or {}).get("format", "electronic")
    if fmt == "electronic":
        return "пришлём готовый файл на почту в течение часа ⚡"
    return "отправим в печать, оформим в рамку и передадим вам 🖼"


async def deliver(bot, order: dict, file_id: str) -> tuple[bool, str]:
    """Отправляет макет клиенту. → (успех, текст ошибки)."""
    user_id = order["telegram_id"]
    order_id = order["id"]
    caption = msg.MOCKUP_READY.format(next_step=next_step_text(order))

    if user_id > 0:
        try:
            await bot.send_photo(
                user_id, file_id,
                caption=caption,
                reply_markup=kb.kb_mockup_review(order_id),
                parse_mode="Markdown",
            )
            return True, ""
        except Exception as e:
            logger.error(f"Макет → TG {user_id}: {e}")
            return False, str(e)

    # ВКонтакте: скачиваем файл из Telegram и заливаем в ВК
    try:
        from vk_bot import bot as vk_bot_module
        vk_api = vk_bot_module.api
        if not vk_api:
            return False, "ВК-бот не запущен"

        file = await bot.get_file(file_id)
        buf = await bot.download_file(file.file_path)
        image_bytes = buf.getvalue()

        plain = caption.replace("*", "").replace("_", "")
        from vk_bot import keyboards as vk_kb
        await vk_api.send_photo(
            abs(user_id), image_bytes, plain, vk_kb.kb_mockup_review()
        )
        return True, ""
    except Exception as e:
        logger.error(f"Макет → ВК {user_id}: {e}")
        return False, str(e)


async def on_approved(order_id: int, user_db_id: int) -> None:
    """Клиент утвердил макет."""
    await db.update_order(order_id, status="approved")
    name, source = await takeover.describe_user(user_db_id)

    for admin_id in ADMIN_IDS:
        await notifier.send_to_admin(
            admin_id,
            msg.ADMIN_MOCKUP_APPROVED.format(
                order_id=order_id,
                name=f"{takeover.escape(name)} {source}",
            ),
            kb.kb_admin_order(order_id, user_db_id),
        )


async def on_revision(order_id: int, user_db_id: int, comment: str) -> None:
    """Клиент попросил правки."""
    await db.update_order(order_id, status="revision", mockup_comment=comment)
    name, source = await takeover.describe_user(user_db_id)

    for admin_id in ADMIN_IDS:
        await notifier.send_to_admin(
            admin_id,
            msg.ADMIN_MOCKUP_REVISION.format(
                order_id=order_id,
                name=f"{takeover.escape(name)} {source}",
                comment=takeover.escape(comment[:500]),
            ),
            kb.kb_admin_order(order_id, user_db_id),
        )


async def active_order(user_db_id: int) -> dict:
    """Заказ этого клиента, по которому ждём реакции на макет."""
    d = db.get_db()
    if not d:
        return None
    return await d.fetch_one(
        "SELECT * FROM orders WHERE telegram_id = ? AND status = 'mockup_sent' "
        "ORDER BY id DESC LIMIT 1",
        {"1": user_db_id},
    )


# ── Распознавание реакции в свободном тексте ──

_APPROVE_WORDS = (
    "всё хорошо", "все хорошо", "всё отлично", "все отлично", "отлично",
    "супер", "класс", "нравится", "нравиться", "утверждаю", "принимаю",
    "здорово", "красиво", "идеально", "то что надо", "то, что надо",
    "всё верно", "все верно", "всё супер", "все супер", "согласен",
    "согласна", "подходит", "да, всё", "да все", "ок", "окей", "👍", "❤",
    "хорошо", "нормально", "норм", "пойдёт", "пойдет", "годится",
    "устраивает", "оставляем", "берём", "берем", "прекрасно", "чудесно",
    "спасибо, всё", "спасибо все", "всё так", "все так",
)

_REVISION_HINTS = (
    "поправ", "исправ", "измен", "переде", "не так", "ошибк", "опечат",
    "замен", "убер", "добав", "не нрав", "неверно", "не то", "лучше",
    "хотел", "можно ли", "а можно", "не подход", "не совсем",
    # повелительное наклонение — почти всегда просьба о правке
    "сделай", "сдвин", "увелич", "уменьш", "поменя", "помен",
    "потемн", "посветл", "крупнее", "мельче", "жирнее", "пришли",
)

# Противопоставление: «всё хорошо, НО...» — это правки, а не утверждение.
# Ищем по границам слов: «но» подстрокой сидит внутри «отлично», а
# «лишь» — внутри «излишне», и такие ложные срабатывания ломали разбор.
_CONTRAST_RE = re.compile(
    r"\b(но|только|однако|хотя|правда|лишь|единственное)\b"
    r"|а вот|если можно|разве что",
    re.IGNORECASE,
)


def read_reaction(text: str) -> str:
    """→ 'approve' | 'revision' | 'unclear'"""
    t = (text or "").strip().lower()
    if not t:
        return "unclear"

    has_revision = any(h in t for h in _REVISION_HINTS)
    has_contrast = bool(_CONTRAST_RE.search(t))
    has_approve = any(w in t for w in _APPROVE_WORDS)

    # «всё хорошо, только фон темнее» — похвала плюс оговорка. Считаем
    # правками: напечатать не то, что просили, дороже лишнего вопроса.
    if has_revision or has_contrast:
        return "revision"
    if has_approve:
        return "approve"
    # Длинный текст без слов одобрения — почти наверняка описание правок
    if len(t.split()) >= 4:
        return "revision"
    return "unclear"
