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
        [_link_btn("🛒 Оформить заказ на сайте", WEBSITE_URL)],
        [_btn("💬 Задать вопрос", {"cmd": "ask_question"})],
        [_link_btn("📋 Все товары", WEBSITE_URL)],
        _back_btn(),
    ])


def kb_ai_chat() -> str:
    return _keyboard([
        [_link_btn("🛒 Заказать на сайте", WEBSITE_URL)],
        [_btn("🎁 Подобрать подарок", {"cmd": "start_funnel"}, "positive")],
        [_btn("🚚 Доставка", {"cmd": "faq_доставка"}),
         _btn("💳 Оплата", {"cmd": "faq_оплата"})],
        [_btn("🛡 Гарантии", {"cmd": "faq_гарантия"}),
         _btn("⚡ Сроки", {"cmd": "faq_сроки"})],
        [_btn("👨‍💼 Позвать менеджера", {"cmd": "call_manager"}, "negative"),
         _btn("📋 Меню", {"cmd": "restart"})],
        _back_btn(),
    ])


def kb_remove() -> str:
    return json.dumps({"buttons": [], "one_time": True}, ensure_ascii=False)
