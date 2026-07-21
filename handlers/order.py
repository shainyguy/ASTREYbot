"""Оформление заказа: дата → место → надпись → оформление → формат → доставка → оплата.

Бот доводит клиента до оплаты сам. На любом шаге человек может задать вопрос —
бот отвечает (FAQ или ИИ) и возвращает к тому же шагу, а не записывает вопрос
в заказ. Если совсем не понимает — зовёт менеджера, но никогда не молчит.
"""
import logging
import re
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
import messages as msg
import keyboards as kb
import mockup
import notifier
import order_parse as parse
import recent
import takeover
from states import Funnel, Order
from config import ADMIN_IDS, format_info, delivery_info, POSTCARD_PRICE

router = Router()
logger = logging.getLogger(__name__)

# Сколько раз подряд не смогли разобрать ответ — потом зовём менеджера
MAX_RETRIES = 2


# ══════════════════════════════════════════════
#  РАСПОЗНАВАНИЕ ГОТОВНОСТИ КУПИТЬ
# ══════════════════════════════════════════════

_BUY_INTENT = re.compile(
    r"(хочу|готов[аы]?|давай|буду|можно)\s+(заказ|куп|оформ|брать|взять)"
    r"|^(беру|заказываю|покупаю|оформляй|оформить|заказать|купить)\b"
    r"|как (мне )?(заказать|оплатить|купить|оформить)"
    r"|где (оплатить|заказать|купить)"
    r"|хочу (эт[оу]|такую|карту)"
    r"|мне подходит|согласен|уговорил",
    re.IGNORECASE,
)


def detect_buy_intent(text: str) -> bool:
    return bool(_BUY_INTENT.search(text or ""))


# ══════════════════════════════════════════════
#  ОТВЕТ НА ВОПРОС ПОСРЕДИ ОФОРМЛЕНИЯ
# ══════════════════════════════════════════════

async def answer_question(user_id: int, text: str) -> str:
    """Ответ на вопрос: сначала готовые ответы, потом ИИ.

    Пустая строка — не смогли ответить вообще.
    """
    ready = msg.find_faq(text)
    if ready:
        return ready

    from handlers import funnel
    if funnel.gigachat_client:
        import gigachat as gc
        history = gc.get_history(user_id)
        reply = await funnel.gigachat_client.chat(history, text)
        if reply:
            gc.add_to_history(user_id, "user", text)
            gc.add_to_history(user_id, "assistant", reply)
            return reply
    return ""


async def handle_question(message: Message, state: FSMContext, step: str) -> bool:
    """Отвечает на вопрос и возвращает клиента к текущему шагу.

    → True, если это был вопрос и мы его обработали.
    """
    text = message.text or ""
    if not (parse.looks_like_question(text, step) or parse.mentions_faq_topic(text)):
        return False

    user_id = message.from_user.id
    recent.remember(user_id, "incoming", text)

    reply = await answer_question(user_id, text)
    if not reply:
        # Не смогли ответить. Сразу сдаваться нельзя — заказ оборвётся,
        # поэтому честно признаёмся и продолжаем. Менеджера зовём, только
        # если не отвечаем уже второй раз подряд.
        data = await state.get_data()
        misses = data.get("answer_misses", 0) + 1
        await state.update_data(answer_misses=misses)

        if misses >= 2:
            await message.answer(msg.ORDER_STUCK, parse_mode="Markdown")
            await db.update_user(user_id, stage="waiting_manager")
            await takeover.notify_admins_waiting(
                user_id, f"Вопрос при оформлении заказа: {text}"
            )
            return True

        await message.answer(msg.ORDER_ANSWER_LATER, parse_mode="Markdown")
        await message.answer(
            msg.ORDER_STEP_PROMPTS.get(step, "Продолжим оформление 😊"),
            reply_markup=kb.kb_order_cancel(),
            parse_mode="Markdown",
        )
        return True

    await state.update_data(answer_misses=0)
    await message.answer(reply, parse_mode="Markdown")
    recent.remember(user_id, "outgoing", reply)
    await message.answer(
        msg.ORDER_STEP_PROMPTS.get(step, "Продолжим оформление 😊"),
        reply_markup=kb.kb_order_cancel(),
        parse_mode="Markdown",
    )
    return True


async def _retry_or_manager(message: Message, state: FSMContext,
                            step: str, retry_text: str) -> None:
    """Не разобрали ответ: пару раз переспрашиваем, потом зовём менеджера."""
    data = await state.get_data()
    key = f"retries_{step}"
    count = data.get(key, 0) + 1
    await state.update_data(**{key: count})

    if count > MAX_RETRIES:
        await message.answer(msg.ORDER_STUCK, parse_mode="Markdown")
        await db.update_user(message.from_user.id, stage="waiting_manager")
        await takeover.notify_admins_waiting(
            message.from_user.id,
            f"Застрял на шаге «{step}» при оформлении. Последний ответ: {message.text}",
        )
        return

    await message.answer(retry_text, reply_markup=kb.kb_order_cancel(), parse_mode="Markdown")


# ══════════════════════════════════════════════
#  СТАРТ
# ══════════════════════════════════════════════

@router.callback_query(F.data == "order_start")
async def cb_order_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await begin_order(call.from_user.id, call.message, state)


async def begin_order(user_id: int, target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(Order.event_date)
    await state.update_data(order_edit_field=None, occasion=data.get("occasion"))
    await db.update_user(user_id, stage="ordering")
    await target.answer(msg.ORDER_START, reply_markup=kb.kb_order_cancel(), parse_mode="Markdown")


@router.callback_query(F.data == "order_cancel")
async def cb_order_cancel(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Funnel.ai_chat)
    await db.update_user(call.from_user.id, stage="ai_chat")
    await call.message.answer(msg.ORDER_CANCELLED, reply_markup=kb.kb_ai_chat(), parse_mode="Markdown")


# ══════════════════════════════════════════════
#  ШАГ 1 — ДАТА (строгий формат)
# ══════════════════════════════════════════════

@router.message(Order.event_date, F.text)
async def msg_event_date(message: Message, state: FSMContext):
    normalized = parse.parse_date(message.text)
    if normalized:
        await _advance(message, state, "event_date", normalized,
                       Order.event_place, msg.ORDER_ASK_PLACE)
        return
    # Не дата — либо вопрос, либо опечатка
    if await handle_question(message, state, "event_date"):
        return
    await _retry_or_manager(message, state, "event_date", msg.ORDER_DATE_RETRY)


# ══════════════════════════════════════════════
#  ШАГИ 2-4 — МЕСТО, НАДПИСЬ, ОФОРМЛЕНИЕ
# ══════════════════════════════════════════════

@router.message(Order.event_place, F.text)
async def msg_event_place(message: Message, state: FSMContext):
    if await handle_question(message, state, "event_place"):
        return
    await _advance(message, state, "event_place", message.text.strip(),
                   Order.phrase, msg.ORDER_ASK_PHRASE)


@router.message(Order.phrase, F.text)
async def msg_phrase(message: Message, state: FSMContext):
    if await handle_question(message, state, "phrase"):
        return
    await _advance(message, state, "phrase", message.text.strip(),
                   Order.design, msg.ORDER_ASK_DESIGN)


@router.message(Order.design, F.photo)
async def msg_design_photo(message: Message, state: FSMContext):
    """Дизайн принимаем только текстом — по фото дизайнеру работать нечем."""
    await message.answer(msg.ORDER_DESIGN_NOT_PHOTO, parse_mode="Markdown")


@router.message(Order.design, F.text)
async def msg_design(message: Message, state: FSMContext):
    if await handle_question(message, state, "design"):
        return

    design = message.text.strip()
    await state.update_data(design=design)
    recent.remember(message.from_user.id, "incoming", design)

    data = await state.get_data()
    if data.get("order_edit_field") == "design":
        await state.update_data(order_edit_field=None)
        await _show_summary(message, state)
        return

    await state.set_state(Order.choose_format)
    await message.answer(msg.ORDER_ASK_FORMAT, reply_markup=kb.kb_order_format(),
                         parse_mode="Markdown")


async def _advance(message: Message, state: FSMContext, field: str,
                   value: str, next_state, next_text: str) -> None:
    await state.update_data(**{field: value})
    recent.remember(message.from_user.id, "incoming", value)

    data = await state.get_data()
    if data.get("order_edit_field") == field:
        await state.update_data(order_edit_field=None)
        await _show_summary(message, state)
        return

    await state.set_state(next_state)
    await message.answer(next_text, reply_markup=kb.kb_order_cancel(), parse_mode="Markdown")


# ══════════════════════════════════════════════
#  ШАГ 5 — ФОРМАТ
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("order_fmt_"))
async def cb_order_format(call: CallbackQuery, state: FSMContext):
    await call.answer()
    choice = call.data.split("order_fmt_", 1)[1]

    if choice == "help":
        await call.message.answer(
            "Подскажу 😊\n\n"
            "⚡ *Электронно* — если нужно срочно или распечатаете сами.\n"
            "🖼 *А4 в рамке* — универсально, хорошо смотрится на полке или столе.\n"
            "🖼 *А3 в рамке* — если это главный подарок и хочется повесить на стену.\n\n"
            "Чаще всего берут А4 — золотая середина. Какой возьмём?",
            reply_markup=kb.kb_order_format(),
            parse_mode="Markdown",
        )
        return

    await _apply_format(call.message, state, choice, user_id=call.from_user.id)


@router.message(Order.choose_format, F.text)
async def msg_choose_format(message: Message, state: FSMContext):
    """Формат словами: «давайте А4», «электронный».

    Без этого обработчика бот молчал: сообщение не подходило ни одному
    роутеру и просто проваливалось в пустоту.
    """
    fmt = parse.parse_format(message.text)
    if fmt:
        await _apply_format(message, state, fmt, user_id=message.from_user.id)
        return
    if await handle_question(message, state, "format"):
        return
    await _retry_or_manager(message, state, "format", msg.ORDER_FORMAT_RETRY)


async def _apply_format(target: Message, state: FSMContext, fmt: str, user_id: int) -> None:
    await state.update_data(order_format=fmt)
    data = await state.get_data()

    if data.get("order_edit_field") == "format":
        await state.update_data(order_edit_field=None)
        await _show_summary(target, state, user_id=user_id)
        return

    # Электронный формат везти не нужно — сразу к открытке
    if fmt == "electronic":
        await state.update_data(delivery=None)
        await _offer_postcard(target, state)
        return

    await state.set_state(Order.choose_delivery)
    await target.answer(msg.ORDER_ASK_DELIVERY, reply_markup=kb.kb_order_delivery(),
                        parse_mode="Markdown")


# ══════════════════════════════════════════════
#  ШАГ 6 — ДОСТАВКА (для форматов в рамке)
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("order_dlv_"))
async def cb_order_delivery(call: CallbackQuery, state: FSMContext):
    await call.answer()
    choice = call.data.split("order_dlv_", 1)[1]
    await _apply_delivery(call.message, state, choice, user_id=call.from_user.id)


@router.message(Order.choose_delivery, F.text)
async def msg_choose_delivery(message: Message, state: FSMContext):
    choice = parse.parse_delivery(message.text)
    if choice:
        await _apply_delivery(message, state, choice, user_id=message.from_user.id)
        return
    if await handle_question(message, state, "delivery"):
        return
    await _retry_or_manager(message, state, "delivery", msg.ORDER_DELIVERY_RETRY)


async def _apply_delivery(target: Message, state: FSMContext, choice: str, user_id: int) -> None:
    await state.update_data(delivery=choice)
    data = await state.get_data()

    if data.get("order_edit_field") == "delivery":
        await state.update_data(order_edit_field=None)
        await _show_summary(target, state, user_id=user_id)
        return

    await _offer_postcard(target, state)


# ══════════════════════════════════════════════
#  ДОПРОДАЖА — ОТКРЫТКА
# ══════════════════════════════════════════════

async def _offer_postcard(target: Message, state: FSMContext) -> None:
    await state.set_state(Order.awaiting_payment)
    await target.answer(msg.POSTCARD_UPSELL, reply_markup=kb.kb_postcard(), parse_mode="Markdown")


@router.callback_query(F.data == "postcard_yes")
async def cb_postcard_yes(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.update_data(postcard=1, awaiting_postcard_text=True)
    await call.message.answer(msg.POSTCARD_ASK_TEXT, parse_mode="Markdown")


@router.callback_query(F.data == "postcard_no")
async def cb_postcard_no(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.update_data(postcard=0)
    await _show_summary(call.message, state, user_id=call.from_user.id)


@router.message(Order.awaiting_payment, F.text)
async def msg_awaiting_payment(message: Message, state: FSMContext):
    """На шаге оплаты ждём текст открытки, всё остальное — вопросы."""
    data = await state.get_data()

    if data.get("awaiting_postcard_text"):
        await state.update_data(
            postcard_text=message.text.strip(),
            awaiting_postcard_text=False,
        )
        await message.answer(msg.POSTCARD_ADDED, parse_mode="Markdown")
        await _show_summary(message, state)
        return

    # Клиент что-то спрашивает у оплаты — отвечаем, не теряя заказ
    user_id = message.from_user.id
    text = message.text or ""
    recent.remember(user_id, "incoming", text)

    reply = await answer_question(user_id, text)
    if reply:
        await message.answer(reply, reply_markup=kb.kb_order_edit(), parse_mode="Markdown")
        recent.remember(user_id, "outgoing", reply)
        return

    await message.answer(msg.ORDER_STUCK, parse_mode="Markdown")
    await db.update_user(user_id, stage="waiting_manager")
    await takeover.notify_admins_waiting(user_id, f"Вопрос перед оплатой: {text}")


# ══════════════════════════════════════════════
#  СВОДКА + ОПЛАТА
# ══════════════════════════════════════════════

def _calc(data: dict) -> dict:
    """Считает суммы. По ссылке платится только карта, остальное — доплата."""
    fmt_key = data.get("order_format", "electronic")
    fmt_name, base, pay_url = format_info(fmt_key)

    extras, extras_sum = [], 0
    if int(data.get("postcard") or 0):
        extras.append(f"открытка {POSTCARD_PRICE}₽")
        extras_sum += POSTCARD_PRICE

    dlv_key = data.get("delivery")
    dlv_name, dlv_price = delivery_info(dlv_key) if dlv_key else ("", 0)
    if dlv_price:
        extras.append(f"доставка {dlv_price}₽")
        extras_sum += dlv_price

    return {
        "fmt_key": fmt_key, "fmt_name": fmt_name, "base": base, "pay_url": pay_url,
        "dlv_key": dlv_key, "dlv_name": dlv_name, "dlv_price": dlv_price,
        "extras": extras, "extras_sum": extras_sum, "total": base + extras_sum,
    }


def _extras_phrase(c: dict) -> str:
    """«доставка 500₽» или «открытка 190₽ и доставка 500₽ — итого 690₽»."""
    if len(c["extras"]) == 1:
        return c["extras"][0]
    return f"{' и '.join(c['extras'])} — итого {c['extras_sum']}₽"


async def _show_summary(target: Message, state: FSMContext, user_id: int = None) -> None:
    data = await state.get_data()
    uid = user_id or target.chat.id
    c = _calc(data)

    postcard = int(data.get("postcard") or 0)
    postcard_line = f"💌 Открытка: _{data.get('postcard_text', 'с вашим текстом')}_\n" if postcard else ""
    delivery_line = f"📦 Получение: *{c['dlv_name']}*\n" if c["dlv_name"] else ""
    extras_line = msg.ORDER_EXTRAS_NOTE.format(extras=_extras_phrase(c)) if c["extras"] else ""

    user = await db.get_user(uid) or {}
    fields = dict(
        format=c["fmt_key"],
        event_date=data.get("event_date", ""),
        event_place=data.get("event_place", ""),
        phrase=data.get("phrase", ""),
        design=data.get("design", ""),
        postcard=postcard,
        amount=c["total"],
    )

    # Правка уже собранного заказа обновляет ту же запись, иначе каждое
    # исправление плодило дубль и повторное уведомление админу
    existing_id = data.get("order_id")
    if existing_id:
        await db.update_order(existing_id, **fields)
        order_id, is_new = existing_id, False
    else:
        order_id = await db.create_order(
            uid,
            platform="vk" if uid < 0 else "telegram",
            product="Карта звёздного неба",
            full_name=user.get("full_name") or user.get("first_name") or "",
            phone=user.get("phone") or "",
            status="awaiting_payment",
            **fields,
        )
        await state.update_data(order_id=order_id)
        is_new = True

    summary = msg.ORDER_SUMMARY.format(
        event_date=data.get("event_date", "—"),
        event_place=data.get("event_place", "—"),
        phrase=data.get("phrase", "—"),
        design=data.get("design", "—"),
        format_name=c["fmt_name"],
        delivery_line=delivery_line,
        postcard_line=postcard_line,
        amount=c["base"],
        extras_line=extras_line,
    )
    await target.answer(summary, reply_markup=kb.kb_order_pay(c["pay_url"], order_id),
                        parse_mode="Markdown")
    await target.answer(
        msg.ORDER_PAID_HINT.format(delivery_line=_delivery_line(c["fmt_key"], c["dlv_key"])),
        parse_mode="Markdown",
    )

    if is_new:
        await _notify_admin_order(order_id, uid)


def _delivery_line(fmt_key: str, dlv_key: str = None) -> str:
    if fmt_key == "electronic":
        return "Присылаем готовый PDF на почту — в течение часа после утверждения ⚡"
    if dlv_key == "pickup":
        return "Печатаем, оформляем в рамку и пишем вам, когда можно забрать — м. Сокольники 🚶"
    return "Печатаем, оформляем в рамку и отправляем почтой — 3-7 рабочих дней 📮"


# ══════════════════════════════════════════════
#  ПРАВКИ
# ══════════════════════════════════════════════

@router.callback_query(F.data == "order_edit")
async def cb_order_edit(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Что поправим? 😊", reply_markup=kb.kb_order_edit())


@router.callback_query(F.data.startswith("order_re_"))
async def cb_order_redo(call: CallbackQuery, state: FSMContext):
    await call.answer()
    field = call.data.split("order_re_", 1)[1]

    steps = {
        "date": ("event_date", Order.event_date, msg.ORDER_STEP_PROMPTS["event_date"]),
        "place": ("event_place", Order.event_place, msg.ORDER_STEP_PROMPTS["event_place"]),
        "phrase": ("phrase", Order.phrase, msg.ORDER_STEP_PROMPTS["phrase"]),
        "design": ("design", Order.design, msg.ORDER_STEP_PROMPTS["design"]),
    }

    if field == "format":
        await state.update_data(order_edit_field="format")
        await state.set_state(Order.choose_format)
        await call.message.answer(msg.ORDER_ASK_FORMAT, reply_markup=kb.kb_order_format(),
                                  parse_mode="Markdown")
        return

    if field == "delivery":
        await state.update_data(order_edit_field="delivery")
        await state.set_state(Order.choose_delivery)
        await call.message.answer(msg.ORDER_ASK_DELIVERY, reply_markup=kb.kb_order_delivery(),
                                  parse_mode="Markdown")
        return

    if field in steps:
        state_field, fsm_state, prompt = steps[field]
        await state.update_data(order_edit_field=state_field)
        await state.set_state(fsm_state)
        await call.message.answer(prompt, reply_markup=kb.kb_order_cancel(), parse_mode="Markdown")


# ══════════════════════════════════════════════
#  ПОДТВЕРЖДЕНИЕ ОПЛАТЫ
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("order_paid_"))
async def cb_order_paid(call: CallbackQuery, state: FSMContext):
    await call.answer("Спасибо! 💛")
    order_id = int(call.data.split("order_paid_", 1)[1])
    user_id = call.from_user.id

    await db.update_order(order_id, status="paid")
    await state.set_state(Funnel.ai_chat)
    await db.update_user(user_id, stage="ai_chat")

    user = await db.get_user(user_id) or {}
    name = user.get("full_name") or user.get("first_name") or "друг"

    await call.message.answer(
        msg.ORDER_THANKS.format(name=name),
        reply_markup=kb.kb_after_order(),
        parse_mode="Markdown",
    )

    order = await db.get_order(order_id) or {}
    for admin_id in ADMIN_IDS:
        await notifier.send_to_admin(
            admin_id,
            msg.ADMIN_ORDER_PAID.format(
                order_id=order_id,
                name=takeover.escape(name),
                amount=order.get("amount", "—"),
            ),
            kb.kb_admin_order(order_id, user_id),
        )


# ══════════════════════════════════════════════
#  МАКЕТ: РЕАКЦИЯ КЛИЕНТА
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("mockup_ok_"))
async def cb_mockup_ok(call: CallbackQuery, state: FSMContext):
    await call.answer("Спасибо! 💛")
    order_id = int(call.data.split("mockup_ok_", 1)[1])
    order = await db.get_order(order_id) or {}

    await mockup.on_approved(order_id, call.from_user.id)
    await state.set_state(Funnel.ai_chat)
    await call.message.answer(
        msg.MOCKUP_APPROVED.format(next_step=mockup.next_step_text(order)),
        reply_markup=kb.kb_after_order(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("mockup_fix_"))
async def cb_mockup_fix(call: CallbackQuery, state: FSMContext):
    await call.answer()
    order_id = int(call.data.split("mockup_fix_", 1)[1])
    await state.set_state(Order.mockup_comment)
    await state.update_data(mockup_order_id=order_id)
    await call.message.answer(msg.MOCKUP_ASK_COMMENT, parse_mode="Markdown")


@router.message(Order.mockup_comment, F.text)
async def msg_mockup_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("mockup_order_id")
    if not order_id:
        order = await mockup.active_order(message.from_user.id)
        order_id = order["id"] if order else None

    if order_id:
        await mockup.on_revision(order_id, message.from_user.id, message.text)

    await state.set_state(Funnel.ai_chat)
    await message.answer(msg.MOCKUP_COMMENT_SENT, reply_markup=kb.kb_after_order(),
                         parse_mode="Markdown")


async def handle_mockup_reply(message: Message, state: FSMContext) -> bool:
    """Клиент написал в чат, пока висит неотвеченный макет.

    «всё хорошо» → утверждаем, любой другой текст → считаем правками.
    Вызывается из общего AI-обработчика до похода в GigaChat.
    """
    order = await mockup.active_order(message.from_user.id)
    if not order:
        return False

    text = message.text or ""
    reaction = mockup.read_reaction(text)

    if reaction == "approve":
        await mockup.on_approved(order["id"], message.from_user.id)
        await message.answer(
            msg.MOCKUP_APPROVED.format(next_step=mockup.next_step_text(order)),
            reply_markup=kb.kb_after_order(),
            parse_mode="Markdown",
        )
        return True

    if reaction == "revision":
        await mockup.on_revision(order["id"], message.from_user.id, text)
        await message.answer(msg.MOCKUP_COMMENT_SENT, reply_markup=kb.kb_after_order(),
                             parse_mode="Markdown")
        return True

    # Короткая непонятная реплика — уточняем, не гадаем
    await message.answer(
        "Подскажите, всё в порядке с макетом или что-то поправить? 😊",
        reply_markup=kb.kb_mockup_review(order["id"]),
    )
    return True


@router.callback_query(F.data.startswith("ord_status_"))
async def cb_order_status(call: CallbackQuery):
    from handlers.admin import is_admin
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    _, _, order_id, status = call.data.split("_", 3)
    await db.update_order(int(order_id), status=status)
    labels = {"paid": "Оплачен ✅", "mockup_sent": "Макет отправлен 🎨", "done": "Выполнен 🏆"}
    await call.answer(f"Заказ #{order_id}: {labels.get(status, status)}", show_alert=True)


# ══════════════════════════════════════════════
#  КАРТОЧКА ЗАКАЗА АДМИНУ
# ══════════════════════════════════════════════

async def _notify_admin_order(order_id: int, user_db_id: int) -> None:
    order = await db.get_order(order_id)
    if not order:
        return

    name, source = await takeover.describe_user(user_db_id)
    user = await db.get_user(user_db_id) or {}
    fmt_name, base, _ = format_info(order.get("format", "electronic"))

    extras = []
    if order.get("postcard"):
        extras.append(f"открытка {POSTCARD_PRICE}₽")
    total = order.get("amount", base)
    if total - base - (POSTCARD_PRICE if order.get("postcard") else 0) > 0:
        extras.append("доставка 500₽")

    postcard_line = ""
    if extras:
        postcard_line = f"➕ Доплата: {', '.join(extras)} — *свяжись с клиентом*\n"

    text = msg.ADMIN_NEW_ORDER.format(
        order_id=order_id,
        name=takeover.escape(name),
        contact=source,
        phone=user.get("phone") or "не оставил",
        event_date=takeover.escape(order.get("event_date") or "—"),
        event_place=takeover.escape(order.get("event_place") or "—"),
        phrase=takeover.escape(order.get("phrase") or "—"),
        design=takeover.escape(order.get("design") or "—"),
        format_name=fmt_name,
        postcard_line=postcard_line,
        amount=base,
        created_at=datetime.now().strftime("%d.%m.%Y %H:%M"),
    )

    for admin_id in ADMIN_IDS:
        await notifier.send_to_admin(admin_id, text, kb.kb_admin_order(order_id, user_db_id))
