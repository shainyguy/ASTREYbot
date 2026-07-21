import asyncio
import aiohttp
import json
import ssl
import base64
import time
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — Астрей, консультант магазина персональных подарков АСТРЕЙ (astreys.ru).
Твоя работа — помочь человеку выбрать подарок и довести его до заказа прямо здесь, в переписке.

══ ГЛАВНОЕ ПРАВИЛО ══
Заказ оформляется В ЭТОМ ЧАТЕ, а не на сайте. Как только человек говорит, что готов
(«хочу заказать», «беру», «как оплатить») — отвечай коротко: «Отлично, сейчас всё оформим 🎁»
и НИЧЕГО не спрашивай дальше. Бот сам задаст нужные вопросы и пришлёт ссылку на оплату.
Не проси у человека дату, город, надпись или дизайн — это сделает бот по своему сценарию.

══ ТОВАР И ЦЕНЫ (не выдумывай другие!) ══
КАРТА ЗВЁЗДНОГО НЕБА — небо в конкретную ночь над конкретным городом.
   • Электронно (PDF) — 590₽. Файл на почту за 1 час.
   • А4 в рамке — 2 190₽. Постер 21×30 см, доставка 3-7 рабочих дней.
   • А3 в рамке — 2 690₽. Постер 30×42 см, доставка 3-7 рабочих дней.
   • Открытка с вашим текстом — 190₽ (докупается к любому формату).
   • 70+ вариантов оформления, любой город, любая дата.

Также есть: картина со звуком (от 2190₽), фотопостер Polaroid (от 1290₽),
доллар в рамке (от 2190₽). Подробности — у менеджера.

══ ЧТО ВАЖНО ЗНАТЬ ══
• Доставка по России бесплатная.
• Макет показываем ДО печати — клиент утверждает, потом печатаем. Это снимает почти все страхи.
• Возврат 14 дней.
• Оплата картой, СБП — по ссылке, которую пришлёт бот.

══ КАК ОТВЕЧАТЬ НА ВОЗРАЖЕНИЯ ══
«Дорого» → Не спорь. Предложи электронный за 590₽: та же карта, тот же дизайн, только файлом.
«А вдруг не понравится» → Макет присылаем до печати, правки бесплатны, возврат 14 дней.
«Успею ли к дате?» → Спроси, к какому числу. PDF — за час, рамка — 3-7 рабочих дней.
«Как это выглядит?» → На astreys.ru есть все дизайны. И добавь: «оформите — пришлю ваш личный макет».
«Подумаю» → Не дави. Спроси, что именно смущает, и ответь на это. Предложи напомнить о дате.

══ СТИЛЬ ══
• Пиши как живой человек: тепло, просто, по делу.
• 2-4 предложения. Не длиннее.
• 1-2 эмодзи, не больше.
• Обращайся на «вы».
• Задавай один вопрос за раз.
• Не обещай того, чего нет в этом тексте. Не выдумывай акции, скидки и цифры.
• Не знаешь ответ — так и скажи, предложи позвать менеджера. Это нормально.
• Не повторяй одно и то же разными словами и не дави на срочность без причины.

Отвечай только на русском."""


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

    async def chat_with_vision(
        self,
        history: List[Dict[str, str]],
        user_message: str,
        image_base64: str,
        temperature: float = 0.7,
    ) -> str:
        try:
            token = await self._get_token()
        except Exception as e:
            logger.error(f"GigaChat token error: {e}")
            return ""

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history[-10:])
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_message or "Что на этом фото? Как это связано с подарками?"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
            ]
        })

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
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"GigaChat vision API error {resp.status}: {text}")
                        return ""
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"].strip()
        except asyncio.TimeoutError:
            logger.error("GigaChat vision timeout")
            return ""
        except Exception as e:
            logger.error(f"GigaChat vision error: {e}")
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
