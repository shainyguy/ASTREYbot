import asyncio
import logging
import base64
import re
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext

import database as db
import gigachat as gc
import messages as msg
import keyboards as kb
import notifier
import takeover
from states import Funnel, Reminder
from config import ADMIN_IDS, AI_CONFUSION_THRESHOLD, WEBSITE_URL, PRODUCT_IMAGES

router = Router()
logger = logging.getLogger(__name__)

# Глобальный GigaChat клиент (инициализируется в main.py)
gigachat_client: gc.GigaChatClient = None

# Нудж-цепочка: таймеры и счётчики
_nudge_timers: dict[int, asyncio.Task] = {}
_nudge_count: dict[int, int] = {}
MAX_NUDGES = 3
NUDGE_INTERVALS = [45, 90]  # сек между нудж 1→2, 2→3


def _cancel_nudge_timers(user_id: int):
    if user_id in _nudge_timers:
        _nudge_timers[user_id].cancel()
        _nudge_timers.pop(user_id, None)


async def _delayed_nudge(user_id: int, chat_id: int, bot: Bot):
    """Фоновый таймер — отправляет следующий нудж если пользователь молчит."""
    stage = _nudge_count.get(user_id, 0)
    if stage >= MAX_NUDGES:
        return
    interval_idx = stage - 1  # после 1-го нуджа ждём 45с, после 2-го — 90с
    if interval_idx < 0 or interval_idx >= len(NUDGE_INTERVALS):
        return
    delay = NUDGE_INTERVALS[interval_idx]
    await asyncio.sleep(delay)
    if user_id not in _nudge_timers:
        return
    current_stage = _nudge_count.get(user_id, 0)
    if current_stage != stage:
        return
    _nudge_count[user_id] = stage + 1
    nudge_idx = (stage) % len(msg.ORDER_NUDGES)
    nudge_text = msg.ORDER_NUDGES[nudge_idx]
    try:
        await bot.send_message(
            chat_id,
            nudge_text.format(url=WEBSITE_URL),
            reply_markup=kb.kb_ai_chat(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Nudge send error: {e}")
        return
    _nudge_timers[user_id] = asyncio.create_task(
        _delayed_nudge(user_id, chat_id, bot)
    )


async def _update_bot_msg_time(user_id: int) -> None:
    await db.update_last_bot_message(user_id)


async def _maybe_nudge_to_order(user_id: int, message: Message) -> None:
    """Подталкивает к заказу. Запускает цепочку из MAX_NUDGES нуджей с задержками."""
    count = _nudge_count.get(user_id, 0) + 1
    _nudge_count[user_id] = count
    nudge_idx = (count - 1) % len(msg.ORDER_NUDGES)
    nudge_text = msg.ORDER_NUDGES[nudge_idx]
    await message.answer(
        nudge_text.format(url=WEBSITE_URL),
        reply_markup=kb.kb_ai_chat(),
        parse_mode="Markdown"
    )
    _cancel_nudge_timers(user_id)
    if count < MAX_NUDGES:
        _nudge_timers[user_id] = asyncio.create_task(
            _delayed_nudge(user_id, message.chat.id, message.bot)
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

    # Отправляем фото товаров
    await _update_bot_msg_time(call.from_user.id)
    await call.message.answer(msg.PRODUCT_PHOTOS_HEADER, parse_mode="Markdown")
    await send_product_photos(call.message.chat.id, call.bot)

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
    await process_ai_message(message, state, bot)


async def process_ai_message(message: Message, state: FSMContext, bot: Bot) -> bool:
    """Общая логика AI-обработки для любого входящего сообщения."""
    user_id = message.from_user.id
    text = message.text or ""
    _cancel_nudge_timers(user_id)

    await db.log_message(user_id, "incoming", text)

    user = await db.get_user(user_id)
    if user and user.get("stage") in ("manager_takeover", "waiting_manager"):
        await route_to_manager(user_id, text, message)
        return False

    await bot.send_chat_action(message.chat.id, "typing")

    faq_answer = _check_faq(text)
    if faq_answer:
        await db.log_message(user_id, "outgoing", faq_answer)
        await message.answer(faq_answer, reply_markup=kb.kb_ai_chat(), parse_mode="Markdown")
        await _update_bot_msg_time(user_id)
        await _maybe_nudge_to_order(user_id, message)
        return True

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
        await _maybe_nudge_to_order(user_id, message)

        history_len = len(gc.get_history(user_id))
        if history_len >= 6 and user and not user.get("full_name"):
            await state.set_state(Funnel.get_name)
            await message.answer(msg.GET_NAME, parse_mode="Markdown")
    else:
        confusion = (user.get("ai_confusion_count") or 0) + 1 if user else 1
        await db.update_user(user_id, ai_confusion_count=confusion)

        if confusion >= AI_CONFUSION_THRESHOLD:
            await db.update_user(user_id, stage="waiting_manager")
            await takeover.notify_admins_waiting(
                user_id, f"ИИ не справился {confusion} раза подряд. Последний вопрос: {text}"
            )
            await message.answer(msg.MANAGER_CONNECTED, parse_mode="Markdown")
        else:
            await message.answer(msg.FALLBACK_AI, reply_markup=kb.kb_ai_chat(), parse_mode="Markdown")
    return True


# ══════════════════════════════════════════════
#  ФОТО — РАСПОЗНАВАНИЕ
# ══════════════════════════════════════════════

@router.message(F.photo)
async def msg_photo(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    _cancel_nudge_timers(user_id)

    user = await db.get_user(user_id)
    if user and user.get("stage") in ("manager_takeover", "waiting_manager"):
        await route_to_manager(user_id, "[Клиент прислал фото]", message)
        return

    await bot.send_chat_action(message.chat.id, "typing")
    await state.set_state(Funnel.ai_chat)
    await db.log_message(user_id, "incoming", "[Фото]")

    # Скачиваем фото
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        buf = await bot.download_file(file.file_path)
        image_bytes = buf.getvalue()
        image_b64 = base64.b64encode(image_bytes).decode()
    except Exception as e:
        logger.error(f"Photo download error: {e}")
        await message.answer(msg.VISION_FAIL)
        await _notify_admin_needs_help(bot, user_id, "[Ошибка загрузки фото]", 0)
        return

    # Распознаём через GigaChat Vision
    if gigachat_client:
        history = gc.get_history(user_id)
        ai_response = await gigachat_client.chat_with_vision(history, message.caption or "", image_b64)
        if ai_response:
            gc.add_to_history(user_id, "user", f"[Фото] {message.caption or ''}")
            gc.add_to_history(user_id, "assistant", ai_response)
            await db.update_user(user_id, ai_confusion_count=0)
            await _update_bot_msg_time(user_id)
            await db.log_message(user_id, "outgoing", ai_response)
            await message.answer(ai_response, reply_markup=kb.kb_ai_chat(), parse_mode="Markdown")
            await _maybe_nudge_to_order(user_id, message)
            return

    # Vision не сработал
    await message.answer(msg.VISION_FAIL)
    await db.update_user(user_id, stage="waiting_manager")
    await takeover.notify_admins_waiting(
        user_id, f"Прислал фото, ИИ его не разобрал. Подпись: {message.caption or '—'}"
    )


# ══════════════════════════════════════════════
#  ФОТО ТОВАРОВ
# ══════════════════════════════════════════════

async def send_product_photos(chat_id: int, bot: Bot):
    """Отправляет фото товаров после презентации."""
    for url, caption in PRODUCT_IMAGES:
        try:
            await bot.send_photo(chat_id, url, caption=caption, parse_mode="Markdown")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Product photo send error: {e}")
            await bot.send_message(chat_id, f"👉 [{caption}]({url})", parse_mode="Markdown")


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
    # waiting_manager, а не manager_takeover: менеджер диалог ещё не взял.
    # Раньше клиент сразу проваливался в тишину и застревал там навсегда.
    await db.update_user(user_id, stage="waiting_manager")
    await call.message.answer(msg.MANAGER_CONNECTED, parse_mode="Markdown")
    await takeover.notify_admins_waiting(user_id, "Нажал «Позвать менеджера»")


# ══════════════════════════════════════════════
#  МАРШРУТИЗАЦИЯ К МЕНЕДЖЕРУ
# ══════════════════════════════════════════════

# user_id -> сколько раз уже извинились, пока менеджер не подошёл
_waiting_acks: dict[int, int] = {}


async def route_to_manager(user_id: int, text: str, message: Message) -> None:
    """Клиент в режиме менеджера: либо релеим ведущему админу, либо зовём свободного."""
    await db.log_message(user_id, "incoming", text)

    if await takeover.relay_to_admin(user_id, text):
        return

    # Диалог ещё никто не взял — дёргаем всех админов
    await takeover.notify_admins_waiting(user_id, text)

    acks = _waiting_acks.get(user_id, 0)
    if acks == 0:
        await message.answer(msg.MANAGER_WAITING_ACK, parse_mode="Markdown")
    _waiting_acks[user_id] = acks + 1


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

async def _send_admins(text: str, user_id: int, username: str = None) -> None:
    """Одна точка отправки уведомлений — с фолбэком, чтобы ничего не терялось."""
    markup = kb.kb_notify_admin(user_id, username)
    for admin_id in ADMIN_IDS:
        await notifier.send_to_admin(admin_id, text, markup)


async def _notify_admin_new_lead(bot: Bot, user_id: int):
    user = await db.get_user(user_id)
    if not user:
        return
    text = msg.ADMIN_NOTIFICATION_NEW_LEAD.format(
        full_name=escape_md(user.get("full_name") or user.get("first_name") or "Неизвестно"),
        username=escape_md(user.get("username") or "без username"),
        occasion=user.get("occasion") or "—",
        recipient=user.get("recipient") or "—",
        budget=user.get("budget") or "—",
        created_at=_now_str(),
    )
    await _send_admins(text, user_id, user.get("username"))


async def _notify_admin_contact(
    bot: Bot, user_id: int, name: str, phone: str,
    occasion: str, recipient: str, budget: str, username: str
):
    user = await db.get_user(user_id)
    product_interest = user.get("product_interest", "Карта звёздного неба") if user else "—"
    text = msg.ADMIN_NOTIFICATION_CONTACT.format(
        full_name=escape_md(name),
        username=escape_md(username or "без username"),
        telegram_id=user_id,
        phone=escape_md(phone),
        occasion=occasion or "—",
        recipient=recipient or "—",
        budget=budget or "—",
        product_interest=product_interest or "—",
        created_at=_now_str(),
    )
    await _send_admins(text, user_id, username)


async def _notify_admin_needs_help(bot: Bot, user_id: int, last_message: str, count: int):
    """Оставлено для совместимости — вся логика теперь в takeover."""
    await takeover.notify_admins_waiting(user_id, last_message[:300])


async def _notify_admin_lead_no_phone(bot: Bot, user_id: int):
    user = await db.get_user(user_id)
    if not user:
        return
    name = escape_md(user.get("full_name") or user.get("first_name") or "Неизвестно")
    username = user.get("username") or ""
    text = (
        f"👤 *Лид прошёл воронку без телефона*\n\n"
        f"Имя: {name} (@{escape_md(username or 'без username')})\n"
        f"ID: `{user_id}`\n"
        f"Повод: {user.get('occasion') or '—'}\n"
        f"Бюджет: {user.get('budget') or '—'}"
    )
    await _send_admins(text, user_id, username)


def _now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%d.%m.%Y %H:%M")


# ══════════════════════════════════════════════
#  НАПОМИНАНИЯ О ВАЖНОЙ ДАТЕ
# ══════════════════════════════════════════════

@router.callback_query(F.data == "reminder_start")
async def cb_reminder_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Reminder.set_event)
    await call.message.answer(
        "⏰ *Напомню о важной дате!*\n\n"
        "Введи название события, например:\n"
        "_День рождения мамы_, _Годовщина_, _День свадьбы_",
        parse_mode="Markdown"
    )


@router.message(Reminder.set_event)
async def msg_reminder_event(message: Message, state: FSMContext):
    event = message.text.strip()
    if len(event) < 2 or len(event) > 100:
        await message.answer("Название слишком короткое или длинное. Попробуй ещё раз:")
        return
    await state.update_data(reminder_event=event)
    await state.set_state(Reminder.set_date)
    await message.answer(
        f"📅 *Отлично!* Запомнил: _{event}_\n\n"
        "Теперь введи дату события в формате *ДД.ММ* или *ДД.ММ.ГГГГ*\n\n"
        "Примеры: `25.03` или `25.03.1990`\n"
        "_Если введёшь только день и месяц — буду напоминать каждый год_ 🔁",
        parse_mode="Markdown"
    )


@router.message(Reminder.set_date)
async def msg_reminder_date(message: Message, state: FSMContext):
    import re
    text = message.text.strip()
    if re.fullmatch(r"\d{2}\.\d{2}", text):
        event_date = text
    elif re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", text):
        event_date = text
    else:
        await message.answer(
            "Введи дату в формате *ДД.ММ* или *ДД.ММ.ГГГГ* (например: 25.03 или 25.03.1990)",
            parse_mode="Markdown"
        )
        return
    await state.update_data(reminder_date=event_date)
    await state.set_state(Reminder.set_days)
    await message.answer(
        f"✅ Дата: *{event_date}*\n\nЗа сколько дней напомнить?",
        reply_markup=kb.kb_reminder_days(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("remind_days_"), Reminder.set_days)
async def cb_reminder_days(call: CallbackQuery, state: FSMContext):
    await call.answer()
    days = int(call.data.split("remind_days_")[1])
    data = await state.get_data()
    event = data.get("reminder_event", "")
    event_date = data.get("reminder_date", "")

    await db.add_reminder(
        telegram_id=call.from_user.id,
        platform="telegram",
        event_name=event,
        event_date=event_date,
        remind_days_before=days,
    )
    await state.set_state(Funnel.welcome)
    await call.message.edit_text(
        f"🎉 *Напоминание сохранено!*\n\n"
        f"📅 Событие: *{event}*\n"
        f"📆 Дата: *{event_date}*\n"
        f"⏰ Напомню за *{days} дн.* до события\n\n"
        f"_Я также предложу идеи подарков! 🎁_",
        reply_markup=kb.kb_reminder_saved(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "my_reminders")
async def cb_my_reminders(call: CallbackQuery, state: FSMContext):
    await call.answer()
    reminders = await db.get_user_reminders(call.from_user.id)
    if not reminders:
        await call.message.answer(
            "У тебя пока нет активных напоминаний.\n\nНажми ⏰, чтобы добавить!",
            reply_markup=kb.kb_reminder_saved()
        )
        return
    await call.message.answer(
        "📋 *Твои напоминания:*\n\n"
        "Нажми на кнопку чтобы удалить напоминание:",
        reply_markup=kb.kb_my_reminders(reminders),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("del_reminder_"))
async def cb_del_reminder(call: CallbackQuery, state: FSMContext):
    await call.answer()
    reminder_id = int(call.data.split("del_reminder_")[1])
    await db.deactivate_reminder(reminder_id, call.from_user.id)
    await call.message.edit_text(
        "🗑 Напоминание удалено.",
        reply_markup=kb.kb_reminder_saved()
    )


def escape_md(text: str) -> str:
    """Экранирует спецсимволы legacy Markdown (parse_mode='Markdown').

    Раньше экранировалось по правилам MarkdownV2 — слэши перед . - ! ( )
    в legacy-режиме невалидны, из-за них Telegram отклонял сообщение целиком.
    """
    return re.sub(r"([_*`\[])", r"\\\1", text or "")
