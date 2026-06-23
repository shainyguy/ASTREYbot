import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
import gigachat as gc
import messages as msg
import keyboards as kb
from states import Funnel
from config import ADMIN_IDS, AI_CONFUSION_THRESHOLD, WEBSITE_URL

router = Router()
logger = logging.getLogger(__name__)

# Глобальный GigaChat клиент (инициализируется в main.py)
gigachat_client: gc.GigaChatClient = None

# Счётчик сообщений для предложения заказать
_ai_message_count: dict[int, int] = {}


async def _update_bot_msg_time(user_id: int) -> None:
    await db.update_last_bot_message(user_id)


async def _maybe_ask_order_ready(user_id: int, state: FSMContext, message: Message) -> None:
    count = _ai_message_count.get(user_id, 0) + 1
    _ai_message_count[user_id] = count
    if count % 3 == 0:
        nudge_idx = (count // 3 - 1) % len(msg.ORDER_NUDGES)
        nudge_text = msg.ORDER_NUDGES[nudge_idx]
        await message.answer(
            nudge_text.format(url=WEBSITE_URL),
            reply_markup=kb.kb_ai_chat(),
            parse_mode="Markdown"
        )


# ══════════════════════════════════════════════
#  СТАРТ ВОРОНКИ
# ══════════════════════════════════════════════

@router.callback_query(F.data == "start_funnel")
async def cb_start_funnel(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Funnel.choose_occasion)
    await db.upsert_lead(call.from_user.id, stage="choose_occasion")
    await _update_bot_msg_time(call.from_user.id)
    await call.message.edit_text(msg.CHOOSE_OCCASION, reply_markup=kb.kb_occasion(), parse_mode="Markdown")


@router.callback_query(F.data == "ask_question")
async def cb_ask_question(call: CallbackQuery, state: FSMContext):
    await call.answer()
    current = await state.get_state()
    if current not in (Funnel.ai_chat, Funnel.presentation):
        await state.set_state(Funnel.ai_chat)
    await _update_bot_msg_time(call.from_user.id)
    await call.message.answer(
        "💬 *Задай любой вопрос про наши подарки!*\n\nОтвечу мгновенно 👇",
        reply_markup=kb.kb_ai_chat(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "back")
async def cb_back(call: CallbackQuery, state: FSMContext):
    await call.answer()
    current = await state.get_state()

    if current == Funnel.choose_occasion:
        await state.set_state(Funnel.welcome)
        await call.message.edit_text(msg.WELCOME, reply_markup=kb.kb_welcome(), parse_mode="Markdown")
    elif current == Funnel.choose_recipient:
        await state.set_state(Funnel.choose_occasion)
        await call.message.edit_text(msg.CHOOSE_OCCASION, reply_markup=kb.kb_occasion(), parse_mode="Markdown")
    elif current == Funnel.choose_budget:
        await state.set_state(Funnel.choose_recipient)
        await call.message.edit_text(msg.CHOOSE_RECIPIENT, reply_markup=kb.kb_recipient(), parse_mode="Markdown")
    elif current == Funnel.presentation:
        await state.set_state(Funnel.choose_budget)
        await call.message.edit_text(msg.CHOOSE_BUDGET, reply_markup=kb.kb_budget(), parse_mode="Markdown")
    elif current == Funnel.ai_chat:
        data = await state.get_data()
        if data.get("budget"):
            await state.set_state(Funnel.presentation)
            occasion = data.get("occasion", "другое")
            recipient = data.get("recipient", "другому")
            budget = data.get("budget", "до 1000")
            text = _build_presentation(occasion, recipient, budget)
            await call.message.edit_text(text, reply_markup=kb.kb_presentation(budget), parse_mode="Markdown")
        else:
            await state.set_state(Funnel.choose_budget)
            await call.message.edit_text(msg.CHOOSE_BUDGET, reply_markup=kb.kb_budget(), parse_mode="Markdown")


@router.callback_query(F.data == "restart")
async def cb_restart(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Funnel.welcome)
    gc.clear_history(call.from_user.id)
    await call.message.answer(msg.WELCOME, reply_markup=kb.kb_welcome(), parse_mode="Markdown")


# ══════════════════════════════════════════════
#  ШАГ 1 — ПОВОД
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("occasion_"))
async def cb_occasion(call: CallbackQuery, state: FSMContext):
    await call.answer()
    occasion = call.data.split("occasion_", 1)[1]
    await state.update_data(occasion=occasion)
    await state.set_state(Funnel.choose_recipient)

    await db.update_user(call.from_user.id, occasion=occasion, stage="choose_recipient")
    await db.upsert_lead(call.from_user.id, occasion=occasion, stage="choose_recipient")
    await _update_bot_msg_time(call.from_user.id)

    await call.message.edit_text(msg.CHOOSE_RECIPIENT, reply_markup=kb.kb_recipient(), parse_mode="Markdown")


@router.message(Funnel.choose_occasion)
async def msg_occasion_custom(message: Message, state: FSMContext):
    occasion = message.text.strip()
    await state.update_data(occasion=occasion)
    await state.set_state(Funnel.choose_recipient)

    await db.update_user(message.from_user.id, occasion=occasion, stage="choose_recipient")
    await db.upsert_lead(message.from_user.id, occasion=occasion, stage="choose_recipient")
    await _update_bot_msg_time(message.from_user.id)

    await message.answer(msg.CHOOSE_RECIPIENT, reply_markup=kb.kb_recipient(), parse_mode="Markdown")


# ══════════════════════════════════════════════
#  ШАГ 2 — КОМУ
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("recipient_"))
async def cb_recipient(call: CallbackQuery, state: FSMContext):
    await call.answer()
    recipient = call.data.split("recipient_", 1)[1]
    await state.update_data(recipient=recipient)
    await state.set_state(Funnel.choose_budget)

    await db.update_user(call.from_user.id, recipient=recipient, stage="choose_budget")
    await db.upsert_lead(call.from_user.id, recipient=recipient, stage="choose_budget")
    await _update_bot_msg_time(call.from_user.id)

    await call.message.edit_text(msg.CHOOSE_BUDGET, reply_markup=kb.kb_budget(), parse_mode="Markdown")


@router.message(Funnel.choose_recipient)
async def msg_recipient_custom(message: Message, state: FSMContext):
    recipient = message.text.strip()
    await state.update_data(recipient=recipient)
    await state.set_state(Funnel.choose_budget)

    await db.update_user(message.from_user.id, recipient=recipient, stage="choose_budget")
    await db.upsert_lead(message.from_user.id, recipient=recipient, stage="choose_budget")
    await _update_bot_msg_time(message.from_user.id)

    await message.answer(msg.CHOOSE_BUDGET, reply_markup=kb.kb_budget(), parse_mode="Markdown")


# ══════════════════════════════════════════════
#  ШАГ 3 — БЮДЖЕТ + ПРЕЗЕНТАЦИЯ
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("budget_"))
async def cb_budget(call: CallbackQuery, state: FSMContext):
    await call.answer()
    budget_raw = call.data.split("budget_", 1)[1]
    data = await state.get_data()
    occasion = data.get("occasion", "другое")
    recipient = data.get("recipient", "другому")

    await state.update_data(budget=budget_raw)
    await state.set_state(Funnel.presentation)

    await db.update_user(call.from_user.id, budget=budget_raw, stage="presentation")
    await db.upsert_lead(
        call.from_user.id,
        budget=budget_raw,
        occasion=occasion,
        recipient=recipient,
        stage="presentation"
    )

    text = _build_presentation(occasion, recipient, budget_raw)
    await _update_bot_msg_time(call.from_user.id)
    await call.message.edit_text(text, reply_markup=kb.kb_presentation(budget_raw), parse_mode="Markdown")

    # Сразу предлагаем AI-чат
    await _update_bot_msg_time(call.from_user.id)
    await call.message.answer(msg.AI_INTRO, reply_markup=kb.kb_ai_chat(), parse_mode="Markdown")
    await state.set_state(Funnel.ai_chat)

    # Уведомляем админа о новом лиде в воронке
    await _notify_admin_new_lead(call.bot, call.from_user.id)


def _build_presentation(occasion: str, recipient: str, budget: str) -> str:
    key = (occasion.lower(), recipient.lower(), budget.lower())
    preset = msg.PRESENTATIONS.get(key)
    if preset:
        return preset

    rec_map = {
        "до 1000": msg.RECOMMENDATIONS["до 1000"],
        "1000-3000": msg.RECOMMENDATIONS["1000-3000"],
        "3000+": msg.RECOMMENDATIONS["3000+"],
        "не важно": msg.RECOMMENDATIONS["не важно"],
    }
    recommendations = rec_map.get(budget, msg.RECOMMENDATIONS["до 1000"])

    occasion_text = _occasion_line(occasion)
    recipient_text = _recipient_line(recipient)

    return (
        f"🎁 *Отличный выбор!*\n\n"
        f"{occasion_text}{recipient_text}"
        f"Вот лучшее, что я могу предложить:\n\n"
        f"{recommendations}\n\n"
        f"_Нажми кнопку ниже, чтобы оформить заказ на сайте 👇_"
    )


def _occasion_line(occasion: str) -> str:
    nice = {
        "день рождения": "🎂 *Повод:* День рождения\n",
        "годовщина": "💑 *Повод:* Годовщина — самый романтичный подарок!\n",
        "свадьба": "💍 *Повод:* Свадьба — подарок на всю жизнь!\n",
        "новый год": "🎄 *Повод:* Новый год\n",
        "просто так": "💝 *Повод:* Просто так — самые трогательные подарки!\n",
    }
    return nice.get(occasion.lower(), f"🎁 *Повод:* {occasion.capitalize()}\n")


def _recipient_line(recipient: str) -> str:
    nice = {
        "девушке": "👩 *Кому:* Девушке/Жене\n\n",
        "парню": "👨 *Кому:* Парню/Мужу\n\n",
        "маме": "👩‍👧 *Кому:* Маме — будет в восторге!\n\n",
        "папе": "👨‍👦 *Кому:* Папе\n\n",
        "другу": "👫 *Кому:* Другу/Подруге\n\n",
        "ребёнку": "👶 *Кому:* Ребёнку\n\n",
    }
    return nice.get(recipient.lower(), f"👤 *Кому:* {recipient.capitalize()}\n\n")


# ══════════════════════════════════════════════
#  AI ЧАТ — ОТВЕТЫ НА ВОПРОСЫ
# ══════════════════════════════════════════════

@router.message(Funnel.ai_chat)
async def msg_ai_chat(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    text = message.text or ""

    await db.log_message(user_id, "incoming", text)

    # Проверяем — не в режиме ли передачи менеджеру
    user = await db.get_user(user_id)
    if user and user.get("stage") == "manager_takeover":
        from handlers.admin import forward_to_admin, user_takeovers
        if user_id in user_takeovers:
            await forward_to_admin(bot, user_id, text)
        return

    await message.bot.send_chat_action(message.chat.id, "typing")

    # FAQ быстрые ответы
    faq_answer = _check_faq(text)
    if faq_answer:
        await db.log_message(user_id, "outgoing", faq_answer)
        await message.answer(faq_answer, reply_markup=kb.kb_ai_chat(), parse_mode="Markdown")
        return

    # AI ответ
    history = gc.get_history(user_id)
    ai_response = ""

    if gigachat_client:
        ai_response = await gigachat_client.chat(history, text)

    if ai_response:
        gc.add_to_history(user_id, "user", text)
        gc.add_to_history(user_id, "assistant", ai_response)
        await db.update_user(user_id, ai_confusion_count=0)
        await _update_bot_msg_time(user_id)

        await db.log_message(user_id, "outgoing", ai_response)
        await message.answer(ai_response, reply_markup=kb.kb_ai_chat(), parse_mode="Markdown")
        await _maybe_ask_order_ready(user_id, state, message)

        # После 3 AI ответов — предлагаем оставить контакт
        history_len = len(gc.get_history(user_id))
        if history_len >= 6 and user and not user.get("full_name"):
            await state.set_state(Funnel.get_name)
            await message.answer(msg.GET_NAME, parse_mode="Markdown")
    else:
        # AI не ответил — увеличиваем счётчик и уведомляем
        confusion = (user.get("ai_confusion_count") or 0) + 1 if user else 1
        await db.update_user(user_id, ai_confusion_count=confusion)

        if confusion >= AI_CONFUSION_THRESHOLD:
            await _notify_admin_needs_help(bot, user_id, text, confusion)
            await db.update_user(user_id, stage="manager_takeover")
            await message.answer(msg.MANAGER_CONNECTED, parse_mode="Markdown")
        else:
            await message.answer(msg.FALLBACK_AI, reply_markup=kb.kb_ai_chat(), parse_mode="Markdown")


def _check_faq(text: str) -> str:
    text_lower = text.lower()
    for keyword, answer in msg.FAQ.items():
        if keyword in text_lower:
            return answer
    return ""


@router.callback_query(F.data.startswith("faq_"))
async def cb_faq(call: CallbackQuery):
    await call.answer()
    await _update_bot_msg_time(call.from_user.id)
    key = call.data.split("faq_", 1)[1]
    answer = msg.FAQ.get(key)
    if answer:
        await call.message.answer(answer, reply_markup=kb.kb_ai_chat(), parse_mode="Markdown")
    else:
        await call.message.answer(
            "🌟 Перейди на наш сайт — там вся информация!\nhttps://astreys.ru",
            reply_markup=kb.kb_go_to_site()
        )


@router.callback_query(F.data == "call_manager")
async def cb_call_manager(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.answer()
    user_id = call.from_user.id
    await db.update_user(user_id, stage="manager_takeover")
    await call.message.answer(msg.MANAGER_CONNECTED, parse_mode="Markdown")
    await _notify_admin_needs_help(bot, user_id, "Пользователь нажал 'Позвать менеджера'", 0)


# ══════════════════════════════════════════════
#  ШАГ 4 — ПОЛУЧИТЬ ИМЯ
# ══════════════════════════════════════════════

@router.message(Funnel.get_name)
async def msg_get_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Введи своё имя 😊")
        return

    await state.update_data(full_name=name)
    await state.set_state(Funnel.get_phone)
    await db.update_user(message.from_user.id, full_name=name, stage="get_phone")
    await db.upsert_lead(message.from_user.id, full_name=name, stage="get_phone")
    await _update_bot_msg_time(message.from_user.id)

    await message.answer(
        msg.GET_PHONE.format(name=name),
        reply_markup=kb.kb_get_phone(),
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════
#  ШАГ 5 — ПОЛУЧИТЬ ТЕЛЕФОН
# ══════════════════════════════════════════════

@router.message(Funnel.get_phone, F.contact)
async def msg_get_phone_contact(message: Message, state: FSMContext, bot: Bot):
    phone = message.contact.phone_number
    await _complete_lead(message, state, bot, phone)


@router.message(Funnel.get_phone, F.text)
async def msg_get_phone_text(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()

    if text in ("Пропустить →", "Пропустить", "пропустить", "skip"):
        data = await state.get_data()
        name = data.get("full_name", "")
        await state.set_state(Funnel.completed)
        await _update_bot_msg_time(message.from_user.id)
        await message.answer(
            msg.SKIP_PHONE.format(url=WEBSITE_URL),
            reply_markup=kb.kb_go_to_site(),
            parse_mode="Markdown"
        )
        await _notify_admin_lead_no_phone(bot, message.from_user.id)
        return

    import re
    phone_clean = re.sub(r"[^\d+]", "", text)
    if len(phone_clean) >= 10:
        await _complete_lead(message, state, bot, phone_clean)
    else:
        await message.answer(
            "📱 Введи корректный номер телефона (например: +79991234567)\n\nИли нажми «Пропустить»",
            reply_markup=kb.kb_get_phone()
        )


async def _complete_lead(message: Message, state: FSMContext, bot: Bot, phone: str):
    data = await state.get_data()
    name = data.get("full_name", message.from_user.first_name or "")
    occasion = data.get("occasion", "")
    recipient = data.get("recipient", "")
    budget = data.get("budget", "")
    user_id = message.from_user.id

    await state.set_state(Funnel.completed)
    await db.update_user(user_id, phone=phone, stage="completed")
    await _update_bot_msg_time(user_id)
    await db.upsert_lead(
        user_id,
        full_name=name,
        phone=phone,
        occasion=occasion,
        recipient=recipient,
        budget=budget,
        stage="completed",
        status="new",
        username=message.from_user.username or ""
    )

    await message.answer(
        msg.COMPLETED.format(name=name, url=WEBSITE_URL),
        reply_markup=kb.kb_go_to_site(),
        parse_mode="Markdown"
    )

    await _notify_admin_contact(bot, user_id, name, phone, occasion, recipient, budget, message.from_user.username)


# ══════════════════════════════════════════════
#  УВЕДОМЛЕНИЯ АДМИНИСТРАТОРУ
# ══════════════════════════════════════════════

async def _notify_admin_new_lead(bot: Bot, user_id: int):
    user = await db.get_user(user_id)
    if not user:
        return
    text = msg.ADMIN_NOTIFICATION_NEW_LEAD.format(
        full_name=user.get("full_name") or user.get("first_name") or "Неизвестно",
        username=user.get("username") or "без username",
        occasion=user.get("occasion") or "—",
        recipient=user.get("recipient") or "—",
        budget=user.get("budget") or "—",
        created_at=_now_str(),
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                text,
                reply_markup=kb.kb_notify_admin(user_id),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


async def _notify_admin_contact(
    bot: Bot, user_id: int, name: str, phone: str,
    occasion: str, recipient: str, budget: str, username: str
):
    user = await db.get_user(user_id)
    product_interest = user.get("product_interest", "Карта звёздного неба") if user else "—"
    text = msg.ADMIN_NOTIFICATION_CONTACT.format(
        full_name=name,
        username=username or "без username",
        telegram_id=user_id,
        phone=phone,
        occasion=occasion or "—",
        recipient=recipient or "—",
        budget=budget or "—",
        product_interest=product_interest or "—",
        created_at=_now_str(),
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                text,
                reply_markup=kb.kb_notify_admin(user_id),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


async def _notify_admin_needs_help(bot: Bot, user_id: int, last_message: str, count: int):
    user = await db.get_user(user_id)
    name = (user.get("full_name") or user.get("first_name") or "Пользователь") if user else "Пользователь"
    username = (user.get("username") or "без username") if user else "без username"
    text = msg.NEED_HELP_NOTIFY.format(
        name=name,
        username=username,
        user_id=user_id,
        last_message=last_message[:200],
        count=count,
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                text,
                reply_markup=kb.kb_notify_admin(user_id),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


async def _notify_admin_lead_no_phone(bot: Bot, user_id: int):
    user = await db.get_user(user_id)
    if not user:
        return
    name = user.get("full_name") or user.get("first_name") or "Неизвестно"
    username = user.get("username") or "без username"
    text = (
        f"👤 *Лид прошёл воронку без телефона*\n\n"
        f"Имя: {name} (@{username})\n"
        f"Telegram ID: `{user_id}`\n"
        f"Повод: {user.get('occasion') or '—'}\n"
        f"Бюджет: {user.get('budget') or '—'}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id, text,
                reply_markup=kb.kb_notify_admin(user_id),
                parse_mode="Markdown"
            )
        except Exception:
            pass


def _now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%d.%m.%Y %H:%M")
