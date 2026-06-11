import time
import uuid
import requests
import urllib3
import logging
import config

# Отключаем предупреждения о самоподписанных SSL-сертификатах Сбера
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Кэширование токена GigaChat
g_access_token = None
g_token_expires = 0.0  # Unix timestamp окончания действия токена

def get_gigachat_token():
    """
    Получает токен доступа GigaChat по OAuth v2.
    Кэширует токен на 30 минут, чтобы не делать лишних запросов на каждую реплику.
    """
    global g_access_token, g_token_expires
    
    # Если токен есть в кэше и до его истечения больше 60 секунд — используем его
    if g_access_token and g_token_expires > time.time() + 60:
        return g_access_token
        
    if not config.GIGACHAT_AUTH_KEY:
        logger.warning("GIGACHAT_AUTH_KEY не задан в config.py. Работа в режиме локального матчера.")
        return None
        
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {config.GIGACHAT_AUTH_KEY}"
    }
    data = {
        "scope": config.GIGACHAT_SCOPE
    }
    
    try:
        # Используем verify=False, так как Сбер работает на Минцифровских SSL-сертификатах,
        # которых обычно нет в стандартном Linux-пакете.
        response = requests.post(url, headers=headers, data=data, verify=False, timeout=10)
        if response.status_code == 200:
            res_data = response.json()
            g_access_token = res_data["access_token"]
            # expires_at приходит в миллисекундах, переводим в секунды
            g_token_expires = res_data["expires_at"] / 1000.0
            logger.info("Успешно получен новый токен доступа GigaChat!")
            return g_access_token
        else:
            logger.error(f"Ошибка получения токена GigaChat {response.status_code}: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Исключение при запросе токена GigaChat: {e}")
        return None

def get_ai_response(user_text: str) -> str:
    """
    Отправляет реплику в ИИ GigaChat (Сбер) для ведения супер-продающего диалога.
    Если API-ключ не задан или упал по таймауту, мгновенно переключается на базу знаний.
    """
    user_text_lower = user_text.lower().strip()
    
    # Пробуем получить токен GigaChat
    token = get_gigachat_token()
    
    if token:
        try:
            url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "GigaChat",
                "messages": [
                    {"role": "system", "content": config.SYSTEM_PROMPT},
                    {"role": "user", "content": user_text}
                ],
                "temperature": 0.7
            }
            
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            if response.status_code == 200:
                result_json = response.json()
                return result_json['choices'][0]['message']['content']
            else:
                logger.error(f"GigaChat API вернул статус-код {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Ошибка соединения с GigaChat API: {e}")
            
    # Резервный локальный текстовый матчер (База знаний), если ИИ недоступен
    for item in config.KNOWLEDGE_BASE:
        for keyword in item['keywords']:
            if keyword in user_text_lower:
                return item['answer']
                
    # Заботливый продающий ответ по умолчанию
    default_answer = (
        "🤔 *Отличный вопрос!* Я хочу ответить на него максимально подробно. \n\n"
        "Каждый подарок в нашей звёздной мастерской *Astrey* создается индивидуально дизайнером под ваше событие. "
        "Поэтому лучше всего обсудить все детали с нашим живым менеджером — он подскажет идеальное решение! \n\n"
        "👉 Вы можете нажать кнопку ниже, чтобы **мгновенно позвать менеджера**, "
        "или запустить наш **интерактивный конструктор**, чтобы примерить дизайн будущей картины! 👇"
    )
    return default_answer
