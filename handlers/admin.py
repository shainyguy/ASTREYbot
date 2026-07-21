import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

import database as db
import gigachat as gc
import messages as msg
import keyboards as kb
import mockup
import recent
import takeover
from states import Admin, Funnel
from config import ADMIN_PASSWORD, ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)


def set_vk_api(api) -> None:
    """Вызывается из vk_bot.bot при старте ВК-бота."""
    takeover.set_vk_api(api)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ══════════════════════════════════════════════
#  АВТОРИЗАЦИЯ
# ══════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(msg.ADMIN_WELCOME, parse_mode="Markdown")
        await state.set_state(Admin.waiting_password)
        return

    password = parts[1].strip()
    if password == ADMIN_PASSWORD or is_admin(message.from_user.id):
        await db.upsert_user(message.from_user.id, username=message.from_user.username,
                             first_name=message.from_user.first_name)
        await db.update_user(message.from_user.id, admin_authorized=1)
        await state.set_state(Admin.panel)
        await message.answer(
            msg.ADMIN_PANEL.format(name=message.from_user.first_name or "Админ"),
            reply_markup=kb.kb_admin_panel(),
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Неверный пароль.")


@router.message(Admin.waiting_password)
async def admin_password_input(message: Message, state: FSMContext):
    if message.text.strip() == ADMIN_PASSWORD or is_admin(message.from_user.id):
        await db.upsert_user(message.from_user.id, username=message.from_user.username,
                             first_name=message.from_user.first_name)
        await db.update_user(message.from_user.id, admin_authorized=1)
        await state.set_state(Admin.panel)
        await message.answer(
            msg.ADMIN_PANEL.format(name=message.from_user.first_name or "Админ"),
            reply_markup=kb.kb_admin_panel(),
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Неверный пароль. Попробуй ещё раз:")


# ══════════════════════════════════════════════
#  ПАНЕЛЬ — главное меню
# ══════════════════════════════════════════════

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery, state: FSMContext):
    if not await _check_admin_auth(call):
        return
    await call.answer()
    await state.set_state(Admin.panel)
    await call.message.edit_text(
        msg.ADMIN_PANEL.format(name=call.from_user.first_name or "Админ"),
        reply_markup=kb.kb_admin_panel(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "admin_refresh")
async def cb_admin_refresh(call: CallbackQuery):
    if not await _check_admin_auth(call):
        return
    await call.answer("Обновлено ✅")
    await call.message.edit_reply_markup(reply_markup=kb.kb_admin_panel())


# ══════════════════════════════════════════════
#  СТАТИСТИКА
# ══════════════════════════════════════════════

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    if not await _check_admin_auth(call):
        return
    await call.answer()
    stats = await db.get_stats()
    text = msg.ADMIN_STATS.format(**stats)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="◀️ Панель", callback_data="admin_panel"))
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


# ══════════════════════════════════════════════
#  ЛИДЫ
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("admin_leads_"))
async def cb_admin_leads(call: CallbackQuery):
    if not await _check_admin_auth(call):
        return
    await call.answer()

    raw = call.data.split("admin_leads_", 1)[1]
    if raw == "new":
        status, page = "new", 0
    elif raw == "converted":
        status, page = "converted", 0
    else:
        status, page = "all", int(raw) if raw.isdigit() else 0

    leads = await db.get_leads(status=status, page=page, per_page=8)

    if not leads:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="◀️ Панель", callback_data="admin_panel"))
        await call.message.edit_text(
            "📭 *Лидов не найдено*",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        return

    header = f"📋 *Лиды* {'(новые)' if status == 'new' else '(закрытые)' if status == 'converted' else '(все)'}\n_Страница {page + 1}_\n\n"
    await call.message.edit_text(
        header + f"Найдено: {len(leads)} записей",
        reply_markup=kb.kb_admin_leads_list(leads, page),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("lead_view_"))
async def cb_lead_view(call: CallbackQuery):
    if not await _check_admin_auth(call):
        return
    await call.answer()

    lead_id = int(call.data.split("lead_view_", 1)[1])
    lead = await db.get_lead(lead_id)
    if not lead:
        await call.answer("Лид не найден", show_alert=True)
        return

    text = msg.ADMIN_LEAD_CARD.format(
        lead_id=lead["id"],
        full_name=lead.get("full_name") or "—",
        username=f"@{lead.get('username')}" if lead.get("username") else "—",
        phone=lead.get("phone") or "—",
        occasion=lead.get("occasion") or "—",
        recipient=lead.get("recipient") or "—",
        budget=lead.get("budget") or "—",
        product_interest=lead.get("product_interest") or "—",
        stage=lead.get("stage") or "—",
        created_at=lead.get("created_at") or "—",
        notes=lead.get("admin_notes") or "Нет заметок",
    )
    await call.message.edit_text(
        text,
        reply_markup=kb.kb_admin_lead(lead["id"], lead["telegram_id"], lead.get("status", "new")),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("lead_status_"))
async def cb_lead_status(call: CallbackQuery):
    if not await _check_admin_auth(call):
        return
    parts = call.data.split("_")
    lead_id = int(parts[2])
    status = parts[3]
    await db.update_lead_status(lead_id, status)
    status_labels = {"in_progress": "В работе 🔄", "converted": "Закрыт ✅", "lost": "Отклонён ❌"}
    await call.answer(f"Статус: {status_labels.get(status, status)}", show_alert=True)


@router.callback_query(F.data.startswith("lead_note_"))
async def cb_lead_note(call: CallbackQuery, state: FSMContext):
    if not await _check_admin_auth(call):
        return
    await call.answer()
    lead_id = int(call.data.split("lead_note_", 1)[1])
    await state.set_state(Admin.add_note)
    await state.update_data(note_lead_id=lead_id)
    await call.message.answer(
        f"📝 Введи заметку для лида #{lead_id}:\n\n_Отправь текст заметки_",
        parse_mode="Markdown"
    )


@router.message(Admin.add_note)
async def msg_add_note(message: Message, state: FSMContext):
    data = await state.get_data()
    lead_id = data.get("note_lead_id")
    if lead_id:
        await db.update_lead_notes(lead_id, message.text.strip())
        await message.answer(f"✅ Заметка для лида #{lead_id} сохранена!")
    await state.set_state(Admin.panel)


# ══════════════════════════════════════════════
#  РАССЫЛКА
# ══════════════════════════════════════════════

@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    if not await _check_admin_auth(call):
        return
    await call.answer()
    await state.set_state(Admin.broadcast)
    await call.message.answer(
        "📢 *Рассылка*\n\nНапиши текст сообщения для отправки всем пользователям.\n\n"
        "_Поддерживается Markdown-форматирование_\n\n"
        "Напиши /cancel для отмены",
        parse_mode="Markdown"
    )


@router.message(Admin.broadcast, Command("cancel"))
async def broadcast_cancel(message: Message, state: FSMContext):
    await state.set_state(Admin.panel)
    await message.answer("❌ Рассылка отменена.", reply_markup=kb.kb_admin_panel())


@router.message(Admin.broadcast)
async def broadcast_send(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    await state.set_state(Admin.panel)

    user_ids = await db.get_all_user_ids()
    sent = 0
    failed = 0

    await message.answer(f"⏳ Отправляю {len(user_ids)} пользователям...")

    for uid in user_ids:
        if uid == message.from_user.id:
            continue
        try:
            await bot.send_message(uid, text, parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"✅ Рассылка завершена!\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        reply_markup=kb.kb_admin_panel()
    )


# ══════════════════════════════════════════════
#  ПЕРЕХВАТ УПРАВЛЕНИЯ (TAKEOVER)
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("takeover_"))
async def cb_takeover(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not await _check_admin_auth(call):
        return
    await call.answer("Диалог твой 🎯")

    user_id = int(call.data.split("takeover_", 1)[1])
    admin_id = call.from_user.id

    released = await takeover.start(admin_id, user_id)
    name, source = await takeover.describe_user(user_id)

    await state.set_state(Admin.takeover)

    if released is not None:
        prev_name, _ = await takeover.describe_user(released)
        await call.message.answer(f"↩️ Диалог с {prev_name} закрыт — ты можешь вести только один за раз.")

    await call.message.answer(
        msg.ADMIN_TAKEOVER_ON.format(name=name, source=source),
        reply_markup=kb.kb_takeover_active(user_id),
        parse_mode="Markdown",
    )

    # Показываем последние сообщения, чтобы админ вошёл в контекст
    history = await _recent_dialog(user_id)
    if history:
        await call.message.answer(history, parse_mode="Markdown")

    ok, err = await takeover.send_to_user(user_id, msg.TAKEOVER_USER_NOTIFY)
    if not ok:
        await call.message.answer(f"⚠️ Клиента предупредить не вышло: {err}")


@router.callback_query(F.data.startswith("release_"))
async def cb_release(call: CallbackQuery, state: FSMContext):
    if not await _check_admin_auth(call):
        return
    await call.answer()
    admin_id = call.from_user.id

    user_id = await takeover.stop(admin_id)
    if user_id is None:
        await call.message.answer("У тебя нет активного диалога.")
        return

    name, _ = await takeover.describe_user(user_id)
    gc.clear_history(user_id)
    await state.set_state(Admin.panel)
    await call.message.answer(
        msg.ADMIN_TAKEOVER_OFF.format(name=name),
        reply_markup=kb.kb_admin_panel(),
    )


@router.message(Command("release"))
async def cmd_release(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    user_id = await takeover.stop(admin_id)

    if user_id is None:
        await message.answer("У тебя нет активного диалога.")
        return

    name, _ = await takeover.describe_user(user_id)
    gc.clear_history(user_id)
    await state.set_state(Admin.panel)
    await message.answer(
        msg.ADMIN_TAKEOVER_OFF.format(name=name),
        reply_markup=kb.kb_admin_panel(),
    )


# ══════════════════════════════════════════════
#  ОТПРАВКА МАКЕТА КЛИЕНТУ
# ══════════════════════════════════════════════

@router.callback_query(F.data.startswith("send_mockup_"))
async def cb_send_mockup(call: CallbackQuery, state: FSMContext):
    if not await _check_admin_auth(call):
        return
    await call.answer()

    order_id = int(call.data.split("send_mockup_", 1)[1])
    order = await db.get_order(order_id)
    if not order:
        await call.message.answer("Заказ не найден 🤔")
        return

    name, _ = await takeover.describe_user(order["telegram_id"])
    await state.set_state(Admin.send_mockup)
    await state.update_data(mockup_order_id=order_id)
    await call.message.answer(
        msg.ADMIN_ASK_MOCKUP.format(order_id=order_id, name=takeover.escape(name)),
        parse_mode="Markdown",
    )


@router.message(Admin.send_mockup, Command("cancel"))
async def cmd_mockup_cancel(message: Message, state: FSMContext):
    await state.set_state(Admin.panel)
    await message.answer("Отменил. Макет не отправлен.", reply_markup=kb.kb_admin_panel())


@router.message(Admin.send_mockup, F.photo | F.document)
async def msg_mockup_upload(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    order_id = data.get("mockup_order_id")
    order = await db.get_order(order_id) if order_id else None
    if not order:
        await state.set_state(Admin.panel)
        await message.answer("Заказ потерялся — открой карточку заново.")
        return

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    ok, err = await mockup.deliver(bot, order, file_id)

    if not ok:
        await message.answer(f"❌ Не удалось отправить: {err}")
        return

    await db.update_order(order_id, status="mockup_sent", nudge_level=0)
    await state.set_state(Admin.panel)
    await message.answer(
        msg.ADMIN_MOCKUP_SENT.format(order_id=order_id),
        reply_markup=kb.kb_admin_panel(),
        parse_mode="Markdown",
    )


@router.message(Admin.send_mockup)
async def msg_mockup_wrong_type(message: Message):
    """Админ прислал текст вместо картинки — не молчим."""
    await message.answer("Жду картинку макета 🎨\n\nИли /cancel, чтобы отменить.")


def _admin_is_relaying(message: Message) -> bool:
    """Фильтр: админ прямо сейчас ведёт диалог, а это не команда."""
    text = message.text or ""
    if text.startswith("/"):
        return False
    return takeover.user_of(message.from_user.id) is not None


@router.message(_admin_is_relaying)
async def admin_takeover_message(message: Message):
    """Всё, что админ пишет во время перехвата, уходит клиенту.

    Опирается на takeover (восстанавливается из БД), а не на FSM-состояние —
    поэтому переживает рестарт контейнера.
    """
    admin_id = message.from_user.id
    user_id = takeover.user_of(admin_id)

    text = message.text or message.caption or ""
    if not text:
        await message.answer("⚠️ Пока умею пересылать только текст. Опиши словами или дай ссылку.")
        return

    ok, err = await takeover.send_to_user(user_id, text)
    if ok:
        recent.remember(user_id, "outgoing_admin", text)
    else:
        await message.answer(f"❌ Не доставлено: {err}")


async def _recent_dialog(user_id: int, limit: int = 6) -> str:
    """Последние реплики диалога — чтобы менеджер сразу видел контекст.

    Берём из памяти (recent.py): переписку в базе больше не храним.
    """
    rows = recent.recent(user_id, limit)
    if not rows:
        return ""
    lines = ["🗂 *Последние сообщения:*", ""]
    for direction, body in rows:
        who = "👤" if direction == "incoming" else "🤖"
        lines.append(f"{who} {takeover.escape(body[:150])}")
    return "\n".join(lines)


# ══════════════════════════════════════════════
#  ФОРВАРД СООБЩЕНИЙ ОТ ПОЛЬЗОВАТЕЛЯ К АДМИНУ
# ══════════════════════════════════════════════

async def forward_to_admin(bot: Bot, user_id: int, text: str) -> bool:
    """Сообщение клиента → ведущему админу (совместимость со старым кодом)."""
    return await takeover.relay_to_admin(user_id, text)


# ══════════════════════════════════════════════
#  КОМАНДЫ АДМИНИСТРАТОРА
# ══════════════════════════════════════════════

@router.message(Command("leads"))
async def cmd_leads(message: Message):
    if not is_admin(message.from_user.id):
        return
    leads = await db.get_leads(status="all", page=0, per_page=8)
    if not leads:
        await message.answer("📭 Лидов нет")
        return
    await message.answer(
        f"📋 *Последние лиды* ({len(leads)} шт.)",
        reply_markup=kb.kb_admin_leads_list(leads),
        parse_mode="Markdown"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = await db.get_stats()
    await message.answer(msg.ADMIN_STATS.format(**stats), parse_mode="Markdown")


# ══════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ
# ══════════════════════════════════════════════

async def _check_admin_auth(call: CallbackQuery) -> bool:
    # Сначала проверяем ADMIN_IDS — без DB
    if is_admin(call.from_user.id):
        return True
    # Для остальных — проверяем admin_authorized в БД
    user = await db.get_user(call.from_user.id)
    if user and user.get("admin_authorized"):
        return True
    await call.answer("⛔ Нет доступа. Используй /admin ПАРОЛЬ", show_alert=True)
    return False
