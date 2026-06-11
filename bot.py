import json
import logging
import telebot
from telebot import types
import config
import database
import keyboards
import ai_helper

# Инициализация логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация базы данных
database.init_db()

# Создание экземпляра бота
bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode='Markdown')

# Временное хранение состояния пользователей в памяти
USER_STATES = {}

# Хранение активных сессий администраторов с клиентами (Live Chat CRM)
# {admin_id: client_user_id}
ADMIN_CHATS = {}

# Хранение временных промокодов при заказе
USER_APPLIED_PROMO = {}

# Пароль администратора для авторизации
ADMIN_PASSWORD = "ASTREY_POWER_ADMIN_2026"

def get_user_state(user_id):
    if user_id not in USER_STATES:
        db_user = database.get_user(user_id)
        if db_user and db_user['quiz_state']:
            try:
                data = json.loads(db_user['quiz_data']) if db_user['quiz_data'] else {}
                USER_STATES[user_id] = {'state': db_user['quiz_state'], 'data': data}
            except Exception:
                USER_STATES[user_id] = {'state': 'IDLE', 'data': {}}
        else:
            USER_STATES[user_id] = {'state': 'IDLE', 'data': {}}
    return USER_STATES[user_id]

def update_state(user_id, state, data_update=None):
    user_state = get_user_state(user_id)
    user_state['state'] = state
    if data_update:
        user_state['data'].update(data_update)
    USER_STATES[user_id] = user_state
    
    # Сохраняем в БД
    try:
        database.update_user_quiz(user_id, state, json.dumps(user_state['data'], ensure_ascii=False))
    except Exception as e:
        logger.error(f"Error saving state to DB: {e}")

def clear_state(user_id):
    USER_STATES[user_id] = {'state': 'IDLE', 'data': {}}
    database.update_user_quiz(user_id, 'IDLE', '{}')

def calculate_price(state_data, discount_percent=0):
    product_type = state_data.get('product_type')
    if not product_type or product_type not in config.PRODUCTS:
        return 0
    
    base = config.PRODUCTS[product_type]['base_price']
    
    # Доплата за размер
    size_id = state_data.get('size', 'A4')
    size_extra = config.SIZES.get(size_id, {}).get('extra', 0)
    
    # Доплата за раму
    frame_id = state_data.get('frame', 'no_frame')
    frame_extra = config.FRAMES.get(frame_id, {}).get('extra', 0)
    
    # Доплата за упаковку
    pack_id = state_data.get('packaging', 'standard')
    pack_extra = config.PACKAGING.get(pack_id, {}).get('extra', 0)
    
    total = base + size_extra + frame_extra + pack_extra
    
    # Применение скидки
    if discount_percent > 0:
        total = int(total * (1 - discount_percent / 100))
        
    return total

# Уведомление администраторам о новом заказе
def notify_admins_about_order(order_id, order_data):
    user_info = f"@{order_data['username']}" if order_data['username'] else f"ID: {order_data['user_id']}"
    
    product_name = config.PRODUCTS.get(order_data['product_type'], {}).get('name', order_data['product_type'])
    size_name = config.SIZES.get(order_data['size'], {}).get('name', order_data['size'])
    frame_name = config.FRAMES.get(order_data['frame'], {}).get('name', order_data['frame'])
    pack_name = config.PACKAGING.get(order_data['packaging'], {}).get('name', order_data['packaging'])
    
    admin_text = (
        f"🚨 *ПОСТУПИЛ НОВЫЙ ЗАКАЗ №{order_id}!* 🚨\n\n"
        f"👤 *Клиент:* {order_data['client_name']} ({user_info})\n"
        f"📞 *Телефон:* `{order_data['client_phone']}`\n"
        f"📍 *Доставка:* {order_data['delivery_address']}\n\n"
        f"📦 *Продукт:* {product_name}\n"
        f"📐 *Размер:* {size_name}\n"
        f"🖼️ *Оформление:* {frame_name}\n"
        f"🎁 *Упаковка:* {pack_name}\n\n"
        f"⚙️ *Детали заказа:*\n"
        f"📅 *Дата события:* {order_data.get('event_date', '—')}\n"
        f"🏙️ *Город:* {order_data.get('event_city', '—')}\n"
        f"✍️ *Фраза на постере:* «{order_data.get('custom_phrase', '—')}»\n"
    )
    
    if order_data['product_type'] == 'soundwave':
        admin_text += f"🎵 *Аудио/Ссылка:* {order_data.get('audio_source', '—')}\n"
        
    admin_text += f"\n💰 *Сумма к оплате:* {order_data['price']} руб.\n"
    
    markup = keyboards.admin_order_item_keyboard(order_id)
    
    sent_any = False
    for admin_id in config.ADMIN_IDS:
        try:
            bot.send_message(admin_id, admin_text, reply_markup=markup, parse_mode='Markdown')
            sent_any = True
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")
            
    if not sent_any:
        logger.info(f"Order #{order_id} generated, but no active admin IDs in config. Use /admin to access.")

# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@bot.message_handler(commands=['start'])
def command_start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "друг"
    
    database.add_user(user_id, username, first_name)
    database.set_user_chat_mode(user_id, 0, None)
    if user_id in ADMIN_CHATS:
        del ADMIN_CHATS[user_id]
        
    clear_state(user_id)
    
    welcome_text = (
        f"🌟 *Привет, {first_name}! Рады видеть тебя в Astrey!* 🌟\n\n"
        "Мы создаем подарки, которые вызывают мурашки и слёзы счастья у самых близких. "
        "Карты звёздного неба над вашим городом в тот самый миг, уникальные постеры со звуком "
        "вашего голоса и стильные фотоколлажи на заказ. 🌌✨\n\n"
        "🎁 *Лови приветственный подарок!* Специально для тебя мы активировали промокод "
        "`ASTREY10` на скидку *10%* на первый заказ!\n\n"
        "🤔 *Не знаешь, что выбрать или есть вопрос?* Задай любой вопрос прямо в чат — "
        "я мгновенно на него отвечу!\n\n"
        "👉 Или нажми *Подобрать подарок*, чтобы пройти наш умный мини-квиз за 1 минуту, "
        "подобрать идеальный формат подарка и фразу, а также забрать *скидку 15%*! 👇"
    )
    
    bot.send_message(user_id, welcome_text, reply_markup=keyboards.main_menu())

@bot.message_handler(commands=['admin'])
def command_admin(message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) > 1 and args[1] == ADMIN_PASSWORD:
        if user_id not in config.ADMIN_IDS:
            config.ADMIN_IDS.append(user_id)
        bot.send_message(user_id, "🔑 *Вы успешно авторизованы как Администратор!*", reply_markup=keyboards.admin_keyboard())
        return
    
    if user_id in config.ADMIN_IDS:
        bot.send_message(user_id, "⚙️ *Панель администратора Astrey:*", reply_markup=keyboards.admin_keyboard())
    else:
        bot.send_message(user_id, "⚠️ У вас нет доступа к этой команде. Для авторизации введите `/admin ПАРОЛЬ`")

@bot.message_handler(commands=['stopchat'])
def command_stopchat(message):
    user_id = message.from_user.id
    if user_id in config.ADMIN_IDS and user_id in ADMIN_CHATS:
        client_id = ADMIN_CHATS[user_id]
        
        # Сброс режима чата
        database.set_user_chat_mode(client_id, 0, None)
        del ADMIN_CHATS[user_id]
        
        bot.send_message(user_id, "❌ *Диалог с клиентом успешно завершен.* Бот вернулся в режим автоответов.")
        
        try:
            bot.send_message(
                client_id, 
                "❌ *Менеджер завершил диалог.* \n\n"
                "Если у вас возникнут новые вопросы, я (умный бот-ассистент) всегда готов мгновенно "
                "ответить на них! Вы также можете запустить наш интерактивный квиз-конструктор. 👇",
                reply_markup=keyboards.main_menu()
            )
        except Exception:
            pass
    else:
        bot.send_message(user_id, "ℹ️ Вы не находитесь в активном диалоге с клиентом.")

# ==================== ТЕКСТОВЫЕ КНОПКИ И LIVE CHAT CRM ====================

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text_and_live_chat(message):
    user_id = message.from_user.id
    text = message.text
    
    database.update_last_activity(user_id)
    
    # 1. ПРОВЕРКА: Находится ли КЛИЕНТ в режиме чата с живым оператором?
    user_data = database.get_user(user_id)
    if user_data and user_data['is_in_chat'] == 1:
        operator_id = user_data['operator_id']
        
        # Если оператор назначен, пересылаем ему
        if operator_id:
            user_info = f"@{message.from_user.username}" if message.from_user.username else f"ID: {user_id}"
            try:
                bot.send_message(
                    operator_id, 
                    f"💬 *Клиент {user_info}:*\n\n{text}",
                    reply_markup=keyboards.admin_stop_chat_keyboard(user_id)
                )
            except Exception as e:
                logger.error(f"Failed to forward message to operator {operator_id}: {e}")
        else:
            # Если оператор еще не подключился, но чат активен, уведомляем админов еще раз
            notify_text = (
                f"🚨 *Клиент ждет ответа!* 🚨\n\n"
                f"👤 Клиент: @{message.from_user.username or 'без_юзернейма'} (ID: `{user_id}`)\n"
                f"✍️ Написал сообщение: «_{text}_»\n\n"
                f"Нажмите кнопку ниже, чтобы войти в чат и ответить ему!"
            )
            for admin_id in config.ADMIN_IDS:
                try:
                    bot.send_message(admin_id, notify_text, reply_markup=keyboards.admin_chat_keyboard(user_id))
                except Exception:
                    pass
        return

    # 2. ПРОВЕРКА: Пишет ли АДМИНИСТРАТОР, находящийся в режиме Live Chat?
    if user_id in config.ADMIN_IDS and user_id in ADMIN_CHATS:
        client_id = ADMIN_CHATS[user_id]
        try:
            bot.send_message(
                client_id, 
                f"💬 *Менеджер Astrey:*\n\n{text}"
            )
            # Дублируем админу подтверждение доставки
            bot.send_message(user_id, "✅ _Сообщение доставлено клиенту._", reply_markup=keyboards.admin_stop_chat_keyboard(client_id))
        except Exception as e:
            bot.send_message(user_id, f"❌ *Не удалось доставить сообщение клиенту:* {e}")
            database.set_user_chat_mode(client_id, 0, None)
            del ADMIN_CHATS[user_id]
        return

    # 3. ШТАТНЫЙ ОПРОСНИК / STATE MACHINE (Если не в чате)
    state_info = get_user_state(user_id)
    state = state_info['state']
    
    if state == 'WAITING_FOR_DATE':
        update_state(user_id, 'WAITING_FOR_CITY', {'event_date': text})
        bot.send_message(
            user_id, 
            "🏙️ *Прекрасно! Теперь укажите город (место события):*\n\n"
            "Например: _Москва_, _Сочи_ или _деревня Ивановка_.",
            reply_markup=keyboards.skip_keyboard("skip_step_city")
        )
        return
        
    elif state == 'WAITING_FOR_CITY':
        update_state(user_id, 'WAITING_FOR_PHRASE', {'event_city': text})
        bot.send_message(
            user_id, 
            "✍️ *Какую памятную фразу или заголовок нанести на постер?*\n\n"
            "Например: _«В эту ночь звёзды светили для нас»_, _«День, когда зародилась наша вселенная»_.\n\n"
            "👉 Напишите фразу или нажмите пропустить (мы предложим стандартный вариант):",
            reply_markup=keyboards.skip_keyboard("skip_step_phrase")
        )
        return
        
    elif state == 'WAITING_FOR_PHRASE':
        update_state(user_id, 'WAITING_FOR_AUDIO' if state_info['data'].get('product_type') == 'soundwave' else 'CHOOSING_SIZE', {'custom_phrase': text})
        
        if state_info['data'].get('product_type') == 'soundwave':
            bot.send_message(
                user_id, 
                "🎵 *Загрузите аудио или укажите ссылку:*\n\n"
                "Вы можете отправить голосовое сообщение прямо сюда, прикрепить аудиофайл (mp3, wav) "
                "или отправить ссылку на любимую песню.",
                reply_markup=keyboards.skip_keyboard("skip_step_audio")
            )
        else:
            bot.send_message(
                user_id, 
                "📐 *Выберите размер картины:*", 
                reply_markup=keyboards.size_keyboard()
            )
        return
        
    elif state == 'WAITING_FOR_AUDIO':
        update_state(user_id, 'CHOOSING_SIZE', {'audio_source': text})
        bot.send_message(
            user_id, 
            "📐 *Отлично! Теперь выберите размер картины:*", 
            reply_markup=keyboards.size_keyboard()
        )
        return
        
    elif state == 'WAITING_FOR_NAME':
        update_state(user_id, 'WAITING_FOR_PHONE', {'client_name': text})
        
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        btn_phone = types.KeyboardButton('📞 Поделиться контактом', request_contact=True)
        markup.add(btn_phone)
        
        bot.send_message(
            user_id, 
            "📞 *Ваш номер телефона для связи:*\n\n"
            "Нажмите на кнопку ниже, чтобы автоматически поделиться контактом, или введите его вручную в формате `+7...`",
            reply_markup=markup
        )
        return
        
    elif state == 'WAITING_FOR_PHONE':
        update_state(user_id, 'WAITING_FOR_ADDRESS', {'client_phone': text})
        bot.send_message(
            user_id, 
            "📍 *Укажите адрес доставки:* \n\n"
            "Например: _г. Москва, ул. Ленина, д. 10, кв. 25_ или _Пункт выдачи СДЭК на ул. Пушкина 4_.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return
        
    elif state == 'WAITING_FOR_ADDRESS':
        update_state(user_id, 'ORDER_CONFIRMATION', {'delivery_address': text})
        show_order_summary(user_id)
        return
        
    elif state == 'WAITING_FOR_PROMO':
        discount = database.check_promocode(text)
        if discount:
            USER_APPLIED_PROMO[user_id] = {'code': text.upper(), 'discount': discount}
            bot.send_message(user_id, f"🎉 *Промокод успешно применен!* Ваша скидка составляет *{discount}%*.")
            update_state(user_id, 'ORDER_CONFIRMATION')
            show_order_summary(user_id)
        else:
            bot.send_message(user_id, "❌ *Промокод не найден.* Попробуйте другой или вернитесь к заказу.")
            update_state(user_id, 'ORDER_CONFIRMATION')
            show_order_summary(user_id)
        return

    elif state == 'WAITING_FOR_BROADCAST':
        if user_id in config.ADMIN_IDS:
            clear_state(user_id)
            run_broadcast(text, message)
        return

    # --- Обработка стандартных кнопок меню ---
    if text == '🌌 Подобрать подарок (Квиз-конструктор) 🔥':
        clear_state(user_id)
        bot.send_message(
            user_id,
            "🚀 *Добро пожаловать в интерактивный квиз Astrey!* 🚀\n\n"
            "Ответьте всего на 3 простых вопроса, и наш алгоритм подберет "
            "идеальный персонализированный подарок, который запомнится навсегда.\n\n"
            "❓ *Вопрос 1 из 3:* Для кого вы выбираете подарок?",
            reply_markup=keyboards.quiz_who_keyboard()
        )
        return
        
    elif text == '🛍️ Каталог и Цены':
        catalog_text = (
            "⭐ *Наш ассортимент уникальных подарков-воспоминаний:* ⭐\n\n"
            "🌌 *Карта звёздного неба* (от 1490 руб.) — точное положение звёзд над вашим городом в особый день.\n\n"
            "🎵 *Картина со звуком* (от 1990 руб.) — интерактивный постер со звуковой волной и QR-кодом.\n\n"
            "📸 *Индивидуальный Фотопостер* (от 1290 руб.) — ваши яркие кадры на холсте премиум-бумаги в стильном дизайне.\n\n"
            "👉 Нажмите на любой товар ниже, чтобы узнать больше подробностей и запустить визуальный конструктор:"
        )
        bot.send_message(user_id, catalog_text, reply_markup=keyboards.catalog_keyboard())
        return
        
    elif text == 'ℹ️ Вопросы и Ответы (FAQ)':
        bot.send_message(
            user_id,
            "💡 *Часто задаваемые вопросы о нашей продукции:* \n\n"
            "Выберите тему на кнопках ниже, чтобы мгновенно получить ответ.",
            reply_markup=keyboards.faq_keyboard()
        )
        return
        
    elif text == '🎁 Мои скидки и промокоды':
        promo_text = (
            "🎁 *Ваши доступные скидки и бонусы:* 🎁\n\n"
            "🔥 `ASTREY10` — Скидка *10%* на первый заказ (Активен!)\n"
            "⭐ Пройдите *Квиз-конструктор*, чтобы получить секретный промокод на *15%*!\n\n"
            "💡 Чтобы применить промокод, просто введите его на финальном шаге оформления заказа в корзине!"
        )
        bot.send_message(user_id, promo_text)
        return
        
    elif text == '💬 Менеджер / Отзывы':
        bot.send_message(
            user_id,
            "🤗 *Мы всегда рады помочь вам с выбором!* 🤗\n\n"
            "Если вы хотите обсудить индивидуальный дизайн, прислать свои наработки или "
            "посмотреть сотни живых отзывов от наших счастливых клиентов, воспользуйтесь кнопками ниже:",
            reply_markup=keyboards.contact_keyboard()
        )
        return
        
    elif text == '📦 Мои Заказы':
        orders = database.get_user_orders(user_id)
        if not orders:
            bot.send_message(user_id, "ℹ️ У вас пока нет активных или завершенных заказов. Пора создать свой первый шедевр! 😊")
        else:
            orders_text = "📦 *История ваших заказов в Astrey:*\n\n"
            for o in orders:
                prod_name = config.PRODUCTS.get(o['product_type'], {}).get('name', o['product_type'])
                orders_text += (
                    f"🔸 *Заказ №{o['order_id']}* от {o['created_at'][:10]}\n"
                    f" • Товар: {prod_name}\n"
                    f" • Статус: *{o['status'].upper()}*\n"
                    f" • Сумма: {o['price']} руб.\n\n"
                )
            bot.send_message(user_id, orders_text)
        return

    # 4. ИНТЕЛЛЕКТУАЛЬНЫЙ fallback-ОТВЕТЧИК (AI / Keyword Matcher)
    # Если это не кнопка, не команда и не активный опросник — это вопрос по сайту или заказу!
    bot.send_chat_action(user_id, 'typing')
    ai_response = ai_helper.get_ai_response(text)
    
    bot.send_message(
        user_id, 
        ai_response, 
        reply_markup=keyboards.ai_fallback_keyboard()
    )

# Обработка входящего контакта
@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    user_id = message.from_user.id
    state_info = get_user_state(user_id)
    if state_info['state'] == 'WAITING_FOR_PHONE':
        phone = message.contact.phone_number
        update_state(user_id, 'WAITING_FOR_ADDRESS', {'client_phone': phone})
        bot.send_message(
            user_id, 
            "📍 *Контакт получен! Теперь укажите адрес доставки:* \n\n"
            "Например: _г. Москва, ул. Ленина, д. 10, кв. 25_ или _Пункт выдачи СДЭК на ул. Пушкина 4_.",
            reply_markup=types.ReplyKeyboardRemove()
        )

# Обработка входящего голосового или аудио сообщения
@bot.message_handler(content_types=['voice', 'audio'])
def handle_audio(message):
    user_id = message.from_user.id
    state_info = get_user_state(user_id)
    if state_info['state'] == 'WAITING_FOR_AUDIO':
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        update_state(user_id, 'CHOOSING_SIZE', {'audio_source': f"TG_FILE_ID:{file_id}"})
        bot.send_message(
            user_id, 
            "🎵 *Голос/аудио успешно записано! Мы сгенерируем звуковую волну именно по нему.* \n\n"
            "📐 *Теперь выберите размер картины:*",
            reply_markup=keyboards.size_keyboard()
        )

# ==================== CALLBACK QUERY HANDLERS ====================

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    
    database.update_last_activity(user_id)
    
    # ---- КВИЗ ВОПРОСЫ ----
    if data.startswith('quiz1_'):
        who = data.split('_')[1]
        update_state(user_id, 'QUIZ_Q2', {'quiz_who': who})
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=(
                "❓ *Вопрос 2 из 3:* Какой у вас намечается повод?\n\n"
                "Это поможет боту предложить наиболее уместный стиль и оформление."
            ),
            reply_markup=keyboards.quiz_occasion_keyboard()
        )
        
    elif data.startswith('quiz2_'):
        occasion = data.split('_')[1]
        update_state(user_id, 'QUIZ_Q3', {'quiz_occasion': occasion})
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=(
                "❓ *Вопрос 3 из 3:* Какой формат картины вам нравится больше всего?\n\n"
                "Выберите то, что больше откликается в сердце:"
            ),
            reply_markup=keyboards.quiz_format_keyboard()
        )
        
    elif data.startswith('quiz3_format_'):
        prod_format = data.split('_')[2]
        state_info = get_user_state(user_id)
        
        who = state_info['data'].get('quiz_who', 'lover')
        occasion = state_info['data'].get('quiz_occasion', 'love')
        
        rec_title = ""
        rec_phrase = ""
        
        if prod_format == 'star_map':
            rec_title = "🌌 *Рекомендация: Карта звёздного неба!*"
            if who == 'lover':
                rec_phrase = "«В эту ночь звёзды сошлись, чтобы соединить наши сердца»"
            elif who == 'family':
                rec_phrase = "«День, когда наша семья стала полной и счастливой»"
            else:
                rec_phrase = "«Так сошлись звёзды в твой самый лучший день»"
                
        elif prod_format == 'soundwave':
            rec_title = "🎵 *Рекомендация: Интерактивная картина со звуком!*"
            if who == 'lover':
                rec_phrase = "«Слова, которые я буду повторять тебе вечно...» (Ваш голос)"
            else:
                rec_phrase = "Ваша любимая общая песня, вызывающая улыбку и воспоминания."
                
        else:
            rec_title = "📸 *Рекомендация: Индивидуальный Фотопостер!*"
            rec_phrase = "Минималистичный фотоколлаж с вашими памятными датами внизу."
            
        rec_text = (
            f"🎉 *Ура! Квиз пройден! Мы подобрали идеальное решение:* \n\n"
            f"{rec_title}\n"
            f"💡 *Идея фразы:* {rec_phrase}\n\n"
            f"🔥 Как и обещали, мы дарим вам повышенную скидку *15%* по промокоду `STARFALL` на этот заказ! "
            f"Промокод уже автоматически забронирован за вашим аккаунтом.\n\n"
            f"👉 Начнем конструировать картину прямо сейчас?"
        )
        
        update_state(user_id, 'IDLE', {'product_type': prod_format})
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton('✨ Запустить Конструктор', callback_data=f"start_order_{prod_format}"))
        markup.add(types.InlineKeyboardButton('⬅️ В главное меню', callback_data="back_to_menu"))
        
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=rec_text,
            reply_markup=markup
        )
        
    # ---- КАТАЛОГ И ПРОДУКТЫ ----
    elif data.startswith('show_product_'):
        prod_id = data.split('_')[2]
        prod_data = config.PRODUCTS[prod_id]
        
        prod_text = (
            f"📦 *{prod_data['name']}*\n\n"
            f"{prod_data['desc']}\n\n"
            f"💰 *Базовая цена:* от {prod_data['base_price']} руб.\n"
            "⏳ *Срок изготовления:* 1-2 дня."
        )
        
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=prod_text,
            reply_markup=keyboards.order_product_keyboard(prod_id)
        )
        
    elif data == 'back_to_catalog':
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text="👉 Выберите интересующий товар из нашего каталога:",
            reply_markup=keyboards.catalog_keyboard()
        )
        
    elif data == 'back_to_menu':
        bot.send_message(user_id, "Вы вернулись в главное меню. 👇", reply_markup=keyboards.main_menu())
        
    # ---- КОНСТРУКТОР ЗАКАЗА ----
    elif data.startswith('start_order_'):
        prod_id = data.split('_')[2]
        update_state(user_id, 'WAITING_FOR_DATE', {'product_type': prod_id})
        
        prompt_text = ""
        if prod_id == 'star_map':
            prompt_text = (
                "📅 *Шаг 1: Укажите памятную дату события:*\n\n"
                "Например: _15.09.2023_ или _24 декабря 2018_. По этой дате мы рассчитаем "
                "расположение созвездий."
            )
        elif prod_id == 'soundwave':
            prompt_text = (
                "📅 *Шаг 1: Укажите дату или событие:*\n\n"
                "Например: _Наш первый танец_ или _14.02.2025_."
            )
        else:
            prompt_text = (
                "📅 *Шаг 1: Укажите памятную дату или заголовок:*\n\n"
                "Например: _Вместе навсегда, 2026_."
            )
            
        bot.send_message(user_id, prompt_text, reply_markup=keyboards.skip_keyboard("skip_step_date"))
        
    # Пропуски шагов
    elif data == 'skip_step_date':
        update_state(user_id, 'WAITING_FOR_CITY', {'event_date': 'Не указано'})
        bot.send_message(
            user_id, 
            "🏙️ *Шаг 2: Укажите город (место события):*\n\n"
            "Например: _Москва_, _Сочи_.",
            reply_markup=keyboards.skip_keyboard("skip_step_city")
        )
        
    elif data == 'skip_step_city':
        update_state(user_id, 'WAITING_FOR_PHRASE', {'event_city': 'Не указано'})
        bot.send_message(
            user_id, 
            "✍️ *Шаг 3: Напишите памятную фразу на постере:*\n\n"
            "Например: _«В эту ночь звёзды светили для нас»_.",
            reply_markup=keyboards.skip_keyboard("skip_step_phrase")
        )
        
    elif data == 'skip_step_phrase':
        state_info = get_user_state(user_id)
        default_phrase = "Любовь вне времени" if state_info['data'].get('product_type') == 'star_map' else "Музыка нашего сердца"
        
        if state_info['data'].get('product_type') == 'soundwave':
            update_state(user_id, 'WAITING_FOR_AUDIO', {'custom_phrase': default_phrase})
            bot.send_message(
                user_id, 
                "🎵 *Шаг 4: Загрузите аудио или укажите ссылку:*\n\n"
                "Отправьте голосовое сообщение или ссылку на песню.",
                reply_markup=keyboards.skip_keyboard("skip_step_audio")
            )
        else:
            update_state(user_id, 'CHOOSING_SIZE', {'custom_phrase': default_phrase})
            bot.send_message(
                user_id, 
                "📐 *Шаг 4: Выберите размер картины:*", 
                reply_markup=keyboards.size_keyboard()
            )
            
    elif data == 'skip_step_audio':
        update_state(user_id, 'CHOOSING_SIZE', {'audio_source': 'Песня на выбор дизайнера'})
        bot.send_message(
            user_id, 
            "📐 *Шаг 4: Выберите размер картины:*", 
            reply_markup=keyboards.size_keyboard()
        )
            
    # Конструктор: выбор размера, рамки, упаковки через Inline кнопки
    elif data.startswith('set_size_'):
        size_id = data.split('_')[2]
        update_state(user_id, 'CHOOSING_FRAME', {'size': size_id})
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text="🖼️ *Шаг 5: Выберите раму и оформление картины:*",
            reply_markup=keyboards.frame_keyboard()
        )
        
    elif data.startswith('set_frame_'):
        frame_id = data.split('_')[2]
        update_state(user_id, 'CHOOSING_PACKAGING', {'frame': frame_id})
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text="🎁 *Шаг 6: Выберите тип упаковки:*\n\nДля подарка мы очень рекомендуем наш стильный фирменный тубус!",
            reply_markup=keyboards.packaging_keyboard()
        )
        
    elif data.startswith('set_pack_'):
        pack_id = data.split('_')[2]
        update_state(user_id, 'WAITING_FOR_NAME', {'packaging': pack_id})
        
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text="✨ *Превосходный выбор! Конфигурация картины завершена.* \n\nТеперь соберем контакты для доставки и согласуем макет."
        )
        bot.send_message(user_id, "👤 *Введите Ваше имя (ФИО для доставки):*")

    # ---- ФИНАЛИЗАЦИЯ И ПОДТВЕРЖДЕНИЕ ----
    elif data == 'order_promo':
        update_state(user_id, 'WAITING_FOR_PROMO')
        bot.send_message(user_id, "🎟️ *Введите ваш промокод:*\n\nНапример, `ASTREY10` или `STARFALL`:")
        
    elif data == 'order_restart':
        clear_state(user_id)
        bot.send_message(user_id, "🔄 Оформление сброшено. Начните сначала с помощью меню или квиза!", reply_markup=keyboards.main_menu())
        
    elif data == 'order_submit':
        state_info = get_user_state(user_id)
        applied_promo = USER_APPLIED_PROMO.get(user_id, {})
        discount = applied_promo.get('discount', 0)
        
        final_price = calculate_price(state_info['data'], discount)
        
        order_id = database.create_order(
            user_id=user_id,
            username=call.from_user.username,
            product_type=state_info['data'].get('product_type'),
            event_date=state_info['data'].get('event_date', '—'),
            event_city=state_info['data'].get('event_city', '—'),
            custom_phrase=state_info['data'].get('custom_phrase', '—'),
            audio_source=state_info['data'].get('audio_source', '—'),
            poster_size=state_info['data'].get('size', 'A4'),
            frame_type=state_info['data'].get('frame', 'no_frame'),
            packaging=state_info['data'].get('packaging', 'standard'),
            client_name=state_info['data'].get('client_name'),
            client_phone=state_info['data'].get('client_phone'),
            delivery_address=state_info['data'].get('delivery_address'),
            price=final_price
        )
        
        order_details = state_info['data'].copy()
        order_details['price'] = final_price
        order_details['username'] = call.from_user.username
        order_details['user_id'] = user_id
        
        notify_admins_about_order(order_id, order_details)
        
        success_text = (
            f"🎉 *УРА! ВАШ ЗАКАЗ №{order_id} УСПЕШНО ОФОРМЛЕН!* 🎉\n\n"
            f"💖 *{state_info['data'].get('client_name')}, спасибо за доверие!* Мы уже передали детали нашему дизайнеру. "
            "Каждый постер мы создаем с душой и огромным вниманием к деталям.\n\n"
            "📞 В течение 30 минут наш менеджер свяжется с вами по номеру телефона "
            f"`{state_info['data'].get('client_phone')}` для подтверждения макета, обсуждения деталей доставки и оплаты!\n\n"
            "✨ _С любовью, команда звёздной мастерской Astrey!_"
        )
        
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=success_text
        )
        
        clear_state(user_id)
        if user_id in USER_APPLIED_PROMO:
            del USER_APPLIED_PROMO[user_id]

    # ---- FAQ ИНТЕРАКТИВ ----
    elif data.startswith('faq_'):
        faq_key = data.split('_')[1] + '_' + data.split('_')[2] if len(data.split('_')) > 2 else data.split('_')[1]
        if faq_key in config.FAQ:
            bot.send_message(user_id, config.FAQ[faq_key], parse_mode='Markdown')

    # ---- ВЫЗОВ ОПЕРАТОРА / LIVE CHAT (CRM) ----
    elif data == 'call_operator':
        database.set_user_chat_mode(user_id, 1, None)
        clear_state(user_id)
        
        # Сообщение клиенту
        bot.send_message(
            user_id, 
            "🚨 *Я уже позвал нашего менеджера!* \n\n"
            "Он подключится к нашему диалогу в течение пары минут и с удовольствием ответит "
            "на любые ваши вопросы по сайту или заказу. Вы можете написать свои вопросы прямо сюда... 👇"
        )
        
        # Уведомление администраторам
        username_text = f"@{call.from_user.username}" if call.from_user.username else f"ID: {user_id}"
        notify_text = (
            f"🚨 *ВНИМАНИЕ! КЛИЕНТ ЖДЕТ ОТВЕТА!* 🚨\n\n"
            f"👤 Клиент: {username_text} (ID: `{user_id}`)\n"
            f"Перешел с сайта/задал вопрос, который требует живого общения.\n\n"
            f"Нажмите на кнопку ниже, чтобы начать чат напрямую с ним!"
        )
        
        for admin_id in config.ADMIN_IDS:
            try:
                bot.send_message(admin_id, notify_text, reply_markup=keyboards.admin_chat_keyboard(user_id))
            except Exception:
                pass
                
    elif data.startswith('admin_chat_'):
        admin_id = call.from_user.id
        client_id = int(data.split('_')[2])
        
        # Вход в сессию
        database.set_user_chat_mode(client_id, 1, admin_id)
        ADMIN_CHATS[admin_id] = client_id
        
        client_user = database.get_user(client_id)
        client_name = client_user['first_name'] if client_user else "клиент"
        
        bot.answer_callback_query(call.id, "Вы успешно вошли в чат с клиентом!")
        
        # Оповещение админа
        bot.send_message(
            admin_id, 
            f"💬 *Вы вошли в режим диалога с клиентом (ID: {client_id})!* \n\n"
            f"Все ваши последующие текстовые сообщения будут отправляться ему. "
            f"Чтобы завершить диалог и вернуть бота в авторежим, введите `/stopchat` или "
            f"нажмите на кнопку ниже:",
            reply_markup=keyboards.admin_stop_chat_keyboard(client_id)
        )
        
        # Оповещение клиента
        try:
            bot.send_message(
                client_id, 
                "💬 *К нашему диалогу подключился старший менеджер Astrey!* \n\n"
                "С удовольствием отвечу на любые вопросы. Напишите ваш вопрос ниже..."
            )
        except Exception:
            pass
            
    elif data.startswith('admin_stopchat_'):
        admin_id = call.from_user.id
        client_id = int(data.split('_')[2])
        
        # Сброс режима чата
        database.set_user_chat_mode(client_id, 0, None)
        if admin_id in ADMIN_CHATS:
            del ADMIN_CHATS[admin_id]
            
        bot.answer_callback_query(call.id, "Диалог завершен!")
        bot.send_message(admin_id, "❌ *Диалог с клиентом завершен.* Бот снова работает в авторежиме.")
        
        try:
            bot.send_message(
                client_id, 
                "❌ *Менеджер завершил диалог.* \n\n"
                "Если у вас возникнут новые вопросы, я всегда готов мгновенно ответить на них! "
                "Вы также можете продолжить конструктор в меню. 👇",
                reply_markup=keyboards.main_menu()
            )
        except Exception:
            pass
            
    # ---- АДМИН-ПАНЕЛЬ (CALLBACKS) ----
    elif data == 'admin_stats':
        if user_id in config.ADMIN_IDS:
            stats = database.get_stats()
            stats_text = (
                "📊 *Статистика бота Astrey на данный момент:* \n\n"
                f"👤 Всего пользователей в базе: *{stats['total_users']}*\n"
                f"📦 Всего заказов оформлено: *{stats['total_orders']}*\n"
                f"🔥 Новых заказов (в обработке): *{stats['new_orders']}*\n"
                f"💰 Общая выручка (без отмененных): *{stats['total_revenue']} руб.*"
            )
            bot.send_message(user_id, stats_text)
            
    elif data == 'admin_broadcast':
        if user_id in config.ADMIN_IDS:
            update_state(user_id, 'WAITING_FOR_BROADCAST')
            bot.send_message(
                user_id, 
                "📣 *Режим создания массовой рассылки!* \n\n"
                "Введите текст сообщения, которое увидят ВСЕ пользователи бота.\n\n"
                "✏️ Напишите текст рассылки прямо сейчас:"
            )
            
    elif data == 'admin_orders':
        if user_id in config.ADMIN_IDS:
            conn = database.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM orders ORDER BY order_id DESC LIMIT 5')
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                bot.send_message(user_id, "📦 Заказов пока нет.")
            else:
                for o in rows:
                    prod_name = config.PRODUCTS.get(o['product_type'], {}).get('name', o['product_type'])
                    order_text = (
                        f"📦 *Заказ №{o['order_id']}* [{o['status'].upper()}]\n"
                        f"👤 Клиент: {o['client_name']} ({o['client_phone']})\n"
                        f"🛍️ Товар: {prod_name}\n"
                        f"💰 Сумма: {o['price']} руб.\n"
                    )
                    bot.send_message(user_id, order_text, reply_markup=keyboards.admin_order_item_keyboard(o['order_id']))

    elif data.startswith('admin_status_'):
        if user_id in config.ADMIN_IDS:
            parts = data.split('_')
            order_id = int(parts[2])
            new_status = parts[3]
            
            database.update_order_status(order_id, new_status)
            bot.answer_callback_query(call.id, f"Статус заказа №{order_id} изменен на: {new_status}")
            
            order_data = database.get_order(order_id)
            if order_data:
                client_id = order_data['user_id']
                status_messages = {
                    'оплачен': f"💳 *Ваш заказ №{order_id} успешно оплачен!* Спасибо! Скоро мы передадим его на печать. 🖨️",
                    'в работе': f"🎨 *Ваш заказ №{order_id} передан дизайнеру и находится в работе!* Мы сообщим, когда постер будет готов.",
                    'доставлен': f"🚚 *Ваш заказ №{order_id} отправлен/доставлен!* Мы надеемся, что он подарит вам море улыбок. Будем рады отзыву! 🥰",
                    'отменен': f"❌ *Ваш заказ №{order_id} был отменен администратором.* Если у вас остались вопросы, обратитесь в поддержку."
                }
                if new_status in status_messages:
                    try:
                        bot.send_message(client_id, status_messages[new_status])
                    except Exception as e:
                        logger.error(f"Failed to send status update to user {client_id}: {e}")

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def show_order_summary(user_id):
    state_info = get_user_state(user_id)
    data = state_info['data']
    
    applied_promo = USER_APPLIED_PROMO.get(user_id, {})
    discount = applied_promo.get('discount', 0)
    promo_code = applied_promo.get('code', 'Нет')
    
    price = calculate_price(data, discount)
    
    product_name = config.PRODUCTS.get(data.get('product_type'), {}).get('name', '—')
    size_name = config.SIZES.get(data.get('size'), {}).get('name', '—')
    frame_name = config.FRAMES.get(data.get('frame'), {}).get('name', '—')
    pack_name = config.PACKAGING.get(data.get('packaging'), {}).get('name', '—')
    
    summary_text = (
        "🛒 *ВАША КОРЗИНА И ДЕТАЛИ ЗАКАЗА:* \n\n"
        f"🌌 *Формат:* {product_name}\n"
        f"📅 *Дата события:* {data.get('event_date', '—')}\n"
        f"🏙 *Город события:* {data.get('event_city', '—')}\n"
        f"✍️ *Надпись:* «{data.get('custom_phrase', '—')}»\n"
    )
    
    if data.get('product_type') == 'soundwave':
        audio = data.get('audio_source', '—')
        if audio.startswith('TG_FILE_ID'):
            audio = "Голосовое сообщение 🎤"
        summary_text += f"🎵 *Аудио:* {audio}\n"
        
    summary_text += (
        f"\n📐 *Размер:* {size_name}\n"
        f"🖼️ *Рама:* {frame_name}\n"
        f"🎁 *Упаковка:* {pack_name}\n\n"
        f"👤 *Получатель:* {data.get('client_name', '—')}\n"
        f"📞 *Телефон:* `{data.get('client_phone', '—')}`\n"
        f"📍 *Адрес:* {data.get('delivery_address', '—')}\n\n"
        f"🎫 *Примененный промокод:* `{promo_code}` " + (f"(-{discount}%)" if discount > 0 else "") + "\n"
        f"💰 *Итоговая стоимость:* *{price} руб.* (без учета доставки)\n\n"
        "👉 Проверьте все данные. Если всё верно — нажмите зеленую кнопку для отправки заказа дизайнеру!"
    )
    
    bot.send_message(user_id, summary_text, reply_markup=keyboards.order_confirm_keyboard())

def run_broadcast(text, admin_message):
    users = database.get_all_users()
    admin_id = admin_message.from_user.id
    
    bot.send_message(admin_id, f"🔄 Начата рассылка по базе из *{len(users)}* пользователей...")
    
    success_count = 0
    fail_count = 0
    
    for u in users:
        try:
            bot.send_message(u['user_id'], text)
            success_count += 1
        except Exception:
            fail_count += 1
            
    bot.send_message(
        admin_id, 
        f"✅ *Рассылка завершена!*\n\n"
        f"📈 Успешно доставлено: {success_count}\n"
        f"📉 Не доставлено (заблокировали бота): {fail_count}"
    )

if __name__ == '__main__':
    logger.info("Starting Telegram Bot...")
    if not config.IS_CONFIGURED:
        logger.warning("BOT_TOKEN is not configured! Please set it in config.py or BOT_TOKEN env variable.")
    print("Bot is ready! Run 'python3 bot.py' to launch.")
    bot.infinity_polling()
