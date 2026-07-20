import os
import json
from typing import Optional, List, Dict, Any


class Database:
    """Простая обёртка над SQLite, с возможностью переключения на PostgreSQL."""
    def __init__(self):
        self._conn = None
        self._is_pg = False
        self._path = ""

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
            return await self._conn.execute(q, *v)
        else:
            return await self._conn.execute(q, v if v else None)

    async def executemany(self, query: str, params_list: list):
        q = self._convert_query(query)
        if self._is_pg:
            return await self._conn.executemany(q, [list(p.values()) for p in params_list])
        else:
            return await self._conn.executemany(q, [tuple(p.values()) for p in params_list])

    async def fetch_one(self, query: str, params: dict = None):
        q = self._convert_query(query)
        v = self._vals(params)
        if self._is_pg:
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
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                direction TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT DEFAULT NOW()
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
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                direction TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
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

async def upsert_user(telegram_id: int, username: str = None, first_name: str = None,
                      last_name: str = None, platform: str = "telegram") -> None:
    await _DB.execute(
        "INSERT INTO users (telegram_id, username, first_name, last_name, platform) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(telegram_id) DO UPDATE SET "
        "username = COALESCE(excluded.username, username), "
        "first_name = COALESCE(excluded.first_name, first_name), "
        "last_name = COALESCE(excluded.last_name, last_name), "
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
#  MESSAGES
# ─────────────────────────────────────────────

async def log_message(telegram_id: int, direction: str, text: str) -> None:
    await _DB.execute(
        "INSERT INTO messages (telegram_id, direction, text) VALUES (?, ?, ?)",
        {"1": telegram_id, "2": direction, "3": text[:4000]}
    )


async def get_user_messages(telegram_id: int, limit: int = 20) -> List[Dict]:
    rows = await _DB.fetch_all(
        "SELECT * FROM messages WHERE telegram_id = ? ORDER BY created_at DESC LIMIT ?",
        {"1": telegram_id, "2": limit}
    )
    return list(reversed(rows))


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


# ─────────────────────────────────────────────
#  EXPORT / IMPORT
# ─────────────────────────────────────────────

DUMP_FILE = "astreybot_dump.json"


async def export_data() -> str:
    data = {}
    for table in ["users", "messages", "leads", "admin_takeovers", "broadcasts", "subscriptions"]:
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
