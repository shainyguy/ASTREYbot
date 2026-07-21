from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import WEBSITE_URL, VK_GROUP_ID


def kb_welcome() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Выбрать подарок", callback_data="start_funnel"))
    builder.row(InlineKeyboardButton(text="🛒 Заказать сейчас", url=WEBSITE_URL))
    builder.row(InlineKeyboardButton(text="❓ Задать вопрос", callback_data="ask_question"))
    builder.row(InlineKeyboardButton(text="⏰ Напомнить о важной дате", callback_data="reminder_start"))
    builder.row(
        InlineKeyboardButton(text="🚚 Доставка", callback_data="faq_доставка"),
        InlineKeyboardButton(text="💳 Оплата", callback_data="faq_оплата"),
    )
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
    builder.row(InlineKeyboardButton(text="🎁 Оформить заказ", callback_data="order_start"))
    builder.row(InlineKeyboardButton(text="💬 Задать вопрос", callback_data="ask_question"))
    builder.row(InlineKeyboardButton(text="👀 Посмотреть дизайны", url=WEBSITE_URL))
    _add_back(builder)
    return builder.as_markup()


def kb_ai_chat() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Оформить заказ", callback_data="order_start"))
    builder.row(InlineKeyboardButton(text="✨ Подобрать подарок", callback_data="start_funnel"))
    builder.row(
        InlineKeyboardButton(text="🚚 Доставка", callback_data="faq_доставка"),
        InlineKeyboardButton(text="💳 Оплата", callback_data="faq_оплата"),
    )
    builder.row(
        InlineKeyboardButton(text="🛡 Гарантии", callback_data="faq_гарантия"),
        InlineKeyboardButton(text="⚡ Сроки", callback_data="faq_сроки"),
    )
    builder.row(
        InlineKeyboardButton(text="👨‍💼 Позвать менеджера", callback_data="call_manager"),
        InlineKeyboardButton(text="📋 Меню", callback_data="restart"),
    )
    builder.row(BACK_BTN)
    return builder.as_markup()


def kb_reminder_days() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="За 1 день", callback_data="remind_days_1"),
        InlineKeyboardButton(text="За 3 дня", callback_data="remind_days_3"),
    )
    builder.row(
        InlineKeyboardButton(text="За 5 дней", callback_data="remind_days_5"),
        InlineKeyboardButton(text="За 7 дней", callback_data="remind_days_7"),
    )
    builder.row(BACK_BTN)
    return builder.as_markup()


def kb_reminder_saved() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Мои напоминания", callback_data="my_reminders"))
    builder.row(InlineKeyboardButton(text="🎁 Выбрать подарок", callback_data="start_funnel"))
    builder.row(InlineKeyboardButton(text="📋 Меню", callback_data="restart"))
    return builder.as_markup()


def kb_my_reminders(reminders: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for r in reminders:
        builder.row(InlineKeyboardButton(
            text=f"🗑 {r['event_name']} ({r['event_date']})",
            callback_data=f"del_reminder_{r['id']}"
        ))
    builder.row(InlineKeyboardButton(text="➕ Добавить напоминание", callback_data="reminder_start"))
    builder.row(InlineKeyboardButton(text="📋 Меню", callback_data="restart"))
    return builder.as_markup()


# ══════════════════════════════════════════════
#  ОФОРМЛЕНИЕ ЗАКАЗА
# ══════════════════════════════════════════════

def kb_start_order() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Оформить заказ", callback_data="order_start"))
    builder.row(InlineKeyboardButton(text="💬 Сначала спрошу", callback_data="ask_question"))
    return builder.as_markup()


def kb_order_cancel() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✖️ Отменить оформление", callback_data="order_cancel"))
    return builder.as_markup()


def kb_order_format() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚡ Электронно — 590₽", callback_data="order_fmt_electronic"))
    builder.row(InlineKeyboardButton(text="🖼 А4 в рамке — 2 190₽", callback_data="order_fmt_a4_frame"))
    builder.row(InlineKeyboardButton(text="🖼 А3 в рамке — 2 490₽", callback_data="order_fmt_a3_frame"))
    builder.row(InlineKeyboardButton(text="🤔 Помогите выбрать", callback_data="order_fmt_help"))
    return builder.as_markup()


def kb_order_delivery() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚶 Самовывоз — бесплатно", callback_data="order_dlv_pickup"))
    builder.row(InlineKeyboardButton(text="📮 Почтой России — 500₽", callback_data="order_dlv_post"))
    return builder.as_markup()


def kb_order_pay(pay_url: str, order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оплатить заказ", url=pay_url))
    builder.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"order_paid_{order_id}"))
    builder.row(InlineKeyboardButton(text="✏️ Что-то поправить", callback_data="order_edit"))
    return builder.as_markup()


def kb_postcard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💌 Добавить открытку — 190₽", callback_data="postcard_yes"))
    builder.row(InlineKeyboardButton(text="Спасибо, без неё", callback_data="postcard_no"))
    return builder.as_markup()


def kb_order_edit() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Дату", callback_data="order_re_date"),
        InlineKeyboardButton(text="🌍 Место", callback_data="order_re_place"),
    )
    builder.row(
        InlineKeyboardButton(text="✍️ Надпись", callback_data="order_re_phrase"),
        InlineKeyboardButton(text="🎨 Оформление", callback_data="order_re_design"),
    )
    builder.row(
        InlineKeyboardButton(text="🎁 Формат", callback_data="order_re_format"),
        InlineKeyboardButton(text="📦 Доставку", callback_data="order_re_delivery"),
    )
    builder.row(InlineKeyboardButton(text="👨‍💼 Позвать менеджера", callback_data="call_manager"))
    return builder.as_markup()


def kb_after_order() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💬 Задать вопрос", callback_data="ask_question"))
    builder.row(InlineKeyboardButton(text="⏰ Напомнить о важной дате", callback_data="reminder_start"))
    return builder.as_markup()


def kb_admin_order(order_id: int, user_db_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🎨 Отправить макет",
        callback_data=f"send_mockup_{order_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="🎯 Написать клиенту",
        callback_data=f"takeover_{user_db_id}"
    ))
    builder.row(
        InlineKeyboardButton(text="✅ Оплачен", callback_data=f"ord_status_{order_id}_paid"),
        InlineKeyboardButton(text="🏆 Выполнен", callback_data=f"ord_status_{order_id}_done"),
    )
    return builder.as_markup()


def kb_mockup_review(order_id: int) -> InlineKeyboardMarkup:
    """Кнопки под макетом у клиента."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="✅ Всё отлично, утверждаю",
        callback_data=f"mockup_ok_{order_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="✏️ Нужно поправить",
        callback_data=f"mockup_fix_{order_id}"
    ))
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


def kb_notify_admin(user_db_id: int, username: str = None) -> InlineKeyboardMarkup:
    """Кнопки под уведомлением о клиенте.

    Никаких tg://user?id= — Telegram отклоняет такие кнопки для юзеров
    с закрытой приватностью, и вместе с кнопкой падало всё уведомление.
    Только https-ссылки, которые валидны всегда.
    """
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🎯 Взять в работу",
        callback_data=f"takeover_{user_db_id}"
    ))
    if user_db_id < 0:
        vk_id = abs(user_db_id)
        link = f"https://vk.com/gim{VK_GROUP_ID}?sel={vk_id}" if VK_GROUP_ID else f"https://vk.com/id{vk_id}"
        builder.row(InlineKeyboardButton(text="🔗 Открыть в ВК", url=link))
    elif username:
        builder.row(InlineKeyboardButton(
            text="🔗 Открыть в Telegram",
            url=f"https://t.me/{username.lstrip('@')}"
        ))
    return builder.as_markup()


def kb_takeover_active(user_db_id: int) -> InlineKeyboardMarkup:
    """Показывается админу, пока он ведёт диалог."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="✅ Завершить диалог",
        callback_data=f"release_{user_db_id}"
    ))
    builder.row(InlineKeyboardButton(text="⚙️ Панель", callback_data="admin_panel"))
    return builder.as_markup()
