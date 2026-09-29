"""
config.py — Central configuration loader for Rent Bot
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Bot ──────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# ── Telegram API ──────────────────────────────────────────────
API_ID: int = int(os.getenv("API_ID", "0"))
API_HASH: str = os.getenv("API_HASH", "")

# ── Admins ────────────────────────────────────────────────────
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
]

# ── Razorpay ──────────────────────────────────────────────────
RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "")

# ── Rent Settings ─────────────────────────────────────────────
RENT_DURATION: int = int(os.getenv("RENT_DURATION", "86100"))   # 23h 55min

# ── Referral ─────────────────────────────────────────────────
REFERRAL_BONUS: float = float(os.getenv("REFERRAL_BONUS", "20"))

# ── Database ─────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# ── Timezone ─────────────────────────────────────────────────
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
