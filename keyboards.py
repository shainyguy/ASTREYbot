from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import WEBSITE_URL


def kb_welcome() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Выбрать подарок", callback_data="start_funnel"))
    builder.row(InlineKeyboardButton(text="❓ Вопрос по заказу", callback_data="ask_question"))
    builder.row(InlineKeyboardButton(text="🚚 Доставка и оплата", callback_data="faq_delivery"))
    return builder.as_markup()


BACK_BTN = InlineKeyboardButton(text="◀️ Назад", callback_data="back")

def _add_back(builder: InlineKeyboardBuilder) -> InlineKeyboardBuilder:
    builder.row(BACK_BTN)
    return builder


def kb_occasion() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎂 День рождения", callback_data="occasion_день рождения"),
        InlineKeyboardButton(text="💑 Годовщина", callback_data="occasion_годовщина"),
    )
    builder.row(
        InlineKeyboardButton(text="💍 Свадьба", callback_data="occasion_свадьба"),
        InlineKeyboardButton(text="🎄 Новый год", callback_data="occasion_новый год"),
    )
    builder.row(
        InlineKeyboardButton(text="💝 Просто так", callback_data="occasion_просто так"),
        InlineKeyboardButton(text="✍️ Другой повод", callback_data="occasion_другое"),
    )
    _add_back(builder)
    return builder.as_markup()


def kb_recipient() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👩 Девушке/Жене", callback_data="recipient_девушке"),
        InlineKeyboardButton(text="👨 Парню/Мужу", callback_data="recipient_парню"),
    )
    builder.row(
        InlineKeyboardButton(text="👩‍👧 Маме", callback_data="recipient_маме"),
        InlineKeyboardButton(text="👨‍👦 Папе", callback_data="recipient_папе"),
    )
    builder.row(
        InlineKeyboardButton(text="👫 Другу/Подруге", callback_data="recipient_другу"),
        InlineKeyboardButton(text="👶 Ребёнку", callback_data="recipient_ребёнку"),
    )
    builder.row(InlineKeyboardButton(text="✍️ Другому человеку", callback_data="recipient_другому"))
    _add_back(builder)
    return builder.as_markup()


def kb_budget() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 До 1 000₽", callback_data="budget_до 1000"))
    builder.row(InlineKeyboardButton(text="💳 1 000 — 3 000₽", callback_data="budget_1000-3000"))
    builder.row(InlineKeyboardButton(text="💎 От 3 000₽", callback_data="budget_3000+"))
    builder.row(InlineKeyboardButton(text="🤷 Бюджет не важен", callback_data="budget_не важно"))
    _add_back(builder)
    return builder.as_markup()


def kb_presentation(budget: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🛒 Оформить заказ на сайте",
        url=WEBSITE_URL
    ))
    builder.row(InlineKeyboardButton(text="💬 Задать вопрос", callback_data="ask_question"))
    builder.row(InlineKeyboardButton(text="📋 Посмотреть все товары", url=WEBSITE_URL))
    return builder.as_markup()


def kb_ai_chat() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛒 Заказать сейчас", url=WEBSITE_URL))
    builder.row(
        InlineKeyboardButton(text="🚚 Доставка", callback_data="faq_доставка"),
        InlineKeyboardButton(text="💳 Оплата", callback_data="faq_оплата"),
    )
    builder.row(
        InlineKeyboardButton(text="🛡 Гарантии", callback_data="faq_гарантия"),
        InlineKeyboardButton(text="⚡ Сроки", callback_data="faq_сроки"),
    )
    builder.row(InlineKeyboardButton(text="👨‍💼 Позвать менеджера", callback_data="call_manager"))
    return builder.as_markup()


def kb_get_phone() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📱 Отправить мой номер", request_contact=True))
    builder.row(KeyboardButton(text="Пропустить →"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def kb_remove() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def kb_go_to_site() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🌟 Перейти на сайт АСТРЕЙ", url=WEBSITE_URL))
    builder.row(InlineKeyboardButton(text="💬 Задать ещё вопрос", callback_data="ask_question"))
    return builder.as_markup()


def kb_restart() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Начать заново", callback_data="restart"))
    builder.row(InlineKeyboardButton(text="🌟 Перейти на сайт", url=WEBSITE_URL))
    return builder.as_markup()


# ══════════════════════════════════════════════
#  АДМИН КЛАВИАТУРЫ
# ══════════════════════════════════════════════

def kb_admin_panel() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="👥 Лиды", callback_data="admin_leads_0"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Новые лиды", callback_data="admin_leads_new"),
        InlineKeyboardButton(text="✅ Закрытые", callback_data="admin_leads_converted"),
    )
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh"))
    return builder.as_markup()


def kb_admin_lead(lead_id: int, telegram_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="💬 Открыть диалог",
        url=f"tg://user?id={telegram_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="🎯 Взять управление",
        callback_data=f"takeover_{telegram_id}"
    ))
    builder.row(
        InlineKeyboardButton(text="✅ В работе", callback_data=f"lead_status_{lead_id}_in_progress"),
        InlineKeyboardButton(text="🏆 Закрыт", callback_data=f"lead_status_{lead_id}_converted"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отклонён", callback_data=f"lead_status_{lead_id}_lost"),
        InlineKeyboardButton(text="📝 Заметка", callback_data=f"lead_note_{lead_id}"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_leads_0"))
    return builder.as_markup()


def kb_admin_leads_list(leads: list, page: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lead in leads:
        status_icon = {"new": "🆕", "in_progress": "🔄", "converted": "✅", "lost": "❌"}.get(
            lead["status"], "📋"
        )
        name = lead["full_name"] or lead["username"] or f"ID:{lead['telegram_id']}"
        builder.row(InlineKeyboardButton(
            text=f"{status_icon} {name} — {lead['occasion'] or '?'} | {lead['budget'] or '?'}",
            callback_data=f"lead_view_{lead['id']}"
        ))
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_leads_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text="🔄 Обновить", callback_data=f"admin_leads_{page}"))
    nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_leads_{page + 1}"))
    builder.row(*nav_row)
    builder.row(InlineKeyboardButton(text="◀️ Панель", callback_data="admin_panel"))
    return builder.as_markup()


def kb_notify_admin(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="💬 Открыть диалог",
        url=f"tg://user?id={telegram_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="🎯 Взять управление",
        callback_data=f"takeover_{telegram_id}"
    ))
    return builder.as_markup()
