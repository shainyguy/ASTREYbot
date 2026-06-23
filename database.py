import aiosqlite
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


_DB_PATH: str = ""


def set_db_path(path: str):
    global _DB_PATH
    _DB_PATH = path
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


async def init_db():
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("""
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
        """)
        await db.commit()

    # Миграция для существующих БД
    async with aiosqlite.connect(_DB_PATH) as db:
        for stmt in [
            "ALTER TABLE users ADD COLUMN platform TEXT DEFAULT 'telegram'",
            "ALTER TABLE leads ADD COLUMN platform TEXT DEFAULT 'telegram'",
            "ALTER TABLE users ADD COLUMN last_bot_message_at TEXT",
            "ALTER TABLE users ADD COLUMN inactivity_notified INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(stmt)
                await db.commit()
            except Exception:
                pass  # Колонка уже существует


# ─────────────────────────────────────────────
#  USERS
# ─────────────────────────────────────────────

async def upsert_user(telegram_id: int, username: str = None, first_name: str = None,
                      last_name: str = None, platform: str = "telegram") -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (telegram_id, username, first_name, last_name, platform)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = COALESCE(excluded.username, username),
                first_name = COALESCE(excluded.first_name, first_name),
                last_name = COALESCE(excluded.last_name, last_name),
                updated_at = datetime('now')
        """, (telegram_id, username, first_name, last_name, platform))
        await db.commit()


async def update_last_bot_message(telegram_id: int) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_bot_message_at = datetime('now'), inactivity_notified = 0 WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db.commit()


async def get_user(telegram_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_user(telegram_id: int, **kwargs) -> None:
    if not kwargs:
        return
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [telegram_id]
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            f"UPDATE users SET {fields}, updated_at = datetime('now') WHERE telegram_id = ?",
            values
        )
        await db.commit()


async def get_all_user_ids() -> List[int]:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute("SELECT telegram_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]


# ─────────────────────────────────────────────
#  MESSAGES
# ─────────────────────────────────────────────

async def log_message(telegram_id: int, direction: str, text: str) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (telegram_id, direction, text) VALUES (?, ?, ?)",
            (telegram_id, direction, text[:4000])
        )
        await db.commit()


async def get_user_messages(telegram_id: int, limit: int = 20) -> List[Dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM messages WHERE telegram_id = ? ORDER BY created_at DESC LIMIT ?",
            (telegram_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in reversed(rows)]


# ─────────────────────────────────────────────
#  LEADS
# ─────────────────────────────────────────────

async def upsert_lead(telegram_id: int, **kwargs) -> int:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM leads WHERE telegram_id = ? AND status NOT IN ('converted', 'lost')",
            (telegram_id,)
        ) as cursor:
            existing = await cursor.fetchone()

        if existing:
            lead_id = existing[0]
            if kwargs:
                fields = ", ".join(f"{k} = ?" for k in kwargs)
                values = list(kwargs.values()) + [lead_id]
                await db.execute(
                    f"UPDATE leads SET {fields}, updated_at = datetime('now') WHERE id = ?",
                    values
                )
        else:
            kwargs["telegram_id"] = telegram_id
            kwargs.setdefault("stage", "started")
            cols = ", ".join(kwargs.keys())
            placeholders = ", ".join("?" * len(kwargs))
            async with db.execute(
                f"INSERT INTO leads ({cols}) VALUES ({placeholders})",
                list(kwargs.values())
            ) as cursor:
                lead_id = cursor.lastrowid

        await db.commit()
        return lead_id


async def get_lead(lead_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_user_lead(telegram_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM leads WHERE telegram_id = ? ORDER BY created_at DESC LIMIT 1",
            (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_lead_status(lead_id: int, status: str) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "UPDATE leads SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, lead_id)
        )
        await db.commit()


async def update_lead_notes(lead_id: int, notes: str) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "UPDATE leads SET admin_notes = ?, updated_at = datetime('now') WHERE id = ?",
            (notes, lead_id)
        )
        await db.commit()


async def get_leads(status: str = None, page: int = 0, per_page: int = 10) -> List[Dict]:
    offset = page * per_page
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status and status != "all":
            async with db.execute(
                "SELECT * FROM leads WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, per_page, offset)
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM leads ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (per_page, offset)
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
#  STATISTICS
# ─────────────────────────────────────────────

async def get_stats() -> Dict[str, Any]:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= date('now')"
        ) as c:
            today_users = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM leads WHERE created_at >= date('now')"
        ) as c:
            today_leads = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM leads WHERE phone IS NOT NULL AND phone != ''"
        ) as c:
            conversions = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM leads") as c:
            total_leads = (await c.fetchone())[0]

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
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT INTO admin_takeovers (admin_id, user_id) VALUES (?, ?)",
            (admin_id, user_id)
        )
        await db.commit()


async def end_takeover(admin_id: int, user_id: int) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """UPDATE admin_takeovers SET ended_at = datetime('now')
               WHERE admin_id = ? AND user_id = ? AND ended_at IS NULL""",
            (admin_id, user_id)
        )
        await db.commit()
