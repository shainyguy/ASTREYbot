import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

import database as db
import messages as msg
import keyboards as kb
from states import Admin, Funnel
from config import ADMIN_PASSWORD, ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)

# admin_id -> user_id (активные перехваты управления)
active_takeovers: dict[int, int] = {}
# user_id -> admin_id (обратный индекс)
user_takeovers: dict[int, int] = {}


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
    await call.answer()

    user_id = int(call.data.split("takeover_", 1)[1])
    admin_id = call.from_user.id

    active_takeovers[admin_id] = user_id
    user_takeovers[user_id] = admin_id

    await db.start_takeover(admin_id, user_id)
    await db.update_user(user_id, stage="manager_takeover")

    user = await db.get_user(user_id)
    name = (user.get("full_name") or user.get("first_name") or "Пользователь") if user else "Пользователь"

    await state.set_state(Admin.takeover)
    await call.message.answer(
        msg.ADMIN_TAKEOVER_ON.format(name=name, user_id=user_id),
        parse_mode="Markdown"
    )

    try:
        await bot.send_message(user_id, msg.TAKEOVER_USER_NOTIFY, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about takeover: {e}")


@router.message(Command("release"))
async def cmd_release(message: Message, state: FSMContext, bot: Bot):
    admin_id = message.from_user.id
    user_id = active_takeovers.pop(admin_id, None)

    if not user_id:
        await message.answer("У тебя нет активного перехвата.")
        return

    user_takeovers.pop(user_id, None)
    await db.end_takeover(admin_id, user_id)
    await db.update_user(user_id, stage="ai_chat")

    user = await db.get_user(user_id)
    name = (user.get("full_name") or user.get("first_name") or "Пользователь") if user else "Пользователь"

    await state.set_state(Admin.panel)
    await message.answer(msg.ADMIN_TAKEOVER_OFF.format(name=name))

    try:
        await bot.send_message(
            user_id,
            "💬 Наш менеджер завершил диалог. Если появятся вопросы — пиши, всегда помогу! 😊",
        )
    except Exception:
        pass


@router.message(Admin.takeover)
async def admin_takeover_message(message: Message, bot: Bot):
    admin_id = message.from_user.id
    user_id = active_takeovers.get(admin_id)

    if not user_id:
        await message.answer(
            "Нет активного перехвата. Используй /admin для входа в панель."
        )
        return

    if message.text and message.text.startswith("/release"):
        return  # Обрабатывается отдельным хэндлером

    await db.log_message(user_id, "outgoing_admin", message.text or "[медиа]")

    try:
        await bot.send_message(user_id, message.text or "")
    except Exception as e:
        await message.answer(f"❌ Не удалось доставить сообщение: {e}")


# ══════════════════════════════════════════════
#  ФОРВАРД СООБЩЕНИЙ ОТ ПОЛЬЗОВАТЕЛЯ К АДМИНУ
# ══════════════════════════════════════════════

async def forward_to_admin(bot: Bot, user_id: int, text: str):
    admin_id = user_takeovers.get(user_id)
    if not admin_id:
        return False

    user = await db.get_user(user_id)
    name = (user.get("full_name") or user.get("first_name") or f"ID:{user_id}") if user else f"ID:{user_id}"
    username = (user.get("username") or "") if user else ""
    uname_str = f" (@{username})" if username else ""

    try:
        await bot.send_message(
            admin_id,
            f"👤 *{name}{uname_str}:*\n{text}",
            parse_mode="Markdown"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to forward message to admin: {e}")
        return False


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
    user = await db.get_user(call.from_user.id)
    if not user or (not user.get("admin_authorized") and not is_admin(call.from_user.id)):
        await call.answer("⛔ Нет доступа. Используй /admin ПАРОЛЬ", show_alert=True)
        return False
    return True
