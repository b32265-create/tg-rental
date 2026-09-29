"""
database.py — Postgres database layer for Rent Bot
Tables: users, accounts, rentals, payments, countries
"""
import asyncpg
import asyncio
from datetime import datetime
from config import DATABASE_URL

pool = None

# ─────────────────────────────────────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────────────────────────────────────

async def init_db():
    """Create all tables if they don't exist."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    
    async with pool.acquire() as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       BIGINT PRIMARY KEY,
            username      TEXT,
            full_name     TEXT,
            balance       REAL    DEFAULT 0,
            referral_code TEXT    UNIQUE,
            referred_by   BIGINT,
            total_spent   REAL    DEFAULT 0,
            created_at    TEXT    DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
            is_banned     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS countries (
            id          SERIAL PRIMARY KEY,
            name        TEXT    UNIQUE NOT NULL,
            flag_emoji  TEXT,
            price_inr   REAL    NOT NULL DEFAULT 50.0,
            is_active   INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id           SERIAL PRIMARY KEY,
            phone_number TEXT    UNIQUE NOT NULL,
            session_str  TEXT    NOT NULL,
            country_id   INTEGER REFERENCES countries(id),
            is_available INTEGER DEFAULT 1,
            added_at     TEXT    DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
            total_rented INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS rentals (
            id           SERIAL PRIMARY KEY,
            user_id      BIGINT NOT NULL,
            account_id   INTEGER NOT NULL,
            payment_id   TEXT,
            started_at   TEXT    DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
            expires_at   TEXT    NOT NULL,
            is_active    INTEGER DEFAULT 1,
            auto_logout  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS payments (
            id              SERIAL PRIMARY KEY,
            user_id         BIGINT NOT NULL,
            razorpay_order  TEXT    UNIQUE,
            razorpay_payment TEXT,
            amount_inr      REAL    NOT NULL,
            status          TEXT    DEFAULT 'pending',
            purpose         TEXT,
            created_at      TEXT    DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
        );
        """)


# ─────────────────────────────────────────────────────────────────────────────
# USER OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def get_or_create_user(user_id: int, username: str = None, full_name: str = None) -> dict:
    import random, string
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if row:
            return dict(row)
        
        ref_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        await db.execute(
            "INSERT INTO users (user_id, username, full_name, referral_code) VALUES ($1, $2, $3, $4)",
            user_id, username, full_name, ref_code
        )
        row = await db.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row)


async def get_user(user_id: int) -> dict | None:
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None


async def update_balance(user_id: int, delta: float):
    async with pool.acquire() as db:
        await db.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", delta, user_id)


async def set_balance(user_id: int, amount: float):
    async with pool.acquire() as db:
        await db.execute("UPDATE users SET balance = $1 WHERE user_id = $2", amount, user_id)


async def get_all_users() -> list[dict]:
    async with pool.acquire() as db:
        rows = await db.fetch("SELECT user_id FROM users WHERE is_banned = 0")
        return [dict(r) for r in rows]


async def ban_user(user_id: int):
    async with pool.acquire() as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = $1", user_id)


async def unban_user(user_id: int):
    async with pool.acquire() as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = $1", user_id)


async def get_user_by_referral(code: str) -> dict | None:
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT * FROM users WHERE referral_code = $1", code)
        return dict(row) if row else None


async def set_referred_by(user_id: int, referrer_id: int):
    async with pool.acquire() as db:
        await db.execute(
            "UPDATE users SET referred_by = $1 WHERE user_id = $2 AND referred_by IS NULL",
            referrer_id, user_id
        )


# ─────────────────────────────────────────────────────────────────────────────
# COUNTRY OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def add_country(name: str, flag: str, price: float) -> int:
    async with pool.acquire() as db:
        row = await db.fetchrow(
            """INSERT INTO countries (name, flag_emoji, price_inr) VALUES ($1, $2, $3)
               ON CONFLICT (name) DO UPDATE SET flag_emoji=$2, price_inr=$3 RETURNING id""",
            name, flag, price
        )
        return row['id']


async def get_countries(active_only: bool = True) -> list[dict]:
    async with pool.acquire() as db:
        if active_only:
            rows = await db.fetch("SELECT * FROM countries WHERE is_active = 1 ORDER BY name")
        else:
            rows = await db.fetch("SELECT * FROM countries ORDER BY name")
        return [dict(r) for r in rows]


async def get_country(country_id: int) -> dict | None:
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT * FROM countries WHERE id = $1", country_id)
        return dict(row) if row else None


async def update_country_price(country_id: int, price: float):
    async with pool.acquire() as db:
        await db.execute("UPDATE countries SET price_inr = $1 WHERE id = $2", price, country_id)


async def toggle_country(country_id: int, active: bool):
    async with pool.acquire() as db:
        await db.execute("UPDATE countries SET is_active = $1 WHERE id = $2", 1 if active else 0, country_id)


# ─────────────────────────────────────────────────────────────────────────────
# ACCOUNT OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def add_account(phone: str, session_str: str, country_id: int) -> int:
    async with pool.acquire() as db:
        row = await db.fetchrow(
            """INSERT INTO accounts (phone_number, session_str, country_id) VALUES ($1, $2, $3)
               ON CONFLICT (phone_number) DO UPDATE SET session_str=$2, country_id=$3 RETURNING id""",
            phone, session_str, country_id
        )
        return row['id']


async def get_available_accounts(country_id: int) -> list[dict]:
    async with pool.acquire() as db:
        rows = await db.fetch(
            "SELECT * FROM accounts WHERE country_id = $1 AND is_available = 1",
            country_id
        )
        return [dict(r) for r in rows]


async def get_account(account_id: int) -> dict | None:
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT * FROM accounts WHERE id = $1", account_id)
        return dict(row) if row else None


async def set_account_availability(account_id: int, available: bool):
    async with pool.acquire() as db:
        await db.execute(
            "UPDATE accounts SET is_available = $1 WHERE id = $2",
            1 if available else 0, account_id
        )


async def delete_account(account_id: int):
    async with pool.acquire() as db:
        await db.execute("DELETE FROM accounts WHERE id = $1", account_id)


async def get_account_stats() -> dict:
    async with pool.acquire() as db:
        total = await db.fetchval("SELECT COUNT(*) FROM accounts")
        available = await db.fetchval("SELECT COUNT(*) FROM accounts WHERE is_available=1")
        return {"total": total, "available": available, "rented": total - available}


async def update_account_session(account_id: int, new_session: str):
    async with pool.acquire() as db:
        await db.execute("UPDATE accounts SET session_str = $1 WHERE id = $2", new_session, account_id)


# ─────────────────────────────────────────────────────────────────────────────
# RENTAL OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def create_rental(user_id: int, account_id: int, expires_at: str, payment_id: str = None) -> int:
    async with pool.acquire() as db:
        async with db.transaction():
            row = await db.fetchrow(
                "INSERT INTO rentals (user_id, account_id, payment_id, expires_at) VALUES ($1, $2, $3, $4) RETURNING id",
                user_id, account_id, payment_id, expires_at
            )
            await db.execute(
                "UPDATE accounts SET is_available=0, total_rented=total_rented+1 WHERE id=$1",
                account_id
            )
            await db.execute(
                "UPDATE users SET total_spent = total_spent + (SELECT price_inr FROM countries c JOIN accounts a ON a.country_id=c.id WHERE a.id=$1) WHERE user_id=$2",
                account_id, user_id
            )
            return row['id']


async def get_active_rental_for_user(user_id: int) -> dict | None:
    async with pool.acquire() as db:
        row = await db.fetchrow(
            "SELECT * FROM rentals WHERE user_id=$1 AND is_active=1 ORDER BY id DESC LIMIT 1",
            user_id
        )
        return dict(row) if row else None


async def get_expired_rentals() -> list[dict]:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with pool.acquire() as db:
        rows = await db.fetch(
            "SELECT * FROM rentals WHERE is_active=1 AND expires_at <= $1",
            now
        )
        return [dict(r) for r in rows]


async def close_rental(rental_id: int, account_id: int):
    async with pool.acquire() as db:
        async with db.transaction():
            await db.execute(
                "UPDATE rentals SET is_active=0, auto_logout=1 WHERE id=$1",
                rental_id
            )
            await db.execute(
                "UPDATE accounts SET is_available=1 WHERE id=$1",
                account_id
            )


async def get_user_rental_history(user_id: int, limit: int = 10) -> list[dict]:
    async with pool.acquire() as db:
        rows = await db.fetch(
            """SELECT r.*, a.phone_number, c.name as country_name, c.flag_emoji
               FROM rentals r
               JOIN accounts a ON r.account_id = a.id
               JOIN countries c ON a.country_id = c.id
               WHERE r.user_id = $1
               ORDER BY r.id DESC LIMIT $2""",
            user_id, limit
        )
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# PAYMENT OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def create_payment(user_id: int, order_id: str, amount: float, purpose: str) -> int:
    async with pool.acquire() as db:
        row = await db.fetchrow(
            "INSERT INTO payments (user_id, razorpay_order, amount_inr, purpose) VALUES ($1, $2, $3, $4) RETURNING id",
            user_id, order_id, amount, purpose
        )
        return row['id']


async def confirm_payment(order_id: str, payment_id: str) -> dict | None:
    async with pool.acquire() as db:
        await db.execute(
            "UPDATE payments SET status='paid', razorpay_payment=$1 WHERE razorpay_order=$2",
            payment_id, order_id
        )
        row = await db.fetchrow("SELECT * FROM payments WHERE razorpay_order=$1", order_id)
        return dict(row) if row else None


async def get_payment_by_order(order_id: str) -> dict | None:
    async with pool.acquire() as db:
        row = await db.fetchrow("SELECT * FROM payments WHERE razorpay_order=$1", order_id)
        return dict(row) if row else None


async def get_pending_payments() -> list[dict]:
    async with pool.acquire() as db:
        rows = await db.fetch("SELECT * FROM payments WHERE status='pending'")
        return [dict(r) for r in rows]


async def get_total_revenue() -> float:
    async with pool.acquire() as db:
        val = await db.fetchval("SELECT SUM(amount_inr) FROM payments WHERE status='paid'")
        return float(val) if val else 0.0
