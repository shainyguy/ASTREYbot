"""Оформление заказа: дата → место → надпись → дизайн → формат → оплата.

Бот доводит клиента до оплаты сам, без участия менеджера. Менеджер получает
готовую карточку заказа и берётся за макет.
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
import notifier
import recent
import takeover
from states import Funnel, Order
from config import ADMIN_IDS, format_info

router = Router()
logger = logging.getLogger(__name__)

POSTCARD_PRICE = 190


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
    """Клиент словами показал, что готов оформлять."""
    return bool(_BUY_INTENT.search(text or ""))


# ══════════════════════════════════════════════
#  СТАРТ
# ══════════════════════════════════════════════

@router.callback_query(F.data == "order_start")
async def cb_order_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await begin_order(call.from_user.id, call.message, state)


async def begin_order(user_id: int, target: Message, state: FSMContext) -> None:
    """Запускает сбор заказа. Годится и для кнопки, и для intent из текста."""
    data = await state.get_data()
    await state.set_state(Order.event_date)
    # Повод/бюджет из воронки сохраняем — пригодятся в карточке заказа
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
#  ШАГИ 1-4 — СБОР ДАННЫХ
# ══════════════════════════════════════════════

async def _advance(message: Message, state: FSMContext, field: str,
                   value: str, next_state, next_text: str) -> None:
    """Сохраняет ответ и ведёт к следующему шагу.

    Если клиент правит один пункт из сводки (order_edit_field), возвращаем
    его сразу к оплате, а не гоним по всей цепочке заново.
    """
    await state.update_data(**{field: value})
    recent.remember(message.from_user.id, "incoming", value)

    data = await state.get_data()
    if data.get("order_edit_field") == field:
        await state.update_data(order_edit_field=None)
        await _show_summary(message, state)
        return

    await state.set_state(next_state)
    await message.answer(next_text, reply_markup=kb.kb_order_cancel(), parse_mode="Markdown")


@router.message(Order.event_date, F.text)
async def msg_event_date(message: Message, state: FSMContext):
    await _advance(message, state, "event_date", message.text.strip(),
                   Order.event_place, msg.ORDER_ASK_PLACE)


@router.message(Order.event_place, F.text)
async def msg_event_place(message: Message, state: FSMContext):
    await _advance(message, state, "event_place", message.text.strip(),
                   Order.phrase, msg.ORDER_ASK_PHRASE)


@router.message(Order.phrase, F.text)
async def msg_phrase(message: Message, state: FSMContext):
    await _advance(message, state, "phrase", message.text.strip(),
                   Order.design, msg.ORDER_ASK_DESIGN)


@router.message(Order.design, F.photo)
async def msg_design_photo(message: Message, state: FSMContext):
    """Дизайн принимаем только текстом — по фото дизайнеру работать нечем."""
    await message.answer(msg.ORDER_DESIGN_NOT_PHOTO, parse_mode="Markdown")


@router.message(Order.design, F.text)
async def msg_design(message: Message, state: FSMContext):
    design = message.text.strip()
    await state.update_data(design=design)
    recent.remember(message.from_user.id, "incoming", design)

    data = await state.get_data()
    if data.get("order_edit_field") == "design":
        await state.update_data(order_edit_field=None)
        await _show_summary(message, state)
        return

    # Формат мог быть выбран заранее — тогда не переспрашиваем
    if data.get("order_format"):
        await _offer_postcard(message, state)
        return

    await state.set_state(Order.choose_format)
    await message.answer(msg.ORDER_ASK_FORMAT, reply_markup=kb.kb_order_format(), parse_mode="Markdown")


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
            "⚡ *Электронно* — если нужно срочно или хотите распечатать сами.\n"
            "🖼 *А4 в рамке* — универсальный вариант, хорошо смотрится на полке или столе.\n"
            "🖼 *А3 в рамке* — если это главный подарок и хочется, чтобы висел на стене.\n\n"
            "Чаще всего берут А4 — золотая середина.",
            reply_markup=kb.kb_order_format(),
            parse_mode="Markdown",
        )
        return

    await state.update_data(order_format=choice)
    data = await state.get_data()

    if data.get("order_edit_field") == "format":
        await state.update_data(order_edit_field=None)
        await _show_summary(call.message, state, user_id=call.from_user.id)
        return

    await _offer_postcard(call.message, state)


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
async def msg_postcard_text(message: Message, state: FSMContext):
    """Текст открытки — единственное, что ждём на этом шаге."""
    data = await state.get_data()
    if not data.get("awaiting_postcard_text"):
        # Клиент просто что-то пишет у оплаты — отвечаем как обычно
        from handlers.funnel import process_ai_message
        await process_ai_message(message, state, message.bot)
        return

    await state.update_data(
        postcard_text=message.text.strip(),
        awaiting_postcard_text=False,
    )
    await message.answer(msg.POSTCARD_ADDED, parse_mode="Markdown")
    await _show_summary(message, state)


# ══════════════════════════════════════════════
#  СВОДКА + ОПЛАТА
# ══════════════════════════════════════════════

async def _show_summary(target: Message, state: FSMContext, user_id: int = None) -> None:
    data = await state.get_data()
    uid = user_id or target.chat.id

    fmt_key = data.get("order_format", "electronic")
    fmt_name, price, pay_url = format_info(fmt_key)

    postcard = int(data.get("postcard") or 0)
    amount = price + (POSTCARD_PRICE if postcard else 0)
    postcard_line = f"💌 Открытка: _{data.get('postcard_text', 'с вашим текстом')}_\n" if postcard else ""

    user = await db.get_user(uid) or {}

    fields = dict(
        format=fmt_key,
        event_date=data.get("event_date", ""),
        event_place=data.get("event_place", ""),
        phrase=data.get("phrase", ""),
        design=data.get("design", ""),
        postcard=postcard,
        amount=amount,
    )

    # Клиент правит уже собранный заказ — обновляем ту же запись,
    # иначе каждая правка плодила новый заказ и новое уведомление админу
    existing_id = data.get("order_id")
    if existing_id:
        await db.update_order(existing_id, **fields)
        order_id = existing_id
        is_new = False
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
        format_name=fmt_name,
        postcard_line=postcard_line,
        amount=amount,
    )
    await target.answer(
        summary,
        reply_markup=kb.kb_order_pay(pay_url, order_id),
        parse_mode="Markdown",
    )
    await target.answer(
        msg.ORDER_PAID_HINT.format(delivery_line=_delivery_line(fmt_key)),
        parse_mode="Markdown",
    )
    # Карточку админу шлём один раз — на правках он её уже видел
    if is_new:
        await _notify_admin_order(order_id, uid)


def _delivery_line(fmt_key: str) -> str:
    if fmt_key == "electronic":
        return "Присылаем готовый PDF на почту — в течение часа после утверждения ⚡"
    return "Печатаем, оформляем в рамку и отправляем — 3-7 рабочих дней по России 🚚"


@router.callback_query(F.data == "order_edit")
async def cb_order_edit(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer(
        "Что поправим? 😊",
        reply_markup=kb.kb_order_edit(),
    )


@router.callback_query(F.data.startswith("order_re_"))
async def cb_order_redo(call: CallbackQuery, state: FSMContext):
    await call.answer()
    field = call.data.split("order_re_", 1)[1]

    steps = {
        "date": ("event_date", Order.event_date, "📅 Какая дата у события?"),
        "place": ("event_place", Order.event_place, "🌍 В каком городе это было?"),
        "phrase": ("phrase", Order.phrase, "✍️ Какую надпись разместить на карте?"),
        "design": ("design", Order.design, "🎨 Опишите словами, каким видите оформление."),
    }

    if field == "format":
        await state.update_data(order_edit_field="format")
        await state.set_state(Order.choose_format)
        await call.message.answer(msg.ORDER_ASK_FORMAT, reply_markup=kb.kb_order_format(),
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
    fmt_name, _, _ = format_info(order.get("format", "electronic"))

    postcard_line = "💌 Открытка: да\n" if order.get("postcard") else ""

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
        amount=order.get("amount", 0),
        created_at=datetime.now().strftime("%d.%m.%Y %H:%M"),
    )

    for admin_id in ADMIN_IDS:
        await notifier.send_to_admin(admin_id, text, kb.kb_admin_order(order_id, user_db_id))
