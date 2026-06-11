import os
import sqlite3
from datetime import datetime

# Railway позволяет монтировать персистентные диски (Volume).
# Если задана переменная окружения DB_DIR, мы сохраняем базу данных туда, чтобы данные не стирались при перезапуске.
DB_DIR = os.getenv('DB_DIR', '')
if DB_DIR:
    os.makedirs(DB_DIR, exist_ok=True)
    DB_PATH = os.path.join(DB_DIR, 'astrey_bot.db')
else:
    DB_PATH = 'astrey_bot.db'

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TEXT,
            last_activity TEXT,
            quiz_state TEXT,
            quiz_data TEXT,
            discount_claimed INTEGER DEFAULT 0,
            is_in_chat INTEGER DEFAULT 0,
            operator_id INTEGER DEFAULT NULL
        )
    ''')
    
    # Таблица заказов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            product_type TEXT, -- 'star_map', 'soundwave', 'photo_poster'
            event_date TEXT,
            event_city TEXT,
            custom_phrase TEXT,
            audio_source TEXT, -- Ссылка на трек или аудиофайл
            poster_size TEXT,  -- A4, A3, A2, 30x40, 40x50, 50x70
            frame_type TEXT,   -- Без рамки, Дерево (Черная), Дерево (Белая), Премиум
            packaging TEXT,    -- Обычная, Подарочный тубус
            client_name TEXT,
            client_phone TEXT,
            delivery_address TEXT,
            price REAL,
            status TEXT DEFAULT 'новый', -- 'новый', 'оплачен', 'в работе', 'доставлен', 'отменен'
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    # Таблица промокодов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            discount_percent INTEGER,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # Пытаемся добавить колонки для старых БД на всякий случай
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_in_chat INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Колонка уже есть
        
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN operator_id INTEGER DEFAULT NULL")
    except sqlite3.OperationalError:
        pass # Колонка уже есть

    # Добавим дефолтные промокоды
    cursor.execute("INSERT OR IGNORE INTO promocodes (code, discount_percent, is_active) VALUES ('ASTREY10', 10, 1)")
    cursor.execute("INSERT OR IGNORE INTO promocodes (code, discount_percent, is_active) VALUES ('STARFALL', 15, 1)")
    cursor.execute("INSERT OR IGNORE INTO promocodes (code, discount_percent, is_active) VALUES ('GIFT20', 20, 1)")
    
    conn.commit()
    conn.close()

# Функции для работы с пользователями
def add_user(user_id, username, first_name):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT INTO users (user_id, username, first_name, created_at, last_activity)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_activity = excluded.last_activity
    ''', (user_id, username, first_name, now, now))
    conn.commit()
    conn.close()

def update_last_activity(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('UPDATE users SET last_activity = ? WHERE user_id = ?', (now, user_id))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_user_quiz(user_id, state, data_json):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET quiz_state = ?, quiz_data = ? WHERE user_id = ?', (state, data_json, user_id))
    conn.commit()
    conn.close()

def claim_discount(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET discount_claimed = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name FROM users')
    rows = cursor.fetchall()
    conn.close()
    return rows

# Управление Live Chat режимом
def set_user_chat_mode(user_id, is_in_chat, operator_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_in_chat = ?, operator_id = ? WHERE user_id = ?', (is_in_chat, operator_id, user_id))
    conn.commit()
    conn.close()

# Функции для работы с заказами
def create_order(user_id, username, product_type, event_date, event_city, custom_phrase, audio_source, poster_size, frame_type, packaging, client_name, client_phone, delivery_address, price):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT INTO orders (
            user_id, username, product_type, event_date, event_city, custom_phrase, 
            audio_source, poster_size, frame_type, packaging, client_name, client_phone, 
            delivery_address, price, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, product_type, event_date, event_city, custom_phrase, 
          audio_source, poster_size, frame_type, packaging, client_name, client_phone, 
          delivery_address, price, now))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id

def get_order(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_user_orders(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY order_id DESC', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_order_status(order_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE orders SET status = ? WHERE order_id = ?', (status, order_id))
    conn.commit()
    conn.close()

# Проверка промокода
def check_promocode(code):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT discount_percent FROM promocodes WHERE code = ? AND is_active = 1', (code.upper().strip(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['discount_percent']
    return None

# Статистика для админки
def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM orders')
    total_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'новый'")
    new_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(price) FROM orders WHERE status != 'отменен'")
    total_revenue = cursor.fetchone()[0] or 0.0
    
    conn.close()
    return {
        'total_users': total_users,
        'total_orders': total_orders,
        'new_orders': new_orders,
        'total_revenue': total_revenue
    }
