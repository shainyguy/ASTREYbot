from telebot import types
import config

# Главное меню (Reply Keyboard)
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_constructor = types.KeyboardButton('🌌 Подобрать подарок (Квиз-конструктор) 🔥')
    btn_catalog = types.KeyboardButton('🛍️ Каталог и Цены')
    btn_faq = types.KeyboardButton('ℹ️ Вопросы и Ответы (FAQ)')
    btn_promo = types.KeyboardButton('🎁 Мои скидки и промокоды')
    btn_contact = types.KeyboardButton('💬 Менеджер / Отзывы')
    btn_my_orders = types.KeyboardButton('📦 Мои Заказы')
    
    markup.add(btn_constructor)
    markup.add(btn_catalog, btn_promo)
    markup.add(btn_faq, btn_contact)
    markup.add(btn_my_orders)
    return markup

# Кнопки каталога товаров (Inline)
def catalog_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for prod_id, prod_data in config.PRODUCTS.items():
        markup.add(types.InlineKeyboardButton(
            text=f"{prod_data['name']} (от {prod_data['base_price']} руб.)",
            callback_data=f"show_product_{prod_id}"
        ))
    return markup

# Клавиатура "Заказать" после просмотра продукта
def order_product_keyboard(product_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_order = types.InlineKeyboardButton('✨ Начать оформление', callback_data=f"start_order_{product_id}")
    btn_back = types.InlineKeyboardButton('⬅️ К списку товаров', callback_data="back_to_catalog")
    markup.add(btn_order)
    markup.add(btn_back)
    return markup

# Квиз: Вопрос 1 (Для кого подарок)
def quiz_who_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    options = [
        ('❤️ Для второй половинки', 'quiz1_lover'),
        ('👨‍👩‍👧‍👦 Для родителей / Семьи', 'quiz1_family'),
        ('🤝 Для друга / Подруги', 'quiz1_friend'),
        ('👶 Для ребёнка', 'quiz1_child'),
        ('✨ Для себя любимого(ой)', 'quiz1_self')
    ]
    for text, data in options:
        markup.add(types.InlineKeyboardButton(text=text, callback_data=data))
    return markup

# Квиз: Вопрос 2 (Повод)
def quiz_occasion_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    options = [
        ('💍 Годовщина / Свадьба', 'quiz2_wedding'),
        ('🎂 День рождения', 'quiz2_birthday'),
        ('🏡 Новоселье / Память', 'quiz2_memory'),
        ('💖 Без повода (Просто любовь)', 'quiz2_love')
    ]
    for text, data in options:
        markup.add(types.InlineKeyboardButton(text=text, callback_data=data))
    return markup

# Выбор формата в квизе
def quiz_format_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for prod_id, prod_data in config.PRODUCTS.items():
        markup.add(types.InlineKeyboardButton(
            text=f"{prod_data['name']}",
            callback_data=f"quiz3_format_{prod_id}"
        ))
    return markup

# Конструктор: Выбор размера
def size_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for size_id, size_data in config.SIZES.items():
        extra_text = f" (+{size_data['extra']} руб.)" if size_data['extra'] > 0 else " (Базовая цена)"
        markup.add(types.InlineKeyboardButton(
            text=f"{size_data['name']}{extra_text}",
            callback_data=f"set_size_{size_id}"
        ))
    return markup

# Конструктор: Выбор рамки
def frame_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for frame_id, frame_data in config.FRAMES.items():
        extra_text = f" (+{frame_data['extra']} rgb.)" if frame_data['extra'] > 0 else " (Включено)"
        markup.add(types.InlineKeyboardButton(
            text=f"{frame_data['name']}{extra_text}",
            callback_data=f"set_frame_{frame_id}"
        ))
    return markup

# Конструктор: Выбор упаковки
def packaging_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for pack_id, pack_data in config.PACKAGING.items():
        extra_text = f" (+{pack_data['extra']} руб.)" if pack_data['extra'] > 0 else " (Включено)"
        markup.add(types.InlineKeyboardButton(
            text=f"{pack_data['name']}{extra_text}",
            callback_data=f"set_pack_{pack_id}"
        ))
    return markup

# Клавиатура подтверждения шага (Пропустить / Оставить как есть)
def skip_keyboard(callback_data):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(text="➡️ Пропустить этот шаг", callback_data=callback_data))
    return markup

# Финальное подтверждение заказа
def order_confirm_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_confirm = types.InlineKeyboardButton('✅ Всё верно, подтверждаю заказ!', callback_data="order_submit")
    btn_promo = types.InlineKeyboardButton('🎟️ Применить промокод', callback_data="order_promo")
    btn_cancel = types.InlineKeyboardButton('❌ Начать сначала', callback_data="order_restart")
    markup.add(btn_confirm, btn_promo, btn_cancel)
    return markup

# Клавиатура FAQ (Inline)
def faq_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton('🌌 Как строится карта звёзд?', callback_data='faq_how_made'))
    markup.add(types.InlineKeyboardButton('🎵 Как звучит картина?', callback_data='faq_how_sound'))
    markup.add(types.InlineKeyboardButton('🚚 Доставка и Оплата', callback_data='faq_delivery'))
    markup.add(types.InlineKeyboardButton('💎 Качество материалов', callback_data='faq_quality'))
    return markup

# Ссылка на менеджера + отзывы
def contact_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton('💬 Позвать живого менеджера прямо сюда', callback_data='call_operator'))
    markup.add(types.InlineKeyboardButton('⭐️ Читать отзывы ВКонтакте', url='https://vk.com/astrey.store?w=app6326142_-200424574'))
    return markup

# Помощник при автоответах (чтобы клиент не зависал)
def ai_fallback_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton('🌌 Запустить конструктор подарка', text='🌌 Запустить конструктор подарка', callback_data='quiz3_format_star_map'))
    markup.add(types.InlineKeyboardButton('💬 Связаться с живым менеджером', callback_data='call_operator'))
    return markup

# Админ-панель
def admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton('📊 Статистика бота', callback_data='admin_stats'))
    markup.add(types.InlineKeyboardButton('📣 Создать рассылку', callback_data='admin_broadcast'))
    markup.add(types.InlineKeyboardButton('📦 Управление заказами', callback_data='admin_orders'))
    return markup

def admin_order_item_keyboard(order_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton('✅ В работу', callback_data=f"admin_status_{order_id}_в работе"),
        types.InlineKeyboardButton('🚚 Доставлен', callback_data=f"admin_status_{order_id}_доставлен")
    )
    markup.add(
        types.InlineKeyboardButton('💳 Оплачен', callback_data=f"admin_status_{order_id}_оплачен"),
        types.InlineKeyboardButton('❌ Отменить', callback_data=f"admin_status_{order_id}_отменен")
    )
    return markup

# Кнопки для админа при вызове менеджера
def admin_chat_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton('💬 Начать диалог с клиентом', callback_data=f"admin_chat_{user_id}"))
    return markup

# Кнопка завершения диалога со стороны админа
def admin_stop_chat_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton('❌ Завершить диалог', callback_data=f"admin_stopchat_{user_id}"))
    return markup
