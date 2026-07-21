import os
import json
import re
import asyncio
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class Database:
    """Простая обёртка над SQLite / PostgreSQL с поддержкой конкурентного доступа."""
    def __init__(self):
        self._conn = None
        self._is_pg = False
        self._path = ""
        self._lock = asyncio.Lock()

    async def connect(self, path_or_url: str):
        self._path = path_or_url
        if path_or_url.startswith("postgresql"):
            self._is_pg = True
            import asyncpg
            self._conn = await asyncpg.connect(path_or_url)
        else:
            import aiosqlite
            path = path_or_url.replace("sqlite:///", "")
            self._conn = await aiosqlite.connect(path)
            self._conn.row_factory = aiosqlite.Row

    async def disconnect(self):
        if self._conn:
            await self._conn.close()

    def _convert_query(self, query: str) -> str:
        if self._is_pg:
            i = 0
            result = []
            for ch in query:
                if ch == '?':
                    i += 1
                    result.append(f'${i}')
                else:
                    result.append(ch)
            return ''.join(result)
        return query

    def _vals(self, params: dict = None):
        if params is None:
            return []
        return list(params.values())

    async def execute(self, query: str, params: dict = None):
        q = self._convert_query(query)
        v = self._vals(params)
        if self._is_pg:
            async with self._lock:
                return await self._conn.execute(q, *v)
        else:
            return await self._conn.execute(q, v if v else None)

    async def executemany(self, query: str, params_list: list):
        q = self._convert_query(query)
        if self._is_pg:
            async with self._lock:
                return await self._conn.executemany(q, [list(p.values()) for p in params_list])
        else:
            return await self._conn.executemany(q, [tuple(p.values()) for p in params_list])

    async def fetch_one(self, query: str, params: dict = None):
        q = self._convert_query(query)
        v = self._vals(params)
        if self._is_pg:
            async with self._lock:
                row = await self._conn.fetchrow(q, *v)
                return dict(row) if row else None
        else:
            async with self._conn.execute(q, v if v else ()) as c:
                row = await c.fetchone()
                return dict(row) if row else None

    async def fetch_all(self, query: str, params: dict = None):
        q = self._convert_query(query)
        v = self._vals(params)
        if self._is_pg:
            async with self._lock:
                rows = await self._conn.fetch(q, *v)
                return [dict(r) for r in rows]
        else:
            async with self._conn.execute(q, v if v else ()) as c:
                rows = await c.fetchall()
                return [dict(r) for r in rows]

    async def execute_script(self, script: str):
        if not self._is_pg:
            await self._conn.executescript(script)

    @property
    def is_pg(self):
        return self._is_pg


_DB: Database = None
_DB_PATH: str = ""


def get_db() -> Database:
    return _DB


def set_db_path(path: str):
    global _DB_PATH
    _DB_PATH = path
    d = os.path.dirname(os.path.abspath(path)) if os.path.dirname(path) else "."
    if d:
        os.makedirs(d, exist_ok=True)


async def init_db():
    global _DB
    _DB = Database()
    db_url = os.environ.get("DATABASE_URL") or f"sqlite:///{_DB_PATH}"
    await _DB.connect(db_url)

    # Логируем что реально подключилось: DATABASE_URL молча побеждает
    # DATABASE_PATH, и по логу нельзя было понять, где лежат данные
    if _DB.is_pg:
        host = db_url.split("@")[-1].split("/")[0] if "@" in db_url else "?"
        logger.info(f"База: PostgreSQL ({host}) — DATABASE_PATH не используется")
    else:
        logger.info(f"База: SQLite ({_DB_PATH})")

    if _DB.is_pg:
        # PostgreSQL синтаксис
        await _DB.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                full_name TEXT,
                phone TEXT,
                stage TEXT DEFAULT 'welcome',
                occasion TEXT,
                recipient TEXT,
                budget TEXT,
                product_interest TEXT,
                ai_confusion_count INTEGER DEFAULT 0,
                admin_authorized INTEGER DEFAULT 0,
                notes TEXT,
                platform TEXT DEFAULT 'telegram',
                last_bot_message_at TEXT,
                inactivity_notified INTEGER DEFAULT 0,
                created_at TEXT DEFAULT NOW(),
                updated_at TEXT DEFAULT NOW()
            )
        """)
        await _DB.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                platform TEXT DEFAULT 'telegram',
                product TEXT,
                format TEXT,
                event_date TEXT,
                event_place TEXT,
                phrase TEXT,
                design TEXT,
                postcard INTEGER DEFAULT 0,
                full_name TEXT,
                phone TEXT,
                amount INTEGER DEFAULT 0,
                status TEXT DEFAULT 'awaiting_payment',
                nudge_level INTEGER DEFAULT 0,
                mockup_comment TEXT,
                created_at TEXT DEFAULT NOW(),
                updated_at TEXT DEFAULT NOW()
            )
        """)
        await _DB.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                stage TEXT NOT NULL,
                occasion TEXT,
                recipient TEXT,
                budget TEXT,
                product_interest TEXT,
                full_name TEXT,
                username TEXT,
                phone TEXT,
                status TEXT DEFAULT 'new',
                notes TEXT,
                admin_notes TEXT,
                platform TEXT DEFAULT 'telegram',
                created_at TEXT DEFAULT NOW(),
                updated_at TEXT DEFAULT NOW()
            )
        """)
        await _DB.execute("""
            CREATE TABLE IF NOT EXISTS admin_takeovers (
                id SERIAL PRIMARY KEY,
                admin_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                started_at TEXT DEFAULT NOW(),
                ended_at TEXT
            )
        """)
        await _DB.execute("""
            CREATE TABLE IF NOT EXISTS broadcasts (
                id SERIAL PRIMARY KEY,
                admin_id BIGINT NOT NULL,
                text TEXT NOT NULL,
                sent_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT NOW()
            )
        """)
        await _DB.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                platform TEXT NOT NULL,
                order_id INTEGER NOT NULL,
                email TEXT,
                created_at TEXT DEFAULT NOW()
            )
        """)
        await _DB.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                platform TEXT DEFAULT 'telegram',
                event_name TEXT NOT NULL,
                event_date TEXT NOT NULL,
                remind_days_before INTEGER DEFAULT 3,
                reminded_years TEXT DEFAULT '',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT NOW()
            )
        """)
    else:
        # SQLite синтаксис
        await _DB.execute_script("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                full_name TEXT,
                phone TEXT,
                stage TEXT DEFAULT 'welcome',
                occasion TEXT,
                recipient TEXT,
                budget TEXT,
                product_interest TEXT,
                ai_confusion_count INTEGER DEFAULT 0,
                admin_authorized INTEGER DEFAULT 0,
                notes TEXT,
                platform TEXT DEFAULT 'telegram',
                last_bot_message_at TEXT,
                inactivity_notified INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                platform TEXT DEFAULT 'telegram',
                product TEXT,
                format TEXT,
                event_date TEXT,
                event_place TEXT,
                phrase TEXT,
                design TEXT,
                postcard INTEGER DEFAULT 0,
                full_name TEXT,
                phone TEXT,
                amount INTEGER DEFAULT 0,
                status TEXT DEFAULT 'awaiting_payment',
                nudge_level INTEGER DEFAULT 0,
                mockup_comment TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                stage TEXT NOT NULL,
                occasion TEXT,
                recipient TEXT,
                budget TEXT,
                product_interest TEXT,
                full_name TEXT,
                username TEXT,
                phone TEXT,
                status TEXT DEFAULT 'new',
                notes TEXT,
                admin_notes TEXT,
                platform TEXT DEFAULT 'telegram',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS admin_takeovers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                started_at TEXT DEFAULT (datetime('now')),
                ended_at TEXT
            );
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                sent_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                order_id INTEGER NOT NULL,
                email TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                platform TEXT DEFAULT 'telegram',
                event_name TEXT NOT NULL,
                event_date TEXT NOT NULL,
                remind_days_before INTEGER DEFAULT 3,
                reminded_years TEXT DEFAULT '',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        # Миграции старых колонок
        for col in ["platform", "last_bot_message_at", "inactivity_notified"]:
            try:
                await _DB.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
            except Exception:
                pass
        try:
            await _DB.execute("ALTER TABLE leads ADD COLUMN platform TEXT DEFAULT 'telegram'")
        except Exception:
            pass

    # Догоняем схему на уже существующих базах
    try:
        await _DB.execute("ALTER TABLE orders ADD COLUMN nudge_level INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        await _DB.execute("ALTER TABLE orders ADD COLUMN mockup_comment TEXT")
    except Exception:
        pass

    # Архив переписки больше не ведём — последние реплики живут в памяти
    # (recent.py). Работает и для PostgreSQL, и для SQLite.
    try:
        await _DB.execute("DROP TABLE IF EXISTS messages")
        logger.info("Таблица messages удалена — переписка не хранится")
    except Exception as e:
        logger.warning(f"messages drop: {e}")


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _now() -> str:
    if _DB and _DB.is_pg:
        return "NOW()"
    return "datetime('now')"


def _on_conflict(col: str) -> str:
    if _DB and _DB.is_pg:
        return f"ON CONFLICT({col}) DO UPDATE SET"
    return f"ON CONFLICT({col}) DO UPDATE SET"


def _returning_id() -> str:
    if _DB and _DB.is_pg:
        return " RETURNING id"
    return ""


# ─────────────────────────────────────────────
#  USERS
# ─────────────────────────────────────────────

def _t() -> str:
    if _DB and _DB.is_pg:
        return "users."
    return ""


async def upsert_user(telegram_id: int, username: str = None, first_name: str = None,
                      last_name: str = None, platform: str = "telegram") -> None:
    t = _t()
    await _DB.execute(
        "INSERT INTO users (telegram_id, username, first_name, last_name, platform) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(telegram_id) DO UPDATE SET "
        f"username = COALESCE(excluded.username, {t}username), "
        f"first_name = COALESCE(excluded.first_name, {t}first_name), "
        f"last_name = COALESCE(excluded.last_name, {t}last_name), "
        f"updated_at = {_now()}",
        {"1": telegram_id, "2": username, "3": first_name, "4": last_name, "5": platform}
    )


async def get_user(telegram_id: int) -> Optional[Dict]:
    return await _DB.fetch_one("SELECT * FROM users WHERE telegram_id = ?", {"1": telegram_id})


async def update_user(telegram_id: int, **kwargs) -> None:
    if not kwargs:
        return
    kwargs["tid"] = telegram_id
    fields = ", ".join(f"{k} = ?" for k in kwargs if k != "tid")
    params = {str(i): v for i, (k, v) in enumerate(kwargs.items())}
    await _DB.execute(
        f"UPDATE users SET {fields}, updated_at = {_now()} WHERE telegram_id = ?",
        params
    )


async def get_all_user_ids() -> List[int]:
    rows = await _DB.fetch_all("SELECT telegram_id FROM users")
    return [list(r.values())[0] if isinstance(r, dict) else r["telegram_id"] for r in rows]


async def update_last_bot_message(telegram_id: int) -> None:
    await _DB.execute(
        f"UPDATE users SET last_bot_message_at = {_now()}, inactivity_notified = 0 WHERE telegram_id = ?",
        {"1": telegram_id}
    )


# ─────────────────────────────────────────────
#  ЗАКАЗЫ
# ─────────────────────────────────────────────

ORDER_FIELDS = (
    "platform", "product", "format", "event_date", "event_place",
    "phrase", "design", "postcard", "full_name", "phone", "amount", "status",
    "nudge_level", "mockup_comment",
)


async def create_order(telegram_id: int, **kwargs) -> int:
    fields = ["telegram_id"] + [k for k in kwargs if k in ORDER_FIELDS]
    values = {"1": telegram_id}
    for i, key in enumerate(fields[1:], start=2):
        values[str(i)] = kwargs[key]
    placeholders = ", ".join("?" for _ in fields)
    sql = f"INSERT INTO orders ({', '.join(fields)}) VALUES ({placeholders}){_returning_id()}"

    if _DB.is_pg:
        row = await _DB.fetch_one(sql, values)
        return row["id"] if row else 0
    await _DB.execute(sql, values)
    row = await _DB.fetch_one(
        "SELECT id FROM orders WHERE telegram_id = ? ORDER BY id DESC LIMIT 1",
        {"1": telegram_id}
    )
    return row["id"] if row else 0


async def update_order(order_id: int, **kwargs) -> None:
    updates = {k: v for k, v in kwargs.items() if k in ORDER_FIELDS}
    if not updates:
        return
    sets, values = [], {}
    for i, (key, val) in enumerate(updates.items(), start=1):
        sets.append(f"{key} = ?")
        values[str(i)] = val
    values[str(len(updates) + 1)] = order_id
    await _DB.execute(
        f"UPDATE orders SET {', '.join(sets)}, updated_at = {_now()} WHERE id = ?",
        values
    )


async def get_order(order_id: int) -> Optional[Dict]:
    return await _DB.fetch_one("SELECT * FROM orders WHERE id = ?", {"1": order_id})


async def get_orders(status: str = None, limit: int = 20) -> List[Dict]:
    if status and status != "all":
        return await _DB.fetch_all(
            "SELECT * FROM orders WHERE status = ? ORDER BY id DESC LIMIT ?",
            {"1": status, "2": limit}
        )
    return await _DB.fetch_all(
        "SELECT * FROM orders ORDER BY id DESC LIMIT ?", {"1": limit}
    )


# ─────────────────────────────────────────────
#  LEADS
# ─────────────────────────────────────────────

async def upsert_lead(telegram_id: int, **kwargs) -> int:
    existing = await _DB.fetch_one(
        "SELECT id FROM leads WHERE telegram_id = ? AND status NOT IN ('converted', 'lost')",
        {"1": telegram_id}
    )
    if existing:
        lead_id = existing["id"] if isinstance(existing, dict) else existing[0]
        if kwargs:
            kwargs["lid"] = lead_id
            fields = ", ".join(f"{k} = ?" for k in kwargs)
            params = {str(i): v for i, (k, v) in enumerate(kwargs.items())}
            await _DB.execute(
                f"UPDATE leads SET {fields}, updated_at = {_now()} WHERE id = ?",
                params
            )
        return lead_id

    kwargs["telegram_id"] = telegram_id
    kwargs.setdefault("stage", "started")
    cols = ", ".join(kwargs.keys())
    ph = ", ".join("?" for _ in kwargs)
    params = {str(i): v for i, (k, v) in enumerate(kwargs.items())}
    rid = _returning_id()
    if rid:
        row = await _DB.fetch_one(f"INSERT INTO leads ({cols}) VALUES ({ph}){rid}", params)
        return row["id"] if row else 0
    else:
        await _DB.execute(f"INSERT INTO leads ({cols}) VALUES ({ph})", params)
        last = await _DB.fetch_one("SELECT MAX(id) as id FROM leads", {})
        return last["id"] if last else 0


async def get_lead(lead_id: int) -> Optional[Dict]:
    return await _DB.fetch_one("SELECT * FROM leads WHERE id = ?", {"1": lead_id})


async def get_user_lead(telegram_id: int) -> Optional[Dict]:
    return await _DB.fetch_one(
        "SELECT * FROM leads WHERE telegram_id = ? ORDER BY created_at DESC LIMIT 1",
        {"1": telegram_id}
    )


async def update_lead_status(lead_id: int, status: str) -> None:
    await _DB.execute(
        f"UPDATE leads SET status = ?, updated_at = {_now()} WHERE id = ?",
        {"1": status, "2": lead_id}
    )


async def update_lead_notes(lead_id: int, notes: str) -> None:
    await _DB.execute(
        f"UPDATE leads SET admin_notes = ?, updated_at = {_now()} WHERE id = ?",
        {"1": notes, "2": lead_id}
    )


async def get_leads(status: str = None, page: int = 0, per_page: int = 10) -> List[Dict]:
    offset = page * per_page
    if status and status != "all":
        rows = await _DB.fetch_all(
            "SELECT * FROM leads WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            {"1": status, "2": per_page, "3": offset}
        )
    else:
        rows = await _DB.fetch_all(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT ? OFFSET ?",
            {"1": per_page, "2": offset}
        )
    return rows


# ─────────────────────────────────────────────
#  STATISTICS
# ─────────────────────────────────────────────

async def get_stats() -> Dict[str, Any]:
    total_users = (await _DB.fetch_one("SELECT COUNT(*) as c FROM users"))["c"]
    if _DB and _DB.is_pg:
        today_users = (await _DB.fetch_one(
            "SELECT COUNT(*) as c FROM users WHERE created_at::date >= CURRENT_DATE"
        ))["c"]
        today_leads = (await _DB.fetch_one(
            "SELECT COUNT(*) as c FROM leads WHERE created_at::date >= CURRENT_DATE"
        ))["c"]
    else:
        today_users = (await _DB.fetch_one(
            "SELECT COUNT(*) as c FROM users WHERE created_at >= date('now')"
        ))["c"]
        today_leads = (await _DB.fetch_one(
            "SELECT COUNT(*) as c FROM leads WHERE created_at >= date('now')"
        ))["c"]
    conversions = (await _DB.fetch_one(
        "SELECT COUNT(*) as c FROM leads WHERE phone IS NOT NULL AND phone != ''"
    ))["c"]
    total_leads = (await _DB.fetch_one("SELECT COUNT(*) as c FROM leads"))["c"]

    conv_rate = round(conversions / total_leads * 100, 1) if total_leads > 0 else 0
    return {
        "total_users": total_users,
        "today_users": today_users,
        "today_leads": today_leads,
        "active_dialogs": today_users,
        "conversions": conversions,
        "conv_rate": conv_rate,
    }


# ─────────────────────────────────────────────
#  ADMIN TAKEOVERS
# ─────────────────────────────────────────────

async def start_takeover(admin_id: int, user_id: int) -> None:
    await _DB.execute(
        "INSERT INTO admin_takeovers (admin_id, user_id) VALUES (?, ?)",
        {"1": admin_id, "2": user_id}
    )


async def end_takeover(admin_id: int, user_id: int) -> None:
    await _DB.execute(
        f"UPDATE admin_takeovers SET ended_at = {_now()} WHERE admin_id = ? AND user_id = ? AND ended_at IS NULL",
        {"1": admin_id, "2": user_id}
    )


async def get_active_takeovers() -> List[Dict]:
    """Незакрытые перехваты — нужны, чтобы пережить рестарт контейнера."""
    return await _DB.fetch_all(
        "SELECT admin_id, user_id FROM admin_takeovers WHERE ended_at IS NULL"
    )


# ─────────────────────────────────────────────
#  SUBSCRIPTIONS
# ─────────────────────────────────────────────

async def add_subscription(chat_id: int, platform: str, order_id: int, email: str = None) -> None:
    await _DB.execute(
        "INSERT INTO subscriptions (chat_id, platform, order_id, email) VALUES (?, ?, ?, ?)",
        {"1": chat_id, "2": platform, "3": order_id, "4": email}
    )


async def remove_subscription(chat_id: int, order_id: int) -> None:
    await _DB.execute(
        "DELETE FROM subscriptions WHERE chat_id = ? AND order_id = ?",
        {"1": chat_id, "2": order_id}
    )


async def get_user_subscriptions(chat_id: int) -> List[Dict]:
    return await _DB.fetch_all(
        "SELECT * FROM subscriptions WHERE chat_id = ? ORDER BY created_at DESC",
        {"1": chat_id}
    )


async def get_subscribers(order_id: int) -> List[Dict]:
    return await _DB.fetch_all(
        "SELECT * FROM subscriptions WHERE order_id = ? ORDER BY created_at DESC",
        {"1": order_id}
    )


async def get_all_subscribers() -> List[Dict]:
    return await _DB.fetch_all(
        "SELECT * FROM subscriptions ORDER BY created_at DESC"
    )


# ─────────────────────────────────────────────
#  REMINDERS
# ─────────────────────────────────────────────

async def add_reminder(telegram_id: int, platform: str, event_name: str, event_date: str, remind_days_before: int) -> None:
    await _DB.execute(
        "INSERT INTO reminders (telegram_id, platform, event_name, event_date, remind_days_before) VALUES (?, ?, ?, ?, ?)",
        {"1": telegram_id, "2": platform, "3": event_name, "4": event_date, "5": remind_days_before}
    )


async def get_user_reminders(telegram_id: int) -> List[Dict]:
    return await _DB.fetch_all(
        "SELECT * FROM reminders WHERE telegram_id = ? AND active = 1 ORDER BY created_at DESC",
        {"1": telegram_id}
    )


async def deactivate_reminder(reminder_id: int, telegram_id: int) -> None:
    await _DB.execute(
        "UPDATE reminders SET active = 0 WHERE id = ? AND telegram_id = ?",
        {"1": reminder_id, "2": telegram_id}
    )


async def get_active_reminders() -> List[Dict]:
    return await _DB.fetch_all(
        "SELECT * FROM reminders WHERE active = 1"
    )


async def mark_reminder_sent(reminder_id: int, year: int) -> None:
    reminder = await _DB.fetch_one("SELECT reminded_years FROM reminders WHERE id = ?", {"1": reminder_id})
    if not reminder:
        return
    years = reminder.get("reminded_years") or ""
    if years:
        years += f",{year}"
    else:
        years = str(year)
    await _DB.execute(
        "UPDATE reminders SET reminded_years = ? WHERE id = ?",
        {"1": years, "2": reminder_id}
    )


# ─────────────────────────────────────────────
#  EXPORT / IMPORT
# ─────────────────────────────────────────────

DUMP_FILE = "astreybot_dump.json"


async def export_data() -> str:
    data = {}
    for table in ["users", "orders", "leads", "admin_takeovers", "broadcasts", "subscriptions"]:
        rows = await _DB.fetch_all(f"SELECT * FROM {table}")
        data[table] = rows
    with open(DUMP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return DUMP_FILE


async def import_data(dump_file: str = DUMP_FILE) -> int:
    if not os.path.exists(dump_file):
        return 0
    with open(dump_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    total = 0
    for table, rows in data.items():
        if not rows:
            continue
        cols = ", ".join(rows[0].keys())
        ph = ", ".join("?" for _ in rows[0])
        for row in rows:
            try:
                params = {str(i): v for i, (k, v) in enumerate(row.items())}
                await _DB.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", params)
                total += 1
            except Exception:
                pass
    return total
