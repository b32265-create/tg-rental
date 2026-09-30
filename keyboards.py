"""
keyboards.py — All inline and reply keyboard markups for Rent Bot
"""
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


# ─────────────────────────────────────────────────────────────────────────────
# MAIN MENU
# ─────────────────────────────────────────────────────────────────────────────

def main_menu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🌍 Rent Account"),
        KeyboardButton(text="📦 My Rentals")
    )
    builder.row(
        KeyboardButton(text="💰 Wallet"),
        KeyboardButton(text="👥 Referral")
    )
    builder.row(
        KeyboardButton(text="📋 Account Stock"),
        KeyboardButton(text="ℹ️ Help")
    )
    return builder.as_markup(resize_keyboard=True)


# ─────────────────────────────────────────────────────────────────────────────
# COUNTRY SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def countries_kb(countries: list[dict]) -> InlineKeyboardMarkup:
    """Generate inline keyboard with country buttons."""
    builder = InlineKeyboardBuilder()
    for c in countries:
        flag = c.get("flag_emoji", "🌐")
        name = c["name"]
        price = c["price_inr"]
        builder.button(
            text=f"{flag} {name} — ₹{price:.0f}",
            callback_data=f"country:{c['id']}"
        )
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# PAYMENT KEYBOARD
# ─────────────────────────────────────────────────────────────────────────────

def payment_kb(order_id: str, pay_url: str, amount: float) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"💳 Pay ₹{amount:.0f} via Razorpay",
        url=pay_url
    )
    builder.button(
        text="✅ I've Paid — Verify",
        callback_data=f"verify_pay:{order_id}"
    )
    builder.button(
        text="❌ Cancel",
        callback_data="cancel_pay"
    )
    builder.adjust(1)
    return builder.as_markup()


def wallet_pay_kb(amount: float, order_id: str) -> InlineKeyboardMarkup:
    """Confirm paying from wallet balance."""
    builder = InlineKeyboardBuilder()
    builder.button(text=f"✅ Pay ₹{amount:.0f} from Wallet", callback_data=f"wallet_pay:{order_id}")
    builder.button(text="💳 Pay via Razorpay Instead", callback_data=f"rzp_instead:{order_id}")
    builder.button(text="❌ Cancel", callback_data="cancel_pay")
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN PANEL
# ─────────────────────────────────────────────────────────────────────────────

def admin_panel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Add Account", callback_data="admin:add_account")
    builder.button(text="🗑️ Remove Account", callback_data="admin:remove_account")
    builder.button(text="🌍 Manage Countries", callback_data="admin:countries")
    builder.button(text="📢 Broadcast", callback_data="admin:broadcast")
    builder.button(text="👥 Users List", callback_data="admin:users")
    builder.button(text="📊 Stats", callback_data="admin:stats")
    builder.button(text="💰 Set User Balance", callback_data="admin:set_balance")
    builder.button(text="🚫 Ban User", callback_data="admin:ban_user")
    builder.adjust(2)
    return builder.as_markup()


def admin_countries_kb(countries: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for c in countries:
        status = "✅" if c["is_active"] else "❌"
        builder.button(
            text=f"{status} {c.get('flag_emoji','')} {c['name']} ₹{c['price_inr']:.0f}",
            callback_data=f"admin_country:{c['id']}"
        )
    builder.button(text="➕ Add Country", callback_data="admin:add_country")
    builder.button(text="🔙 Back", callback_data="admin:back")
    builder.adjust(1)
    return builder.as_markup()


def admin_country_actions_kb(country_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "❌ Deactivate" if is_active else "✅ Activate"
    builder.button(text="✏️ Change Price", callback_data=f"admin_cprice:{country_id}")
    builder.button(text=toggle_text, callback_data=f"admin_ctoggle:{country_id}:{int(is_active)}")
    builder.button(text="🔙 Back", callback_data="admin:countries")
    builder.adjust(1)
    return builder.as_markup()


def confirm_kb(action: str, extra: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm", callback_data=f"confirm:{action}:{extra}")
    builder.button(text="❌ Cancel", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# ACCOUNT DETAILS (after renting)
# ─────────────────────────────────────────────────────────────────────────────

def rental_active_kb(rental_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✉️ Get OTP", callback_data=f"rental_otp:{rental_id}")
    builder.button(text="⏱️ Time Remaining", callback_data=f"rental_time:{rental_id}")
    builder.button(text="🔄 Renew Rental", callback_data=f"rental_renew:{rental_id}")
    builder.adjust(1, 2)
    return builder.as_markup()


# ─────────────────────────────────────────────────────────────────────────────
# BACK BUTTON
# ─────────────────────────────────────────────────────────────────────────────

def back_kb(callback: str = "back") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Back", callback_data=callback)
    return builder.as_markup()
