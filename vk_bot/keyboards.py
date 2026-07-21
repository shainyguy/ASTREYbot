import json
from config import WEBSITE_URL


def _btn(label: str, payload: dict, color: str = "default") -> dict:
    return {
        "action": {"type": "text", "label": label, "payload": json.dumps(payload, ensure_ascii=False)},
        "color": color,
    }


def _link_btn(label: str, url: str) -> dict:
    return {"action": {"type": "open_link", "link": url, "label": label}}


def _keyboard(buttons_rows: list, one_time: bool = False, inline: bool = False) -> str:
    return json.dumps(
        {"one_time": one_time, "inline": inline, "buttons": buttons_rows},
        ensure_ascii=False,
    )


def kb_welcome() -> str:
    return _keyboard([
        [_btn("🎁 Выбрать подарок", {"cmd": "start_funnel"}, "positive")],
        [_link_btn("🛒 Заказать на сайте", WEBSITE_URL)],
        [_btn("❓ Задать вопрос", {"cmd": "ask_question"})],
        [_btn("⏰ Напомнить о важной дате", {"cmd": "reminder_start"})],
        [_btn("🚚 Доставка", {"cmd": "faq_доставка"}), _btn("💳 Оплата", {"cmd": "faq_оплата"})],
    ])


def _back_btn() -> list:
    return [_btn("◀️ Назад", {"cmd": "back"}, "default")]


def kb_occasion() -> str:
    return _keyboard([
        [_btn("🎂 День рождения", {"occasion": "день рождения"}),
         _btn("💑 Годовщина", {"occasion": "годовщина"})],
        [_btn("💍 Свадьба", {"occasion": "свадьба"}),
         _btn("🎄 Новый год", {"occasion": "новый год"})],
        [_btn("💝 Просто так", {"occasion": "просто так"}),
         _btn("✍️ Другой", {"occasion": "другое"})],
        _back_btn(),
    ], one_time=True)


def kb_recipient() -> str:
    return _keyboard([
        [_btn("👩 Девушке/Жене", {"recipient": "девушке"}),
         _btn("👨 Парню/Мужу", {"recipient": "парню"})],
        [_btn("👩‍👧 Маме", {"recipient": "маме"}),
         _btn("👨‍👦 Папе", {"recipient": "папе"})],
        [_btn("👫 Другу", {"recipient": "другу"}),
         _btn("✍️ Другому", {"recipient": "другому"})],
        _back_btn(),
    ], one_time=True)


def kb_budget() -> str:
    return _keyboard([
        [_btn("💸 До 1 000₽", {"budget": "до 1000"})],
        [_btn("💳 1 000 — 3 000₽", {"budget": "1000-3000"})],
        [_btn("💎 От 3 000₽", {"budget": "3000+"})],
        [_btn("🤷 Бюджет не важен", {"budget": "не важно"})],
        _back_btn(),
    ], one_time=True)


def kb_presentation() -> str:
    return _keyboard([
        [_btn("🎁 Оформить заказ", {"cmd": "order_start"}, "positive")],
        [_btn("💬 Задать вопрос", {"cmd": "ask_question"})],
        [_link_btn("👀 Посмотреть дизайны", WEBSITE_URL)],
        _back_btn(),
    ])


def kb_ai_chat() -> str:
    return _keyboard([
        [_btn("🎁 Оформить заказ", {"cmd": "order_start"}, "positive")],
        [_btn("✨ Подобрать подарок", {"cmd": "start_funnel"})],
        [_btn("🚚 Доставка", {"cmd": "faq_доставка"}),
         _btn("💳 Оплата", {"cmd": "faq_оплата"})],
        [_btn("🛡 Гарантии", {"cmd": "faq_гарантия"}),
         _btn("⚡ Сроки", {"cmd": "faq_сроки"})],
        [_btn("👨‍💼 Позвать менеджера", {"cmd": "call_manager"}, "negative"),
         _btn("📋 Меню", {"cmd": "restart"})],
        _back_btn(),
    ])


def kb_reminder_days() -> str:
    return _keyboard([
        [_btn("За 1 день", {"cmd": "remind_days", "days": 1}),
         _btn("За 3 дня", {"cmd": "remind_days", "days": 3})],
        [_btn("За 5 дней", {"cmd": "remind_days", "days": 5}),
         _btn("За 7 дней", {"cmd": "remind_days", "days": 7})],
        _back_btn(),
    ], one_time=True)


def kb_reminder_saved() -> str:
    return _keyboard([
        [_btn("🎁 Выбрать подарок", {"cmd": "start_funnel"}, "positive")],
        [_btn("📋 Меню", {"cmd": "restart"})],
    ])


def kb_order_cancel() -> str:
    return _keyboard([
        [_btn("✖️ Отменить оформление", {"cmd": "order_cancel"})],
    ])


def kb_order_format() -> str:
    return _keyboard([
        [_btn("⚡ Электронно — 590₽", {"cmd": "order_fmt", "fmt": "electronic"}, "positive")],
        [_btn("🖼 А4 в рамке — 2 190₽", {"cmd": "order_fmt", "fmt": "a4_frame"})],
        [_btn("🖼 А3 в рамке — 2 490₽", {"cmd": "order_fmt", "fmt": "a3_frame"})],
        [_btn("🤔 Помогите выбрать", {"cmd": "order_fmt", "fmt": "help"})],
    ], one_time=True)


def kb_order_delivery() -> str:
    return _keyboard([
        [_btn("🚶 Самовывоз — бесплатно", {"cmd": "order_dlv", "dlv": "pickup"}, "positive")],
        [_btn("📮 Почтой России — 500₽", {"cmd": "order_dlv", "dlv": "post"})],
    ], one_time=True)


def kb_postcard() -> str:
    return _keyboard([
        [_btn("💌 Добавить открытку — 190₽", {"cmd": "postcard_yes"}, "positive")],
        [_btn("Спасибо, без неё", {"cmd": "postcard_no"})],
    ], one_time=True)


def kb_order_pay(pay_url: str) -> str:
    return _keyboard([
        [_link_btn("💳 Оплатить заказ", pay_url)],
        [_btn("✅ Я оплатил", {"cmd": "order_paid"}, "positive")],
        [_btn("✏️ Что-то поправить", {"cmd": "call_manager"})],
    ])


def kb_after_order() -> str:
    return _keyboard([
        [_btn("💬 Задать вопрос", {"cmd": "ask_question"})],
        [_btn("⏰ Напомнить о важной дате", {"cmd": "reminder_start"})],
    ])


def kb_remove() -> str:
    return json.dumps({"buttons": [], "one_time": True}, ensure_ascii=False)
