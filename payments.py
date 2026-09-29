"""
payments.py — Razorpay integration for Rent Bot
Uses Razorpay Payment Links API for proper shareable payment links
"""
import hmac
import hashlib
import logging
import requests

from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

logger = logging.getLogger(__name__)
RAZORPAY_API = "https://api.razorpay.com/v1"


def _auth():
    return (RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)


# ─────────────────────────────────────────────────────────────────────────────
# CREATE PAYMENT LINK (proper shareable link)
# ─────────────────────────────────────────────────────────────────────────────

def create_payment_link(amount_inr: float, description: str, user_id: int, purpose: str = "rent") -> dict:
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
    try:
        resp = requests.post(
            f"{RAZORPAY_API}/payment_links",
            json=payload,
            auth=_auth(),
            timeout=10
        )
        resp.raise_for_status()
        link = resp.json()
        logger.info(f"Payment link created: {link['id']} — ₹{amount_inr} — {link.get('short_url','')}")
        return link
    except requests.exceptions.RequestException as e:
        logger.error(f"Payment link creation failed: {e} | Response: {e.response.text if hasattr(e, 'response') and e.response else ''}")
        raise Exception(f"❌ Payment gateway error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CREATE ORDER (for signature verification after payment)
# ─────────────────────────────────────────────────────────────────────────────

def create_order(amount_inr: float, receipt: str, notes: dict = None) -> dict:
    """Create a Razorpay Order (used for backend verification)."""
    payload = {
        "amount": int(amount_inr * 100),
        "currency": "INR",
        "receipt": receipt,
        "notes": notes or {}
    }
    try:
        resp = requests.post(f"{RAZORPAY_API}/orders", json=payload, auth=_auth(), timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Order creation failed: {e}")
        raise Exception(f"Payment gateway error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# FETCH PAYMENT LINK STATUS
# ─────────────────────────────────────────────────────────────────────────────

def fetch_payment_link(link_id: str) -> dict:
    """Fetch payment link details to check if it's been paid."""
    try:
        resp = requests.get(f"{RAZORPAY_API}/payment_links/{link_id}", auth=_auth(), timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Fetch payment link error: {e}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# FETCH PAYMENT
# ─────────────────────────────────────────────────────────────────────────────

def fetch_payment(payment_id: str) -> dict:
    """Fetch individual payment details."""
    try:
        resp = requests.get(f"{RAZORPAY_API}/payments/{payment_id}", auth=_auth(), timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Fetch payment error: {e}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# CHECK IF PAYMENT LINK IS PAID
# ─────────────────────────────────────────────────────────────────────────────

def is_payment_link_paid(link_id: str) -> tuple[bool, str]:
    """
    Returns (is_paid, payment_id).
    Checks Razorpay if the payment link has been paid.
    """
    try:
        link = fetch_payment_link(link_id)
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

def issue_refund(payment_id: str, amount_inr: float = None) -> dict:
    """Issue full or partial refund."""
    try:
        payload = {}
        if amount_inr:
            payload["amount"] = int(amount_inr * 100)
        resp = requests.post(
            f"{RAZORPAY_API}/payments/{payment_id}/refund",
            json=payload,
            auth=_auth(),
            timeout=10
        )
        resp.raise_for_status()
        refund = resp.json()
        logger.info(f"Refund issued: {refund.get('id')} for payment {payment_id}")
        return refund
    except requests.exceptions.RequestException as e:
        logger.error(f"Refund error: {e}")
        raise
