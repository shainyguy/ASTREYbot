"""Разбор ответов клиента во время оформления заказа.

Главная задача — отличить ДАННЫЕ для карты от ВОПРОСА. Раньше бот всё
подряд записывал в заказ: спросишь «а доставка какая?» на шаге города —
и в заказе город «а доставка какая». Здесь эта логика собрана в одном
месте и используется и Telegram-ботом, и ВК.
"""
import re
from datetime import date, datetime
from typing import Optional

# ── Вопросительные маркеры ──
_Q_WORDS = (
    "как", "что", "сколько", "почему", "зачем", "когда", "где", "куда",
    "какой", "какая", "какие", "каком", "кто", "чем", "чего",
    "можно", "нужно", "надо", "будет", "есть",
)
_Q_PHRASES = (
    "можно ли", "есть ли", "а если", "а вдруг", "правда ли", "а что",
    "а как", "а сколько", "а когда", "а где", "а доставка", "а оплата",
    "не понял", "не поняла", "не понятно", "непонятно", "объясни",
    "подскажи", "расскажи", "а можно", "хочу спросить", "вопрос",
)


def looks_like_question(text: str, field: str = "") -> bool:
    """Похоже ли на вопрос, а не на данные для карты.

    field задаёт строгость. Для даты/города/формата судим смелее — там
    осмысленный ответ короткий и предсказуемый. Для надписи и оформления
    осторожнее: человек может написать «Какой была та ночь» как надпись
    или «какой-нибудь тёплый» как пожелание к дизайну.
    """
    t = (text or "").strip().lower()
    if not t:
        return False

    if "?" in t:
        return True

    # Для свободных полей больше ничего не проверяем — слишком легко ошибиться
    if field in ("phrase", "design"):
        return False

    if any(p in t for p in _Q_PHRASES):
        return True

    words = t.split()
    if words and words[0].strip(",.!") in _Q_WORDS:
        return True
    # «а доставка», «а рамка» — вопрос без вопросительного знака
    if len(words) > 1 and words[0] == "а":
        return True

    return False


def mentions_faq_topic(text: str) -> bool:
    """Клиент затронул тему из FAQ (доставка, оплата, сроки, гарантия)."""
    import messages as msg
    t = (text or "").lower()
    return any(key in t for key in msg.FAQ)


# ── Дата события ──

_DATE_PATTERNS = (
    r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$",
    r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2})$",
)

_MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}


def parse_date(text: str) -> Optional[str]:
    """→ нормализованная дата «ДД.ММ.ГГГГ» или None.

    Понимает 14.02.2023, 14/02/23, 14-02-2023 и «14 февраля 2023».
    """
    t = (text or "").strip()

    for pattern in _DATE_PATTERNS:
        m = re.match(pattern, t)
        if m:
            day, month, year = (int(g) for g in m.groups())
            if year < 100:
                year += 2000 if year < 50 else 1900
            return _validate(day, month, year)

    # «14 февраля 2023» / «14 фев 2023»
    m = re.match(r"^(\d{1,2})\s+([а-яё]{3,})\.?\s*(\d{4})?$", t.lower())
    if m:
        day = int(m.group(1))
        month = next((v for k, v in _MONTHS.items() if m.group(2).startswith(k)), None)
        year = int(m.group(3)) if m.group(3) else date.today().year
        if month:
            return _validate(day, month, year)

    return None


def _validate(day: int, month: int, year: int) -> Optional[str]:
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    if not (1900 <= year <= date.today().year + 5):
        return None
    return f"{day:02d}.{month:02d}.{year}"


# ── Формат ──

def parse_format(text: str) -> Optional[str]:
    """Формат из живой речи: «давайте А4», «электронный», «в рамке А3»."""
    t = (text or "").lower()

    if re.search(r"\bа\s?-?3\b|a\s?-?3\b", t):
        return "a3_frame"
    if re.search(r"\bа\s?-?4\b|a\s?-?4\b", t):
        return "a4_frame"
    if any(w in t for w in ("электрон", "пдф", "pdf", "файл", "цифров", "на почту", "email")):
        return "electronic"
    if "рамк" in t or "печат" in t or "постер" in t:
        return "a4_frame"  # рамка без указания размера — самый ходовой А4
    return None


# ── Доставка ──

def parse_delivery(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(w in t for w in ("самовывоз", "сам заберу", "заберу сам", "сокольник", "самовыв", "заеду", "приеду")):
        return "pickup"
    if any(w in t for w in ("почт", "доставк", "отправ", "привез", "курьер")):
        return "post"
    return None
