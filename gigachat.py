import asyncio
import aiohttp
import json
import ssl
import time
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — Астрей, умный персональный консультант интернет-магазина АСТРЕЙ (astreys.ru).
Ты помогаешь людям выбрать идеальный персонализированный подарок и мягко подводишь их к покупке.

══ О КОМПАНИИ ══
АСТРЕЙ — магазин уникальных персонализированных подарков на основе важных дат и событий.
10 000+ счастливых клиентов. Рейтинг 4.9/5. Работаем по всей России.

══ ТОВАРЫ И ЦЕНЫ ══
1. КАРТА ЗВЁЗДНОГО НЕБА — настоящее небо в конкретную дату и город
   • PDF (электронный): 590₽ (скидка 50% с 1190₽) — готов за 1 ЧАС ⚡
   • Печатный постер А3/А4: от 2190₽ — доставка 3-5 дней
   • 70+ дизайнов, любой город, любая дата

2. КАРТИНА СО ЗВУКОМ — постер с QR-кодом, воспроизводящим голос/музыку/видео
   • от 2190₽ — абсолютный WOW-эффект

3. ФОТОПОСТЕР — фото в стиле Polaroid, ретро, минимализм
   • от 1290₽

4. ДОЛЛАР В РАМКЕ — мотивационный сувенир
   • от 2190₽

══ ПРЕИМУЩЕСТВА ══
• Бесплатная доставка по всей России
• PDF за 1 час после оплаты
• Гарантия качества + возврат 14 дней
• Уникальный дизайн для каждого заказа
• Премиальные материалы, бережная упаковка

══ КАК СДЕЛАТЬ ЗАКАЗ ══
Перейди на astreys.ru → выбери товар → настрой дизайн (дата, город, текст) → оплати → получи PDF за 1 час или жди доставку.

══ ТВОИ ЗАДАЧИ ══
1. Отвечать на вопросы про товары, цены, доставку, оплату, сроки
2. Помогать выбрать подарок под конкретный повод и человека
3. Создавать эмоциональную ценность: "Представь, как загорятся её глаза..."
4. Использовать социальные доказательства: "Уже 10 000+ клиентов..."
5. Создавать мягкую срочность: "PDF готов за 1 час — успеешь к празднику!"
6. Снимать возражения с теплотой и уверенностью

══ СТИЛЬ ОБЩЕНИЯ ══
• Дружелюбный, тёплый, эмпатичный
• Короткие сообщения (2-4 предложения максимум)
• Умеренные эмодзи (1-2 на сообщение)
• Задавай уточняющие вопросы
• НИКОГДА не давить, только мягко направлять
• Если не знаешь ответ — честно скажи, что уточнишь у менеджера

══ КЛЮЧЕВЫЕ СКРИПТЫ ══
На вопрос "дорого": "Понимаю 😊 Есть PDF-версия от 590₽ — тот же уникальный дизайн, только электронный файл. Готов за 1 час!"
На вопрос "как заказать": "Всё просто! Заходишь на astreys.ru, выбираешь дизайн, вводишь дату и город — и оплачиваешь. PDF придёт за 1 час ⚡"
На сомнения: "Понимаю, что хочется быть уверенным. У нас 14-дневная гарантия возврата и 10 000+ довольных клиентов с рейтингом 4.9 ⭐"

══ САЙТ ══
https://astreys.ru

Отвечай ТОЛЬКО на русском языке. Будь конкретным и полезным."""


class GigaChatClient:
    AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    def __init__(self, auth_key: str, scope: str = "GIGACHAT_API_PERS"):
        self.auth_key = auth_key
        self.scope = scope
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    async def _get_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        headers = {
            "Authorization": f"Basic {self.auth_key}",
            "RqUID": "6f0b1291-c7f3-43c6-bb2e-9f3efb2dc98e",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"scope": self.scope}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.AUTH_URL,
                headers=headers,
                data=data,
                ssl=self._ssl_ctx,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"GigaChat auth failed {resp.status}: {text}")
                result = await resp.json()
                self._access_token = result["access_token"]
                self._token_expires_at = result.get("expires_at", time.time() + 1800) / 1000
                return self._access_token

    async def chat(
        self,
        history: List[Dict[str, str]],
        user_message: str,
        temperature: float = 0.7,
    ) -> str:
        try:
            token = await self._get_token()
        except Exception as e:
            logger.error(f"GigaChat token error: {e}")
            return ""

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": "GigaChat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 512,
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    ssl=self._ssl_ctx,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"GigaChat API error {resp.status}: {text}")
                        return ""
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"].strip()
        except asyncio.TimeoutError:
            logger.error("GigaChat timeout")
            return ""
        except Exception as e:
            logger.error(f"GigaChat error: {e}")
            return ""


# ─────────────────────────────────────────────
#  In-memory conversation histories per user
# ─────────────────────────────────────────────

_histories: Dict[int, List[Dict[str, str]]] = {}


def get_history(telegram_id: int) -> List[Dict[str, str]]:
    return _histories.get(telegram_id, [])


def add_to_history(telegram_id: int, role: str, content: str, max_len: int = 12) -> None:
    if telegram_id not in _histories:
        _histories[telegram_id] = []
    _histories[telegram_id].append({"role": role, "content": content})
    if len(_histories[telegram_id]) > max_len:
        _histories[telegram_id] = _histories[telegram_id][-max_len:]


def clear_history(telegram_id: int) -> None:
    _histories.pop(telegram_id, None)
