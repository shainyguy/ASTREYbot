import json
import re
import logging
from datetime import datetime
from .api import VKMessage as Message

import database as db
import gigachat as gc
import messages as msg
import notifier
from config import ADMIN_IDS, AI_CONFUSION_THRESHOLD, WEBSITE_URL
from . import states as st
from . import keyboards as vk_kb

logger = logging.getLogger(__name__)

gigachat_client = None  # Устанавливается из main.py

# Счётчик AI сообщений для предложения заказать
_ai_message_count: dict[int, int] = {}


async def _update_bot_msg_time(db_id: int) -> None:
    await db.update_last_bot_message(db_id)


async def _maybe_ask_order_ready(vk_id: int, db_id: int, message: Message) -> None:
    count = _ai_message_count.get(vk_id, 0) + 1
    _ai_message_count[vk_id] = count
    if count % 3 == 0:
        nudge_idx = (count // 3 - 1) % len(msg.ORDER_NUDGES)
        nudge_text = _strip_md(msg.ORDER_NUDGES[nudge_idx].format(url=WEBSITE_URL))
        await _send(message, nudge_text, vk_kb.kb_ai_chat())


def vk_db_id(vk_id: int) -> int:
    """VK user IDs хранятся как отрицательные, чтобы не пересекаться с TG."""
    return -abs(vk_id)


def _strip_md(text: str) -> str:
    """Убирает Telegram-markdown для отправки в VK."""
    return text.replace("*", "").replace("_", "").replace("`", "")


def _now() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M")


# ══════════════════════════════════════════════
#  ГЛАВНЫЙ ОБРАБОТЧИК
# ══════════════════════════════════════════════

async def handle_message(message: Message) -> None:
    user_id = message.from_id
    db_id = vk_db_id(user_id)
    raw_text = (message.text or "").strip()

    # Парсим payload (от кнопок клавиатуры)
    payload: dict = {}
    if message.payload:
        try:
            payload = json.loads(message.payload) if isinstance(message.payload, str) else message.payload
        except Exception:
            payload = {}

    cmd = payload.get("cmd", "")
    state = st.get_state(user_id)

    # Регистрируем / обновляем пользователя в БД
    await _ensure_user(message, user_id, db_id)
    await db.log_message(db_id, "incoming", raw_text or str(payload))

    # ── Режим менеджера ──
    if state == st.MANAGER_TAKEOVER:
        await notifier.notify_admins(
            ADMIN_IDS,
            f"💬 *Сообщение из ВКонтакте:*\n"
            f"🔗 vk.com/id{user_id}\n"
            f"💬 {raw_text}"
        )
        return

    # ── Кнопка Назад ──
    if cmd == "back":
        await _handle_back(message, user_id, db_id)
        return

    # ── FAQ быстрые ответы ──
    if cmd.startswith("faq_"):
        key = cmd.replace("faq_", "")
        answer = msg.FAQ.get(key, "")
        if answer:
            await _update_bot_msg_time(db_id)
            await _send(message, _strip_md(answer), vk_kb.kb_ai_chat())
            return

    # ── Позвать менеджера ──
    if cmd == "call_manager":
        st.set_state(user_id, st.MANAGER_TAKEOVER)
        await db.update_user(db_id, stage="manager_takeover")
        await _send(message, _strip_md(msg.MANAGER_CONNECTED))
        await _notify_needs_help(user_id, db_id, raw_text, 0)
        return

    # ── Рестарт / /start ──
    if raw_text.lower() in ("/start", "начать", "старт", "привет", "hi", "hello") or cmd == "restart":
        await _show_welcome(message, user_id, db_id)
        return

    # ── Шаг 1: Старт воронки ──
    if cmd == "start_funnel" or (state == st.WELCOME and raw_text == "🎁 Выбрать подарок"):
        await _ask_occasion(message, user_id, db_id)
        return

    if cmd == "ask_question" or (state == st.WELCOME and raw_text == "❓ Задать вопрос"):
        st.set_state(user_id, st.AI_CHAT)
        await _update_bot_msg_time(db_id)
        await _send(message, _strip_md(msg.AI_INTRO), vk_kb.kb_ai_chat())
        return

    # ── Шаг 2: Повод ──
    if state == st.CHOOSE_OCCASION:
        occasion = payload.get("occasion") or raw_text
        await _handle_occasion(message, user_id, db_id, occasion)
        return

    # ── Шаг 3: Кому ──
    if state == st.CHOOSE_RECIPIENT:
        recipient = payload.get("recipient") or raw_text
        await _handle_recipient(message, user_id, db_id, recipient)
        return

    # ── Шаг 4: Бюджет ──
    if state == st.CHOOSE_BUDGET:
        budget = payload.get("budget") or raw_text
        await _handle_budget(message, user_id, db_id, budget)
        return

    # ── AI чат ──
    if state == st.AI_CHAT:
        await _handle_ai(message, user_id, db_id, raw_text)
        return

    # ── Сбор имени ──
    if state == st.GET_NAME:
        await _handle_get_name(message, user_id, db_id, raw_text)
        return

    # ── Сбор телефона ──
    if state == st.GET_PHONE:
        await _handle_get_phone(message, user_id, db_id, raw_text)
        return

    # ── По умолчанию ──
    if state == st.WELCOME:
        await _show_welcome(message, user_id, db_id)
    else:
        st.set_state(user_id, st.AI_CHAT)
        await _handle_ai(message, user_id, db_id, raw_text)


# ══════════════════════════════════════════════
#  ШАГИ ВОРОНКИ
# ══════════════════════════════════════════════

async def _show_welcome(message: Message, user_id: int, db_id: int) -> None:
    st.clear(user_id)
    gc.clear_history(db_id)
    await db.update_user(db_id, stage="welcome")
    text = _strip_md(msg.WELCOME) + "\n\n📱 Пишешь из ВКонтакте — ответим мгновенно!"
    await _update_bot_msg_time(db_id)
    await _send(message, text, vk_kb.kb_welcome())


async def _ask_occasion(message: Message, user_id: int, db_id: int) -> None:
    st.set_state(user_id, st.CHOOSE_OCCASION)
    await db.update_user(db_id, stage="choose_occasion")
    await db.upsert_lead(db_id, stage="choose_occasion", platform="vk")
    await _update_bot_msg_time(db_id)
    await _send(message, _strip_md(msg.CHOOSE_OCCASION), vk_kb.kb_occasion())


async def _handle_back(message: Message, user_id: int, db_id: int) -> None:
    state = st.get_state(user_id)
    data = st.get_data(user_id)

    if state == st.CHOOSE_OCCASION:
        await _show_welcome(message, user_id, db_id)
    elif state == st.CHOOSE_RECIPIENT:
        st.set_state(user_id, st.CHOOSE_OCCASION)
        await _update_bot_msg_time(db_id)
        await _send(message, _strip_md(msg.CHOOSE_OCCASION), vk_kb.kb_occasion())
    elif state == st.CHOOSE_BUDGET:
        st.set_state(user_id, st.CHOOSE_RECIPIENT)
        await _update_bot_msg_time(db_id)
        await _send(message, _strip_md(msg.CHOOSE_RECIPIENT), vk_kb.kb_recipient())
    elif state in (st.AI_CHAT, st.PRESENTATION):
        if data.get("budget"):
            from handlers.funnel import _build_presentation
            occasion = data.get("occasion", "другое")
            recipient = data.get("recipient", "другому")
            budget = data.get("budget", "до 1000")
            pres = _strip_md(_build_presentation(occasion, recipient, budget))
            await _update_bot_msg_time(db_id)
            await _send(message, pres, vk_kb.kb_ai_chat())
        else:
            st.set_state(user_id, st.CHOOSE_BUDGET)
            await _update_bot_msg_time(db_id)
            await _send(message, _strip_md(msg.CHOOSE_BUDGET), vk_kb.kb_budget())
    else:
        await _show_welcome(message, user_id, db_id)


async def _handle_occasion(message: Message, user_id: int, db_id: int, occasion: str) -> None:
    st.update_data(user_id, occasion=occasion)
    st.set_state(user_id, st.CHOOSE_RECIPIENT)
    await db.update_user(db_id, occasion=occasion, stage="choose_recipient")
    await db.upsert_lead(db_id, occasion=occasion, stage="choose_recipient")
    await _update_bot_msg_time(db_id)
    await _send(message, _strip_md(msg.CHOOSE_RECIPIENT), vk_kb.kb_recipient())


async def _handle_recipient(message: Message, user_id: int, db_id: int, recipient: str) -> None:
    st.update_data(user_id, recipient=recipient)
    st.set_state(user_id, st.CHOOSE_BUDGET)
    await db.update_user(db_id, recipient=recipient, stage="choose_budget")
    await db.upsert_lead(db_id, recipient=recipient, stage="choose_budget")
    await _update_bot_msg_time(db_id)
    await _send(message, _strip_md(msg.CHOOSE_BUDGET), vk_kb.kb_budget())


async def _handle_budget(message: Message, user_id: int, db_id: int, budget: str) -> None:
    data = st.get_data(user_id)
    occasion = data.get("occasion", "другое")
    recipient = data.get("recipient", "другому")

    st.update_data(user_id, budget=budget)
    st.set_state(user_id, st.PRESENTATION)

    await db.update_user(db_id, budget=budget, stage="presentation")
    await db.upsert_lead(db_id, budget=budget, occasion=occasion, recipient=recipient,
                         stage="presentation", platform="vk")

    from handlers.funnel import _build_presentation
    pres_text = _strip_md(_build_presentation(occasion, recipient, budget))
    await _update_bot_msg_time(db_id)
    await _send(message, pres_text + f"\n\n👉 Оформить заказ: {WEBSITE_URL}", vk_kb.kb_presentation())
    await _update_bot_msg_time(db_id)
    await _send(message, _strip_md(msg.AI_INTRO))

    await _notify_new_lead(user_id, db_id)


async def _handle_ai(message: Message, user_id: int, db_id: int, text: str) -> None:
    # FAQ
    faq = _check_faq(text)
    if faq:
        await db.log_message(db_id, "outgoing", faq)
        await _update_bot_msg_time(db_id)
        await _send(message, _strip_md(faq), vk_kb.kb_ai_chat())
        return

    # AI
    history = gc.get_history(db_id)
    ai_response = ""
    if gigachat_client:
        ai_response = await gigachat_client.chat(history, text)

    if ai_response:
        gc.add_to_history(db_id, "user", text)
        gc.add_to_history(db_id, "assistant", ai_response)
        await db.update_user(db_id, ai_confusion_count=0)
        await _update_bot_msg_time(db_id)
        clean = _strip_md(ai_response)
        await db.log_message(db_id, "outgoing", clean)
        await _send(message, clean, vk_kb.kb_ai_chat())
        await _maybe_ask_order_ready(user_id, db_id, message)

        # После 6 сообщений предлагаем оставить контакт
        if len(gc.get_history(db_id)) >= 6:
            user = await db.get_user(db_id)
            if user and not user.get("full_name"):
                st.set_state(user_id, st.GET_NAME)
                await _send(message, _strip_md(msg.GET_NAME))
    else:
        user = await db.get_user(db_id)
        confusion = ((user.get("ai_confusion_count") or 0) + 1) if user else 1
        await db.update_user(db_id, ai_confusion_count=confusion)
        if confusion >= AI_CONFUSION_THRESHOLD:
            st.set_state(user_id, st.MANAGER_TAKEOVER)
            await db.update_user(db_id, stage="manager_takeover")
            await _notify_needs_help(user_id, db_id, text, confusion)
            await _send(message, _strip_md(msg.MANAGER_CONNECTED))
        else:
            await _send(message, _strip_md(msg.FALLBACK_AI), vk_kb.kb_ai_chat())


async def _handle_get_name(message: Message, user_id: int, db_id: int, name: str) -> None:
    if len(name) < 2 or len(name) > 50:
        await _send(message, "Введи своё имя 😊")
        return
    st.update_data(user_id, full_name=name)
    st.set_state(user_id, st.GET_PHONE)
    await db.update_user(db_id, full_name=name, stage="get_phone")
    await db.upsert_lead(db_id, full_name=name, stage="get_phone")
    await _update_bot_msg_time(db_id)
    text = _strip_md(msg.GET_PHONE.format(name=name))
    await _send(message, text + "\n\nИли напиши «Пропустить»")


async def _handle_get_phone(message: Message, user_id: int, db_id: int, text: str) -> None:
    if text.lower() in ("пропустить", "skip", "→"):
        st.set_state(user_id, st.COMPLETED)
        await _update_bot_msg_time(db_id)
        await _send(message, _strip_md(msg.SKIP_PHONE.format(url=WEBSITE_URL)), vk_kb.kb_remove())
        await _notify_no_phone(user_id, db_id)
        return

    phone = re.sub(r"[^\d+]", "", text)
    if len(phone) >= 10:
        data = st.get_data(user_id)
        name = data.get("full_name", "")
        occasion = data.get("occasion", "")
        recipient = data.get("recipient", "")
        budget = data.get("budget", "")

        st.set_state(user_id, st.COMPLETED)
        await db.update_user(db_id, phone=phone, stage="completed")
        await db.upsert_lead(db_id, full_name=name, phone=phone, occasion=occasion,
                             recipient=recipient, budget=budget, stage="completed",
                             status="new", platform="vk")
        await _update_bot_msg_time(db_id)

        await _send(message, _strip_md(msg.COMPLETED.format(name=name, url=WEBSITE_URL)),
                    vk_kb.kb_remove())
        await _notify_contact(user_id, db_id, name, phone, occasion, recipient, budget)
    else:
        await _send(message, "📱 Введи корректный номер (например: +79991234567)\n\nИли напиши «Пропустить»")


# ══════════════════════════════════════════════
#  УВЕДОМЛЕНИЯ АДМИНУ (через TG)
# ══════════════════════════════════════════════

async def _notify_new_lead(vk_id: int, db_id: int) -> None:
    user = await db.get_user(db_id)
    if not user:
        return
    text = (
        f"🔔 *НОВЫЙ ЛИД — ВКонтакте!*\n\n"
        f"👤 VK: [vk.com/id{vk_id}](https://vk.com/id{vk_id})\n"
        f"🎁 Повод: {user.get('occasion') or '—'}\n"
        f"👥 Кому: {user.get('recipient') or '—'}\n"
        f"💰 Бюджет: {user.get('budget') or '—'}\n"
        f"⏰ {_now()}"
    )
    await notifier.notify_admins(ADMIN_IDS, text)


async def _notify_contact(vk_id: int, db_id: int, name: str, phone: str,
                          occasion: str, recipient: str, budget: str) -> None:
    text = (
        f"🎯 *ЛИД из ВК ОСТАВИЛ КОНТАКТ!*\n\n"
        f"👤 Имя: *{name}*\n"
        f"🔗 VK: [vk.com/id{vk_id}](https://vk.com/id{vk_id})\n"
        f"📞 Телефон: *{phone}*\n\n"
        f"🎁 Повод: {occasion or '—'}\n"
        f"👥 Кому: {recipient or '—'}\n"
        f"💰 Бюджет: {budget or '—'}\n"
        f"⏰ {_now()}\n\n"
        f"_Рекомендую связаться в течение 30 минут!_ 🔥"
    )
    await notifier.notify_admins(ADMIN_IDS, text)


async def _notify_needs_help(vk_id: int, db_id: int, last_msg: str, count: int) -> None:
    text = (
        f"🆘 *Пользователь ВК просит помощи!*\n\n"
        f"🔗 [vk.com/id{vk_id}](https://vk.com/id{vk_id})\n"
        f"❓ _{last_msg[:200]}_\n\n"
        f"_AI затруднился {count} раза подряд_"
    )
    await notifier.notify_admins(ADMIN_IDS, text)


async def _notify_no_phone(vk_id: int, db_id: int) -> None:
    user = await db.get_user(db_id)
    if not user:
        return
    text = (
        f"👤 *Лид из ВК без телефона*\n\n"
        f"Имя: {user.get('full_name') or '—'}\n"
        f"VK: [vk.com/id{vk_id}](https://vk.com/id{vk_id})\n"
        f"Повод: {user.get('occasion') or '—'}"
    )
    await notifier.notify_admins(ADMIN_IDS, text)


# ══════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ
# ══════════════════════════════════════════════

async def _ensure_user(message: Message, user_id: int, db_id: int) -> None:
    user = await db.get_user(db_id)
    if not user or not user.get("first_name"):
        try:
            vk_users = await message.ctx_api.users.get(user_ids=[user_id])
            if vk_users:
                first_name = vk_users[0].first_name or ""
                last_name = vk_users[0].last_name or ""
                await db.upsert_user(db_id, first_name=first_name, last_name=last_name,
                                     platform="vk")
            else:
                await db.upsert_user(db_id, platform="vk")
        except Exception:
            await db.upsert_user(db_id, platform="vk")


async def _send(message: Message, text: str, keyboard: str = None) -> None:
    kwargs = {"message": text[:4096]}
    if keyboard:
        kwargs["keyboard"] = keyboard
    try:
        await message.answer(**kwargs)
    except Exception as e:
        logger.error(f"VK send error: {e}")


def _check_faq(text: str) -> str:
    from messages import FAQ
    tl = text.lower()
    for key, answer in FAQ.items():
        if key in tl:
            return answer
    return ""
