"""
session_manager.py — Pyrogram session manager
Handles: login via OTP, 2FA password change, session logout
"""
import random
import string
import asyncio
import logging

from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid,
    FloodWait, PhoneCodeExpired, PasswordHashInvalid
)

from config import API_ID, API_HASH

logger = logging.getLogger(__name__)

# In-memory OTP state (phone → client waiting for code)
_login_sessions: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# GENERATE RANDOM 2FA PASSWORD
# ─────────────────────────────────────────────────────────────────────────────

def generate_2fa_password(length: int = 16) -> str:
    """Generate a strong random 2FA password."""
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choices(chars, k=length))


# ─────────────────────────────────────────────────────────────────────────────
# SEND OTP (Step 1 of admin login)
# ─────────────────────────────────────────────────────────────────────────────

async def send_otp(phone_number: str) -> str:
    """
    Initiates login for a phone number.
    Returns phone_code_hash needed for verification.
    """
    client = Client(
        name=f"temp_{phone_number.replace('+', '')}",
        api_id=API_ID,
        api_hash=API_HASH,
        in_memory=True
    )
    await client.connect()
    try:
        sent = await client.send_code(phone_number)
        _login_sessions[phone_number] = {
            "client": client,
            "phone_code_hash": sent.phone_code_hash
        }
        return sent.phone_code_hash
    except FloodWait as e:
        await client.disconnect()
        raise Exception(f"⏳ FloodWait: {e.value} seconds intezaar karo")
    except Exception as e:
        await client.disconnect()
        raise


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY OTP + OPTIONAL 2FA (Step 2)
# ─────────────────────────────────────────────────────────────────────────────

async def verify_otp(phone_number: str, code: str, two_fa_password: str = None) -> str:
    """
    Completes login. Returns Pyrogram session string.
    Raises SessionPasswordNeeded if 2FA is enabled and password not provided.
    """
    session_data = _login_sessions.get(phone_number)
    if not session_data:
        raise Exception("Session expired. Please send OTP again.")

    client: Client = session_data["client"]
    phone_code_hash: str = session_data["phone_code_hash"]

    try:
        await client.sign_in(
            phone_number=phone_number,
            phone_code_hash=phone_code_hash,
            phone_code=code
        )
    except SessionPasswordNeeded:
        if not two_fa_password:
            # Signal caller that 2FA password is needed
            raise SessionPasswordNeeded()
        await client.check_password(two_fa_password)
    except PhoneCodeInvalid:
        raise Exception("❌ OTP galat hai. Dobara try karo.")
    except PhoneCodeExpired:
        raise Exception("❌ OTP expire ho gaya. Naaya OTP mangao.")

    session_str = await client.export_session_string()
    await client.disconnect()
    del _login_sessions[phone_number]
    return session_str


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 2FA PASSWORD (called after renting)
# ─────────────────────────────────────────────────────────────────────────────

async def change_2fa_password(session_str: str, new_password: str) -> bool:
    """
    Connects to account using session string and changes 2FA password.
    Returns True on success.
    """
    client = Client(
        name="change_2fa",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_str,
        in_memory=True
    )
    try:
        await client.start()
        await client.change_cloud_password(
            current_password=None,   # Will try with no password first
            new_password=new_password,
            hint="Auto-changed by RentBot"
        )
        logger.info("2FA password changed successfully")
        return True
    except PasswordHashInvalid:
        logger.warning("2FA change failed — wrong current password")
        return False
    except Exception as e:
        logger.error(f"2FA change error: {e}")
        return False
    finally:
        try:
            await client.stop()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# REMOVE 2FA (reset when session is returned)
# ─────────────────────────────────────────────────────────────────────────────

async def remove_2fa(session_str: str, current_password: str) -> bool:
    """Remove 2FA protection from account when rental expires."""
    client = Client(
        name="remove_2fa",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_str,
        in_memory=True
    )
    try:
        await client.start()
        await client.remove_cloud_password(current_password)
        logger.info("2FA removed successfully")
        return True
    except Exception as e:
        logger.error(f"2FA removal error: {e}")
        return False
    finally:
        try:
            await client.stop()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# TERMINATE ALL OTHER SESSIONS (logout user's devices)
# ─────────────────────────────────────────────────────────────────────────────

async def terminate_all_sessions(session_str: str) -> bool:
    """Terminates all other active sessions for an account (security on return)."""
    client = Client(
        name="terminate_sessions",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_str,
        in_memory=True
    )
    try:
        await client.start()
        await client.invoke(
            __import__("pyrogram.raw.functions.auth", fromlist=["ResetAuthorizations"]).ResetAuthorizations()
        )
        logger.info("All other sessions terminated")
        return True
    except Exception as e:
        logger.error(f"Session termination error: {e}")
        return False
    finally:
        try:
            await client.stop()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# GET LATEST OTP (for users logging into rented accounts)
# ─────────────────────────────────────────────────────────────────────────────

async def get_latest_otp(session_str: str) -> str:
    """Connects to the session and fetches the latest Telegram login code from 777000."""
    import re
    from datetime import datetime, timedelta
    
    client = Client(
        name="fetch_otp",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_str,
        in_memory=True
    )
    
    try:
        await client.start()
        # Fetch the last 5 messages from Telegram notifications (777000)
        otp = None
        async for msg in client.get_chat_history(777000, limit=5):
            # Login codes are usually 5 digits and valid for a short time
            if msg.date < datetime.utcnow() - timedelta(minutes=15):
                continue
            
            # Match 5 digit code like: "Login code: 12345"
            match = re.search(r'\b(\d{5})\b', msg.text)
            if match:
                otp = match.group(1)
                break
                
        return otp
    except Exception as e:
        logger.error(f"Fetch OTP error: {e}")
        return None
    finally:
        try:
            await client.stop()
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────────────────
# GET SESSION STRING (for admin adding account)
# ─────────────────────────────────────────────────────────────────────────────

async def get_session_string(phone_number: str, otp: str, two_fa: str = None) -> str:
    """Full flow: returns session string after OTP + optional 2FA."""
    await send_otp(phone_number)
    return await verify_otp(phone_number, otp, two_fa)
