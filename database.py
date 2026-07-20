import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from databases import Database

_DB: Database = None
_DB_PATH: str = ""


def get_db() -> Database:
    return _DB


def set_db_path(path: str):
    global _DB_PATH
    _DB_PATH = path
    os.makedirs(os.path.dirname(os.path.abspath(path)) if os.path.dirname(path) else ".", exist_ok=True)


async def init_db():
    global _DB
    db_url = os.environ.get("DATABASE_URL") or f"sqlite:///{_DB_PATH}"
    _DB = Database(db_url)
    await _DB.connect()

    await _DB.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
            updated_at TEXT DEFAULT (CURRENT_TIMESTAMP)
        )
    """)
    await _DB.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id BIGINT NOT NULL,
            direction TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT DEFAULT (CURRENT_TIMESTAMP)
        )
    """)
    await _DB.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            created_at TEXT DEFAULT (CURRENT_TIMESTAMP),
            updated_at TEXT DEFAULT (CURRENT_TIMESTAMP)
        )
    """)
    await _DB.execute("""
        CREATE TABLE IF NOT EXISTS admin_takeovers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            started_at TEXT DEFAULT (CURRENT_TIMESTAMP),
            ended_at TEXT
        )
    """)
    await _DB.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id BIGINT NOT NULL,
            text TEXT NOT NULL,
            sent_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (CURRENT_TIMESTAMP)
        )
    """)
    await _DB.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id BIGINT NOT NULL,
            platform TEXT NOT NULL,
            order_id INTEGER NOT NULL,
            email TEXT,
            created_at TEXT DEFAULT (CURRENT_TIMESTAMP)
        )
    """)

    # Миграции для старых колонок
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
#  USERS
# ─────────────────────────────────────────────

async def upsert_user(telegram_id: int, username: str = None, first_name: str = None,
                      last_name: str = None, platform: str = "telegram") -> None:
    await _DB.execute("""
        INSERT INTO users (telegram_id, username, first_name, last_name, platform)
        VALUES (:tid, :un, :fn, :ln, :pl)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = COALESCE(excluded.username, username),
            first_name = COALESCE(excluded.first_name, first_name),
            last_name = COALESCE(excluded.last_name, last_name),
            updated_at = CURRENT_TIMESTAMP
    """, {"tid": telegram_id, "un": username, "fn": first_name, "ln": last_name, "pl": platform})


async def get_user(telegram_id: int) -> Optional[Dict]:
    row = await _DB.fetch_one("SELECT * FROM users WHERE telegram_id = :tid", {"tid": telegram_id})
    return dict(row) if row else None


async def update_user(telegram_id: int, **kwargs) -> None:
    if not kwargs:
        return
    kwargs["tid"] = telegram_id
    fields = ", ".join(f"{k} = :{k}" for k in kwargs if k != "tid")
    await _DB.execute(
        f"UPDATE users SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = :tid",
        kwargs
    )


async def get_all_user_ids() -> List[int]:
    rows = await _DB.fetch_all("SELECT telegram_id FROM users")
    return [r["telegram_id"] for r in rows]


async def update_last_bot_message(telegram_id: int) -> None:
    await _DB.execute(
        "UPDATE users SET last_bot_message_at = CURRENT_TIMESTAMP, inactivity_notified = 0 WHERE telegram_id = :tid",
        {"tid": telegram_id}
    )


# ─────────────────────────────────────────────
#  MESSAGES
# ─────────────────────────────────────────────

async def log_message(telegram_id: int, direction: str, text: str) -> None:
    await _DB.execute(
        "INSERT INTO messages (telegram_id, direction, text) VALUES (:tid, :dir, :txt)",
        {"tid": telegram_id, "dir": direction, "txt": text[:4000]}
    )


async def get_user_messages(telegram_id: int, limit: int = 20) -> List[Dict]:
    rows = await _DB.fetch_all(
        "SELECT * FROM messages WHERE telegram_id = :tid ORDER BY created_at DESC LIMIT :lim",
        {"tid": telegram_id, "lim": limit}
    )
    return [dict(r) for r in reversed(rows)]


# ─────────────────────────────────────────────
#  LEADS
# ─────────────────────────────────────────────

async def upsert_lead(telegram_id: int, **kwargs) -> int:
    existing = await _DB.fetch_one(
        "SELECT id FROM leads WHERE telegram_id = :tid AND status NOT IN ('converted', 'lost')",
        {"tid": telegram_id}
    )
    if existing:
        lead_id = existing["id"]
        if kwargs:
            kwargs["lid"] = lead_id
            fields = ", ".join(f"{k} = :{k}" for k in kwargs if k != "lid")
            await _DB.execute(
                f"UPDATE leads SET {fields}, updated_at = CURRENT_TIMESTAMP WHERE id = :lid",
                kwargs
            )
        return lead_id

    kwargs["telegram_id"] = telegram_id
    kwargs.setdefault("stage", "started")
    cols = ", ".join(kwargs.keys())
    params = ", ".join(f":{k}" for k in kwargs)
    row = await _DB.fetch_one(
        f"INSERT INTO leads ({cols}) VALUES ({params}) RETURNING id",
        kwargs
    )
    return row["id"]


async def get_lead(lead_id: int) -> Optional[Dict]:
    row = await _DB.fetch_one("SELECT * FROM leads WHERE id = :lid", {"lid": lead_id})
    return dict(row) if row else None


async def get_user_lead(telegram_id: int) -> Optional[Dict]:
    row = await _DB.fetch_one(
        "SELECT * FROM leads WHERE telegram_id = :tid ORDER BY created_at DESC LIMIT 1",
        {"tid": telegram_id}
    )
    return dict(row) if row else None


async def update_lead_status(lead_id: int, status: str) -> None:
    await _DB.execute(
        "UPDATE leads SET status = :st, updated_at = CURRENT_TIMESTAMP WHERE id = :lid",
        {"st": status, "lid": lead_id}
    )


async def update_lead_notes(lead_id: int, notes: str) -> None:
    await _DB.execute(
        "UPDATE leads SET admin_notes = :nt, updated_at = CURRENT_TIMESTAMP WHERE id = :lid",
        {"nt": notes, "lid": lead_id}
    )


async def get_leads(status: str = None, page: int = 0, per_page: int = 10) -> List[Dict]:
    offset = page * per_page
    if status and status != "all":
        rows = await _DB.fetch_all(
            "SELECT * FROM leads WHERE status = :st ORDER BY created_at DESC LIMIT :lim OFFSET :off",
            {"st": status, "lim": per_page, "off": offset}
        )
    else:
        rows = await _DB.fetch_all(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT :lim OFFSET :off",
            {"lim": per_page, "off": offset}
        )
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
#  STATISTICS
# ─────────────────────────────────────────────

async def get_stats() -> Dict[str, Any]:
    total_users = (await _DB.fetch_one("SELECT COUNT(*) as c FROM users"))["c"]
    today_users = (await _DB.fetch_one(
        "SELECT COUNT(*) as c FROM users WHERE created_at >= CURRENT_DATE"
    ))["c"]
    today_leads = (await _DB.fetch_one(
        "SELECT COUNT(*) as c FROM leads WHERE created_at >= CURRENT_DATE"
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
        "INSERT INTO admin_takeovers (admin_id, user_id) VALUES (:aid, :uid)",
        {"aid": admin_id, "uid": user_id}
    )


async def end_takeover(admin_id: int, user_id: int) -> None:
    await _DB.execute(
        "UPDATE admin_takeovers SET ended_at = CURRENT_TIMESTAMP WHERE admin_id = :aid AND user_id = :uid AND ended_at IS NULL",
        {"aid": admin_id, "uid": user_id}
    )


# ─────────────────────────────────────────────
#  SUBSCRIPTIONS
# ─────────────────────────────────────────────

async def add_subscription(chat_id: int, platform: str, order_id: int, email: str = None) -> None:
    await _DB.execute(
        "INSERT INTO subscriptions (chat_id, platform, order_id, email) VALUES (:cid, :pl, :oid, :em)",
        {"cid": chat_id, "pl": platform, "oid": order_id, "em": email}
    )


async def remove_subscription(chat_id: int, order_id: int) -> None:
    await _DB.execute(
        "DELETE FROM subscriptions WHERE chat_id = :cid AND order_id = :oid",
        {"cid": chat_id, "oid": order_id}
    )


async def get_user_subscriptions(chat_id: int) -> List[Dict]:
    rows = await _DB.fetch_all(
        "SELECT * FROM subscriptions WHERE chat_id = :cid ORDER BY created_at DESC",
        {"cid": chat_id}
    )
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
#  EXPORT / IMPORT (для переноса на PostgreSQL)
# ─────────────────────────────────────────────

DUMP_FILE = "astreybot_dump.json"


async def export_data() -> str:
    data = {}
    for table in ["users", "messages", "leads", "admin_takeovers", "broadcasts", "subscriptions"]:
        rows = await _DB.fetch_all(f"SELECT * FROM {table}")
        data[table] = [dict(r) for r in rows]
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
        params = ", ".join(f":{k}" for k in rows[0])
        for row in rows:
            try:
                await _DB.execute(f"INSERT INTO {table} ({cols}) VALUES ({params})", row)
                total += 1
            except Exception:
                pass
    return total
