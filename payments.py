"""
payments.py — Razorpay integration for Rent Bot
Uses Razorpay Payment Links API for proper shareable payment links
Refactored to use aiohttp for async non-blocking operations.
"""
import logging
import aiohttp
from aiohttp import BasicAuth

from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

logger = logging.getLogger(__name__)
RAZORPAY_API = "https://api.razorpay.com/v1"

def _auth():
    return BasicAuth(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)


# ─────────────────────────────────────────────────────────────────────────────
# CREATE PAYMENT LINK (proper shareable link)
# ─────────────────────────────────────────────────────────────────────────────

async def create_payment_link(amount_inr: float, description: str, user_id: int, purpose: str = "rent") -> dict:
    """
    Creates a Razorpay Payment Link — returns proper shareable URL.
    Returns dict with 'id', 'short_url', 'amount'.
    """
    amount_paise = int(amount_inr * 100)
    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "description": description,
        "notify": {
            "sms": False,
            "email": False
        },
        "reminder_enable": False,
        "notes": {
            "user_id": str(user_id),
            "purpose": purpose
        },
        "callback_url": "",
        "callback_method": "get"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{RAZORPAY_API}/payment_links",
            json=payload,
            auth=_auth(),
            timeout=10
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                logger.error(f"Payment link creation failed | Response: {text}")
                raise Exception(f"❌ Payment gateway error")
                
            link = await resp.json()
            logger.info(f"Payment link created: {link.get('id')} — ₹{amount_inr} — {link.get('short_url','')}")
            return link


# ─────────────────────────────────────────────────────────────────────────────
# CREATE ORDER (for signature verification after payment)
# ─────────────────────────────────────────────────────────────────────────────

async def create_order(amount_inr: float, receipt: str, notes: dict = None) -> dict:
    """Create a Razorpay Order (used for backend verification)."""
    payload = {
        "amount": int(amount_inr * 100),
        "currency": "INR",
        "receipt": receipt,
        "notes": notes or {}
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{RAZORPAY_API}/orders",
            json=payload,
            auth=_auth(),
            timeout=10
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                logger.error(f"Order creation failed | Response: {text}")
                raise Exception("Payment gateway error")
                
            return await resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# FETCH PAYMENT LINK STATUS
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_payment_link(link_id: str) -> dict:
    """Fetch payment link details to check if it's been paid."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{RAZORPAY_API}/payment_links/{link_id}",
            auth=_auth(),
            timeout=10
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                logger.error(f"Fetch payment link error | Response: {text}")
                raise Exception("Fetch payment link error")
                
            return await resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# FETCH PAYMENT
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_payment(payment_id: str) -> dict:
    """Fetch individual payment details."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{RAZORPAY_API}/payments/{payment_id}",
            auth=_auth(),
            timeout=10
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                logger.error(f"Fetch payment error | Response: {text}")
                raise Exception("Fetch payment error")
                
            return await resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# CHECK IF PAYMENT LINK IS PAID
# ─────────────────────────────────────────────────────────────────────────────

async def is_payment_link_paid(link_id: str) -> tuple[bool, str]:
    """
    Returns (is_paid, payment_id).
    Checks Razorpay if the payment link has been paid.
    """
    try:
        link = await fetch_payment_link(link_id)
        status = link.get("status", "")
        if status == "paid":
            # Get payment ID from payments on this link
            payments = link.get("payments", [])
            payment_id = ""
            if payments:
                # Find the captured payment
                for p in payments:
                    if p.get("payment_id"):
                        payment_id = p["payment_id"]
                        break
            return True, payment_id
        return False, ""
    except Exception as e:
        logger.error(f"is_payment_link_paid error: {e}")
        return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# ISSUE REFUND
# ─────────────────────────────────────────────────────────────────────────────

async def issue_refund(payment_id: str, amount_inr: float = None) -> dict:
    """Issue full or partial refund."""
    payload = {}
    if amount_inr:
        payload["amount"] = int(amount_inr * 100)
        
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{RAZORPAY_API}/payments/{payment_id}/refund",
            json=payload,
            auth=_auth(),
            timeout=10
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                logger.error(f"Refund error | Response: {text}")
                raise Exception("Refund error")
                
            refund = await resp.json()
            logger.info(f"Refund issued: {refund.get('id')} for payment {payment_id}")
            return refund
