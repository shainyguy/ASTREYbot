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
    await state.set_state(Funnel.welcome)

    await message.answer(msg.WELCOME, reply_markup=kb.kb_welcome(), parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🌟 *АСТРЕЙ — Персонализированные подарки*\n\n"
        "Просто напиши мне, и я помогу выбрать идеальный подарок!\n\n"
        "Команды:\n"
        "/start — начать заново\n"
        "/menu — главное меню\n"
        "/help — помощь\n\n"
        f"🌐 Сайт: {msg.WEBSITE_URL}",
        parse_mode="Markdown"
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.set_state(Funnel.welcome)
    await message.answer(msg.WELCOME, reply_markup=kb.kb_welcome(), parse_mode="Markdown")


@router.message(Funnel.welcome)
async def msg_welcome_free(message: Message, state: FSMContext):
    text = message.text or ""
    await db.log_message(message.from_user.id, "incoming", text)

    # Если пользователь уже в режиме менеджера — форвардим
    if message.from_user.id in user_takeovers:
        await forward_to_admin(message.bot, message.from_user.id, text)
        return

    # Любой текст на приветственном экране — запускаем AI
    await state.set_state(Funnel.ai_chat)
    await message.answer(msg.WELCOME, reply_markup=kb.kb_welcome(), parse_mode="Markdown")


# Перехват всех сообщений пользователей, которых взял менеджер
@router.message(F.text)
async def catch_all_messages(message: Message, state: FSMContext):
    user_id = message.from_user.id
    current_state = await state.get_state()

    # Если менеджер взял управление — форвардим
    if user_id in user_takeovers:
        await db.log_message(user_id, "incoming", message.text)
        forwarded = await forward_to_admin(message.bot, user_id, message.text)
        if forwarded:
            return

    # Если состояние None или welcome — показываем меню
    if current_state is None:
        await db.upsert_user(
            telegram_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        await state.set_state(Funnel.welcome)
        await message.answer(msg.WELCOME, reply_markup=kb.kb_welcome(), parse_mode="Markdown")
