import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "ASTREYKIRILL")
ADMIN_IDS: List[int] = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "574947799").split(",") if x.strip()
]

GIGACHAT_AUTH_KEY: str = os.getenv("GIGACHAT_AUTH_KEY", "")
GIGACHAT_CLIENT_ID: str = os.getenv("GIGACHAT_CLIENT_ID", "")
GIGACHAT_CLIENT_SECRET: str = os.getenv("GIGACHAT_CLIENT_SECRET", "")
GIGACHAT_SCOPE: str = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")

DATABASE_PATH: str = os.getenv("DATABASE_PATH", "/data/astreybot.db")

VK_TOKEN: str = os.getenv("VK_TOKEN", "")
VK_GROUP_ID: int = int(os.getenv("VK_GROUP_ID", "0"))
ADMIN_VK_IDS: List[int] = [
    int(x.strip()) for x in os.getenv("ADMIN_VK_IDS", "").split(",") if x.strip()
]

WEBSITE_URL: str = "https://astreys.ru"

# ── Форматы товара ──
# key → (название, цена, ссылка на счёт для базовой цены)
_PAY_ELECTRONIC = "https://auth.robokassa.ru/merchant/Invoice/i0627GJwwUWSyvqbro1h-w"
_PAY_A4 = "https://auth.robokassa.ru/merchant/Invoice/NWCLs0grvUKkPFlV8OyIcg"
_PAY_A3 = "https://auth.robokassa.ru/merchant/Invoice/c09X0IUloEyPkRbt6L-CPw"

ORDER_FORMATS: dict = {
    "electronic": ("Электронный (PDF)", 590, _PAY_ELECTRONIC),
    "a4_frame": ("А4 в рамке", 2190, _PAY_A4),
    "a3_frame": ("А3 в рамке", 2490, _PAY_A3),
}

# ── Доставка (только для форматов в рамке) ──
# key → (название, цена)
DELIVERY_OPTIONS: dict = {
    "pickup": ("Самовывоз, м. Сокольники", 0),
    "post": ("Почта России", 500),
}

POSTCARD_PRICE: int = 190

def format_info(key: str) -> tuple:
    """→ (название, цена, ссылка на оплату)

    По ссылке клиент платит только за саму карту — счета Robokassa
    выставлены на фиксированную сумму. Открытка и платная доставка идут
    доплатой, о ней менеджер договаривается отдельно.
    """
    return ORDER_FORMATS.get(key, ORDER_FORMATS["electronic"])


def delivery_info(key: str) -> tuple:
    """→ (название, цена)"""
    return DELIVERY_OPTIONS.get(key, ("", 0))
HTTP_PORT: int = int(os.getenv("PORT", "8080"))
BOT_API_SECRET: str = os.getenv("BOT_API_SECRET", "")

AI_CONFUSION_THRESHOLD: int = 3
MAX_HISTORY_MESSAGES: int = 12

PRODUCT_IMAGES: list = [
    ("https://astreys.ru/img/star-map.jpg", "🌟 *Карта звёздного неба* — PDF от 590₽"),
    ("https://astreys.ru/img/sound-poster.jpg", "🎵 *Картина со звуком* — от 2190₽"),
    ("https://astreys.ru/img/photo-poster.jpg", "📸 *Фотопостер Polaroid* — от 1290₽"),
]
