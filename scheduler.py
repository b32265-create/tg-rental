"""
scheduler.py — APScheduler background tasks for Rent Bot
Handles: auto-logout when rental expires, expiry warnings
"""
import logging
import asyncio
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import pytz

from config import TIMEZONE
from database import get_expired_rentals, close_rental, get_account, get_user
from session_manager import terminate_all_sessions

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))

# Will be set from main.py to allow sending messages
_bot = None
_warned_rentals: set[int] = set()   # Track 30-min warnings sent


def set_bot(bot):
    """Pass bot instance from main.py so scheduler can send messages."""
    global _bot
    _bot = bot


# ─────────────────────────────────────────────────────────────────────────────
# AUTO LOGOUT JOB (runs every 60 seconds)
# ─────────────────────────────────────────────────────────────────────────────

async def check_expired_rentals():
    """Check for expired rentals and terminate sessions."""
    try:
        expired = await get_expired_rentals()
        for rental in expired:
            rental_id = rental["id"]
            account_id = rental["account_id"]
            user_id = rental["user_id"]

            logger.info(f"Auto-logout: rental #{rental_id}, account #{account_id}, user {user_id}")

            # Get account session
            account = await get_account(account_id)
            if account and account.get("session_str"):
                # Terminate all sessions (kick the renter out)
                await terminate_all_sessions(account["session_str"])

            # Free the account in DB
            await close_rental(rental_id, account_id)

            # Notify user
            if _bot:
                try:
                    await _bot.send_message(
                        chat_id=user_id,
                        text=(
                            "⏰ <b>Aapka rental expire ho gaya!</b>\n\n"
                            "🔴 Account se automatically logout kar diya gaya hai.\n"
                            "💎 Dobara rent karne ke liye /rent command use karo.\n\n"
                            "🙏 Thank you for using <b>RentBot</b>!"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"Could not notify user {user_id}: {e}")

            if rental_id in _warned_rentals:
                _warned_rentals.discard(rental_id)

    except Exception as e:
        logger.error(f"check_expired_rentals error: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# 30-MINUTE WARNING JOB (runs every 5 minutes)
# ─────────────────────────────────────────────────────────────────────────────

async def send_expiry_warnings():
    """Send warning to users whose rental expires in ~30 minutes."""
    from database import pool

    try:
        now = datetime.utcnow()
        warning_threshold = now + timedelta(minutes=30)

        async with pool.acquire() as db:
            rows = await db.fetch(
                """SELECT r.*, a.phone_number FROM rentals r
                   JOIN accounts a ON r.account_id = a.id
                   WHERE r.is_active=1
                     AND r.expires_at > $1
                     AND r.expires_at <= $2""",
                now.strftime("%Y-%m-%d %H:%M:%S"),
                warning_threshold.strftime("%Y-%m-%d %H:%M:%S")
            )
            soon_expiring = [dict(r) for r in rows]

        for rental in soon_expiring:
            if rental["id"] not in _warned_rentals and _bot:
                try:
                    await _bot.send_message(
                        chat_id=rental["user_id"],
                        text=(
                            "⚠️ <b>30 minute baad logout!</b>\n\n"
                            f"📱 Account <code>{rental['phone_number']}</code> ka rental "
                            "30 minute mein expire hone wala hai.\n\n"
                            "💡 Renew karne ke liye /rent command use karo!"
                        ),
                        parse_mode="HTML"
                    )
                    _warned_rentals.add(rental["id"])
                except Exception as e:
                    logger.warning(f"Could not send warning to {rental['user_id']}: {e}")

    except Exception as e:
        logger.error(f"send_expiry_warnings error: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# PENDING PAYMENTS CHECK JOB (runs every 30 seconds)
# ─────────────────────────────────────────────────────────────────────────────

async def check_pending_payments():
    """Check for pending payments and verify them via Razorpay API."""
    from database import get_pending_payments, confirm_payment, update_balance
    from payments import is_payment_link_paid
    try:
        pending = await get_pending_payments()
        for payment in pending:
            link_id = payment["razorpay_order"]
            user_id = payment["user_id"]
            amount = payment["amount_inr"]
            
            try:
                is_paid, payment_id = is_payment_link_paid(link_id)
                if is_paid:
                    logger.info(f"Background verify: Payment {link_id} is paid. Updating wallet for user {user_id}.")
                    await confirm_payment(link_id, payment_id)
                    await update_balance(user_id, amount)
                    
                    if _bot:
                        try:
                            msg = (
                                f"✅ <b>Payment Verified Automatically!</b> 🎉\n\n"
                                f"₹{amount:.0f} aapke wallet mein add ho gaye hain.\n\n"
                            )
                            if payment["purpose"] == "rent":
                                msg += "💡 <b>Ab aap /rent use karke wallet balance se account le sakte ho!</b>"
                            
                            await _bot.send_message(
                                chat_id=user_id,
                                text=msg,
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.warning(f"Could not send payment success to user {user_id}: {e}")
            except Exception as inner_e:
                logger.error(f"Error checking payment {link_id}: {inner_e}")
                
    except Exception as e:
        logger.error(f"check_pending_payments error: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# START SCHEDULER
# ─────────────────────────────────────────────────────────────────────────────

def start_scheduler():
    """Register jobs and start the APScheduler."""
    scheduler.add_job(
        check_expired_rentals,
        trigger=IntervalTrigger(seconds=60),
        id="check_expired",
        replace_existing=True
    )
    scheduler.add_job(
        send_expiry_warnings,
        trigger=IntervalTrigger(minutes=5),
        id="expiry_warnings",
        replace_existing=True
    )
    scheduler.add_job(
        check_pending_payments,
        trigger=IntervalTrigger(seconds=30),
        id="check_payments",
        replace_existing=True
    )
    scheduler.start()
    logger.info("✅ Scheduler started (expiry check: 60s, warnings: 5min, payments: 30s)")
