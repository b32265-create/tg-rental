"""
database.py — SQLite database layer for Rent Bot
Tables: users, accounts, rentals, payments, countries
"""
import aiosqlite
import asyncio
from datetime import datetime
from config import DB_PATH


# ─────────────────────────────────────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────────────────────────────────────

async def init_db():
    """Create all tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        -- Users table
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            full_name     TEXT,
            balance       REAL    DEFAULT 0,
            referral_code TEXT    UNIQUE,
            referred_by   INTEGER,
            total_spent   REAL    DEFAULT 0,
            created_at    TEXT    DEFAULT (datetime('now')),
            is_banned     INTEGER DEFAULT 0
        );

        -- Countries table (admin managed)
        CREATE TABLE IF NOT EXISTS countries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    UNIQUE NOT NULL,
            flag_emoji  TEXT,
            price_inr   REAL    NOT NULL DEFAULT 50.0,
            is_active   INTEGER DEFAULT 1
        );

        -- Telegram Accounts table
        CREATE TABLE IF NOT EXISTS accounts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT    UNIQUE NOT NULL,
            session_str  TEXT    NOT NULL,
            country_id   INTEGER REFERENCES countries(id),
            is_available INTEGER DEFAULT 1,
            added_at     TEXT    DEFAULT (datetime('now')),
            total_rented INTEGER DEFAULT 0
        );

        -- Rentals table
        CREATE TABLE IF NOT EXISTS rentals (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            account_id   INTEGER NOT NULL,
            payment_id   TEXT,
            started_at   TEXT    DEFAULT (datetime('now')),
            expires_at   TEXT    NOT NULL,
            is_active    INTEGER DEFAULT 1,
            auto_logout  INTEGER DEFAULT 0
        );

        -- Payments table
        CREATE TABLE IF NOT EXISTS payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            razorpay_order  TEXT    UNIQUE,
            razorpay_payment TEXT,
            amount_inr      REAL    NOT NULL,
            status          TEXT    DEFAULT 'pending',
            purpose         TEXT,
            created_at      TEXT    DEFAULT (datetime('now'))
        );
        """)
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# USER OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def get_or_create_user(user_id: int, username: str = None, full_name: str = None) -> dict:
    """Fetch user or create if new. Returns user dict."""
    import random, string
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
        # New user
        ref_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        await db.execute(
            "INSERT INTO users (user_id, username, full_name, referral_code) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, ref_code)
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(await cursor.fetchone())


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_balance(user_id: int, delta: float):
    """Add or subtract balance."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (delta, user_id)
        )
        await db.commit()


async def set_balance(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()


async def get_all_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT user_id FROM users WHERE is_banned = 0")
        return [dict(r) for r in await cursor.fetchall()]


async def ban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def unban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_user_by_referral(code: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE referral_code = ?", (code,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_referred_by(user_id: int, referrer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET referred_by = ? WHERE user_id = ? AND referred_by IS NULL",
            (referrer_id, user_id)
        )
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# COUNTRY OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def add_country(name: str, flag: str, price: float) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT OR REPLACE INTO countries (name, flag_emoji, price_inr) VALUES (?, ?, ?)",
            (name, flag, price)
        )
        await db.commit()
        return cursor.lastrowid


async def get_countries(active_only: bool = True) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM countries"
        if active_only:
            q += " WHERE is_active = 1"
        q += " ORDER BY name"
        cursor = await db.execute(q)
        return [dict(r) for r in await cursor.fetchall()]


async def get_country(country_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM countries WHERE id = ?", (country_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_country_price(country_id: int, price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE countries SET price_inr = ? WHERE id = ?", (price, country_id))
        await db.commit()


async def toggle_country(country_id: int, active: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE countries SET is_active = ? WHERE id = ?", (1 if active else 0, country_id))
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# ACCOUNT OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def add_account(phone: str, session_str: str, country_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT OR REPLACE INTO accounts (phone_number, session_str, country_id) VALUES (?, ?, ?)",
            (phone, session_str, country_id)
        )
        await db.commit()
        return cursor.lastrowid


async def get_available_accounts(country_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM accounts WHERE country_id = ? AND is_available = 1",
            (country_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_account(account_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_account_availability(account_id: int, available: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE accounts SET is_available = ? WHERE id = ?",
            (1 if available else 0, account_id)
        )
        await db.commit()


async def delete_account(account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        await db.commit()


async def get_account_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        total = (await (await db.execute("SELECT COUNT(*) FROM accounts")).fetchone())[0]
        available = (await (await db.execute("SELECT COUNT(*) FROM accounts WHERE is_available=1")).fetchone())[0]
        return {"total": total, "available": available, "rented": total - available}


async def update_account_session(account_id: int, new_session: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET session_str = ? WHERE id = ?", (new_session, account_id))
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# RENTAL OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def create_rental(user_id: int, account_id: int, expires_at: str, payment_id: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO rentals (user_id, account_id, payment_id, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, account_id, payment_id, expires_at)
        )
        await db.execute(
            "UPDATE accounts SET is_available=0, total_rented=total_rented+1 WHERE id=?",
            (account_id,)
        )
        await db.execute(
            "UPDATE users SET total_spent = total_spent + (SELECT price_inr FROM countries c JOIN accounts a ON a.country_id=c.id WHERE a.id=?) WHERE user_id=?",
            (account_id, user_id)
        )
        await db.commit()
        return cursor.lastrowid


async def get_active_rental_for_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM rentals WHERE user_id=? AND is_active=1 ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_expired_rentals() -> list[dict]:
    """Returns all active rentals that have passed their expiry time."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM rentals WHERE is_active=1 AND expires_at <= ?",
            (now,)
        )
        return [dict(r) for r in await cursor.fetchall()]


async def close_rental(rental_id: int, account_id: int):
    """Mark rental as closed and free the account."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE rentals SET is_active=0, auto_logout=1 WHERE id=?",
            (rental_id,)
        )
        await db.execute(
            "UPDATE accounts SET is_available=1 WHERE id=?",
            (account_id,)
        )
        await db.commit()


async def get_user_rental_history(user_id: int, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT r.*, a.phone_number, c.name as country_name, c.flag_emoji
               FROM rentals r
               JOIN accounts a ON r.account_id = a.id
               JOIN countries c ON a.country_id = c.id
               WHERE r.user_id = ?
               ORDER BY r.id DESC LIMIT ?""",
            (user_id, limit)
        )
        return [dict(r) for r in await cursor.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# PAYMENT OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def create_payment(user_id: int, order_id: str, amount: float, purpose: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO payments (user_id, razorpay_order, amount_inr, purpose) VALUES (?, ?, ?, ?)",
            (user_id, order_id, amount, purpose)
        )
        await db.commit()
        return cursor.lastrowid


async def confirm_payment(order_id: str, payment_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "UPDATE payments SET status='paid', razorpay_payment=? WHERE razorpay_order=?",
            (payment_id, order_id)
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM payments WHERE razorpay_order=?", (order_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_payment_by_order(order_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM payments WHERE razorpay_order=?", (order_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_pending_payments() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM payments WHERE status='pending'")
        return [dict(r) for r in await cursor.fetchall()]


async def get_total_revenue() -> float:
    async with aiosqlite.connect(DB_PATH) as db:
        result = await (await db.execute("SELECT SUM(amount_inr) FROM payments WHERE status='paid'")).fetchone()
        return result[0] or 0.0
