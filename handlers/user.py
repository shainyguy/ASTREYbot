import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, Command

import database as db
import gigachat as gc
import messages as msg
import keyboards as kb
from states import Funnel
from handlers.admin import forward_to_admin, user_takeovers

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = message.from_user
    await db.upsert_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    await db.log_message(user.id, "incoming", "/start")
    gc.clear_history(user.id)

    # Deep link: /start subscribe_42
    text = message.text or ""
    if text.startswith("/start subscribe_"):
        parts = text.split("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            order_id = int(parts[1])
            await db.add_subscription(
                chat_id=message.from_user.id,
                platform="telegram",
                order_id=order_id,
                email=None,
            )
            await message.answer(
                f"✅ *Подписка оформлена!*\n\n"
                f"Я буду уведомлять тебя о смене статуса заказа *#{order_id}* 🚀\n\n"
                f"Чтобы отписаться: `/unsubscribe {order_id}`",
                parse_mode="Markdown"
            )
            return

    await state.set_state(Funnel.welcome)
    await message.answer(msg.WELCOME, reply_markup=kb.kb_welcome(), parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🌟 *АСТРЕЙ — Персонализированные подарки*\n\n"
        "Просто напиши мне, и я помогу выбрать идеальный подарок!\n\n"
        "Команды:\n"
        "/start — начать заново\n"
        "/subscribe — подписаться на уведомления о заказе\n"
        "/unsubscribe — отписаться от уведомлений\n"
        "/menu — главное меню\n"
        "/help — помощь\n\n"
        f"🌐 Сайт: {msg.WEBSITE_URL}",
        parse_mode="Markdown"
    )


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "📋 *Подписка на уведомления о заказе*\n\n"
            "Чтобы получать уведомления о смене статуса, отправь:\n"
            "`/subscribe НОМЕР_ЗАКАЗА EMAIL`\n\n"
            "Например: `/subscribe 42 ivan@example.com`\n\n"
            "Номер заказа и email — в письме после оформления 🚀",
            parse_mode="Markdown"
        )
        return

    order_id = args[1].strip()
    email = args[2].strip()

    if not order_id.isdigit():
        await message.answer("❌ Номер заказа должен быть числом")
        return

    if "@" not in email:
        await message.answer("❌ Введите корректный email")
        return

    await db.add_subscription(
        chat_id=message.from_user.id,
        platform="telegram",
        order_id=int(order_id),
        email=email,
    )
    await message.answer(
        f"✅ *Подписка оформлена!*\n\n"
        f"Я буду уведомлять тебя о смене статуса заказа *#{order_id}*.\n"
        f"Как только статус изменится — сразу напишу 🚀\n\n"
        f"Чтобы отписаться: `/unsubscribe {order_id}`",
        parse_mode="Markdown"
    )


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "📋 *Отписка от уведомлений*\n\n"
            "Чтобы отписаться от заказа: `/unsubscribe НОМЕР_ЗАКАЗА`\n"
            "Например: `/unsubscribe 42`",
            parse_mode="Markdown"
        )
        return

    order_id = args[1].strip()
    if not order_id.isdigit():
        await message.answer("❌ Номер заказа должен быть числом")
        return

    await db.remove_subscription(message.from_user.id, int(order_id))
    user_subs = await db.get_user_subscriptions(message.from_user.id)
    subs_count = len(user_subs)

    reply = f"✅ Отписка от заказа *#{order_id}* оформлена.\n"
    if subs_count > 0:
        reply += f"У тебя осталось подписок: {subs_count}"
    else:
        reply += "У тебя больше нет активных подписок."

    await message.answer(reply, parse_mode="Markdown")


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.set_state(Funnel.welcome)
    await message.answer(msg.WELCOME, reply_markup=kb.kb_welcome(), parse_mode="Markdown")


@router.message(Funnel.welcome)
async def msg_welcome_free(message: Message, state: FSMContext):
    text = message.text or ""
    await db.log_message(message.from_user.id, "incoming", text)

    if message.from_user.id in user_takeovers:
        await forward_to_admin(message.bot, message.from_user.id, text)
        return

    # Сразу в AI-чат, не дублируем приветствие
    await state.set_state(Funnel.ai_chat)
    from handlers.funnel import process_ai_message
    await process_ai_message(message, state, message.bot)


@router.message(F.text)
async def catch_all_messages(message: Message, state: FSMContext):
    user_id = message.from_user.id
    current_state = await state.get_state()

    if user_id in user_takeovers:
        await db.log_message(user_id, "incoming", message.text)
        forwarded = await forward_to_admin(message.bot, user_id, message.text)
        if forwarded:
            return

    if current_state is None:
        await db.upsert_user(
            telegram_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        await state.set_state(Funnel.ai_chat)
        from handlers.funnel import process_ai_message
        await process_ai_message(message, state, message.bot)
