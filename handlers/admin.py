"""
handlers/admin.py — Admin panel handlers
Commands: /admin, /addaccount, /broadcast, /ban, /unban, /setbalance
All restricted to ADMIN_IDS only.
"""
import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS, RENT_DURATION
from database import (
    get_all_users, get_account_stats, get_countries, get_country,
    add_country, update_country_price, toggle_country,
    add_account, get_available_accounts, delete_account,
    get_user, set_balance, ban_user, unban_user, get_total_revenue,
    update_account_session
)
from session_manager import send_otp, verify_otp, generate_2fa_password
from keyboards import (
    admin_panel_kb, admin_countries_kb, admin_country_actions_kb,
    confirm_kb, back_kb
)

logger = logging.getLogger(__name__)
router = Router()


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN FILTER
# ─────────────────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ─────────────────────────────────────────────────────────────────────────────
# FSM STATES
# ─────────────────────────────────────────────────────────────────────────────

class AddAccountState(StatesGroup):
    waiting_phone = State()
    waiting_otp = State()
    waiting_2fa = State()
    waiting_country = State()


class AddCountryState(StatesGroup):
    waiting_name = State()
    waiting_flag = State()
    waiting_price = State()


class BroadcastState(StatesGroup):
    waiting_message = State()


class SetBalanceState(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()


class BanState(StatesGroup):
    waiting_user_id = State()


class EditPriceState(StatesGroup):
    waiting_price = State()
    country_id = None


# ─────────────────────────────────────────────────────────────────────────────
# /admin COMMAND
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.clear()
    stats = await get_account_stats()
    revenue = await get_total_revenue()

    await message.answer(
        f"👑 <b>Admin Panel</b>\n\n"
        f"📊 Accounts: {stats['total']} total | {stats['available']} available | {stats['rented']} rented\n"
        f"💰 Total Revenue: <b>₹{revenue:.2f}</b>\n\n"
        f"Choose action:",
        reply_markup=admin_panel_kb(),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN STATS
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:stats")
async def admin_stats_cb(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return

    from database import get_account_stats, get_total_revenue, get_all_users
    stats = await get_account_stats()
    revenue = await get_total_revenue()
    users = await get_all_users()

    await cb.message.edit_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total Users: <b>{len(users)}</b>\n"
        f"📱 Total Accounts: <b>{stats['total']}</b>\n"
        f"✅ Available: <b>{stats['available']}</b>\n"
        f"🔴 Currently Rented: <b>{stats['rented']}</b>\n"
        f"💰 Total Revenue: <b>₹{revenue:.2f}</b>",
        parse_mode="HTML",
        reply_markup=back_kb("admin:back")
    )
    await cb.answer()


# ─────────────────────────────────────────────────────────────────────────────
# ADD ACCOUNT FLOW
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:add_account")
async def add_account_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return

    await cb.message.edit_text(
        "📱 <b>Account Add Karo</b>\n\n"
        "Phone number bhejo (+91XXXXXXXXXX format mein):",
        parse_mode="HTML"
    )
    await state.set_state(AddAccountState.waiting_phone)
    await cb.answer()


@router.message(AddAccountState.waiting_phone)
async def add_account_phone(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    phone = message.text.strip()
    if not phone.startswith("+"):
        await message.answer("❌ Phone number + se start karo. Example: <code>+919876543210</code>", parse_mode="HTML")
        return

    await message.answer(f"📤 OTP bhej raha hoon <code>{phone}</code> pe... ⏳", parse_mode="HTML")

    try:
        await send_otp(phone)
        await state.update_data(phone=phone)
        await state.set_state(AddAccountState.waiting_otp)
        await message.answer(
            "✅ OTP bhej diya! Ab OTP enter karo:\n"
            "(Agar 2FA enabled hai, format: <code>OTP 2FApassword</code>)",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Error: {e}")
        await state.clear()


@router.message(AddAccountState.waiting_otp)
async def add_account_otp(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    text = message.text.strip()
    parts = text.split(" ", 1)
    otp = parts[0]
    two_fa = parts[1] if len(parts) > 1 else None

    data = await state.get_data()
    phone = data["phone"]

    await message.answer("⏳ Verify kar raha hoon...")

    try:
        from pyrogram.errors import SessionPasswordNeeded
        session_str = await verify_otp(phone, otp, two_fa)
        await state.update_data(session_str=session_str)
        await state.set_state(AddAccountState.waiting_country)

        countries = await get_countries()
        if not countries:
            await message.answer("⚠️ Pehle country add karo! /admin → Manage Countries")
            await state.clear()
            return

        text = "✅ Login successful!\n\n🌍 <b>Country choose karo (number bhejo):</b>\n\n"
        for i, c in enumerate(countries, 1):
            text += f"{i}. {c.get('flag_emoji','')} {c['name']} (₹{c['price_inr']})\n"

        await message.answer(text, parse_mode="HTML")
        await state.update_data(countries=countries)

    except SessionPasswordNeeded:
        await message.answer(
            "🔐 2FA password required!\n"
            "Format: <code>OTP 2FApassword</code>\n"
            "Dobara bhejo:",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Error: {e}")
        await state.clear()


@router.message(AddAccountState.waiting_country)
async def add_account_country(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    countries = data.get("countries", [])

    try:
        idx = int(message.text.strip()) - 1
        if idx < 0 or idx >= len(countries):
            raise ValueError
        country = countries[idx]
    except ValueError:
        await message.answer("❌ Sahi number bhejo!")
        return

    phone = data["phone"]
    session_str = data["session_str"]

    await add_account(phone, session_str, country["id"])
    await message.answer(
        f"✅ <b>Account Added!</b>\n\n"
        f"📱 Phone: <code>{phone}</code>\n"
        f"🌍 Country: {country.get('flag_emoji','')} {country['name']}\n\n"
        f"Account is now available for renting! 🎉",
        parse_mode="HTML"
    )
    await state.clear()


# ─────────────────────────────────────────────────────────────────────────────
# REMOVE ACCOUNT
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:remove_account")
async def remove_account_start(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return

    from database import get_available_accounts
    countries = await get_countries()
    text = "🗑️ <b>Account remove karo</b>\n\nAccount ID bhejo:\n\n"

    for c in countries:
        accounts = await get_available_accounts(c["id"])
        if accounts:
            text += f"\n{c.get('flag_emoji','')} <b>{c['name']}</b>:\n"
            for a in accounts:
                text += f"  ID: <code>{a['id']}</code> | {a['phone_number']}\n"

    await cb.message.edit_text(text + "\n\nAccount ID bhejo:", parse_mode="HTML")
    await cb.answer()


# ─────────────────────────────────────────────────────────────────────────────
# COUNTRIES MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:countries")
async def admin_countries(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return

    countries = await get_countries(active_only=False)
    await cb.message.edit_text(
        "🌍 <b>Countries Management</b>",
        reply_markup=admin_countries_kb(countries),
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("admin_country:"))
async def admin_country_detail(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return

    country_id = int(cb.data.split(":")[1])
    country = await get_country(country_id)
    if not country:
        await cb.answer("Country nahi mili!", show_alert=True)
        return

    accounts = await get_available_accounts(country_id)
    await cb.message.edit_text(
        f"{country.get('flag_emoji','')} <b>{country['name']}</b>\n\n"
        f"💰 Price: ₹{country['price_inr']}\n"
        f"📦 Available: {len(accounts)}\n"
        f"Status: {'✅ Active' if country['is_active'] else '❌ Inactive'}",
        reply_markup=admin_country_actions_kb(country_id, bool(country["is_active"])),
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("admin_cprice:"))
async def admin_change_price(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return

    country_id = int(cb.data.split(":")[1])
    await state.update_data(edit_country_id=country_id)
    await state.set_state(EditPriceState.waiting_price)
    await cb.message.edit_text(
        "✏️ <b>Nayi price enter karo (₹ mein):</b>",
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(EditPriceState.waiting_price)
async def admin_set_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    try:
        price = float(message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Valid price enter karo!")
        return

    data = await state.get_data()
    country_id = data["edit_country_id"]
    await update_country_price(country_id, price)
    country = await get_country(country_id)
    await message.answer(
        f"✅ <b>{country['name']} ki price update ho gayi!</b>\n"
        f"💰 New Price: <b>₹{price:.0f}</b>",
        parse_mode="HTML"
    )
    await state.clear()


@router.callback_query(F.data.startswith("admin_ctoggle:"))
async def admin_toggle_country(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return

    parts = cb.data.split(":")
    country_id = int(parts[1])
    current = int(parts[2])
    new_state = not bool(current)
    await toggle_country(country_id, new_state)
    country = await get_country(country_id)
    await cb.answer(f"{'✅ Activated' if new_state else '❌ Deactivated'}: {country['name']}", show_alert=True)
    # Refresh
    countries = await get_countries(active_only=False)
    await cb.message.edit_reply_markup(reply_markup=admin_countries_kb(countries))


@router.callback_query(F.data == "admin:add_country")
async def admin_add_country_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return

    await state.set_state(AddCountryState.waiting_name)
    await cb.message.edit_text(
        "🌍 <b>Nayi Country Add Karo</b>\n\n"
        "Step 1: Country ka naam bhejo (e.g. <code>India</code>):",
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(AddCountryState.waiting_name)
async def add_country_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(c_name=message.text.strip())
    await state.set_state(AddCountryState.waiting_flag)
    await message.answer("Step 2: Flag emoji bhejo (e.g. 🇮🇳):")


@router.message(AddCountryState.waiting_flag)
async def add_country_flag(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(c_flag=message.text.strip())
    await state.set_state(AddCountryState.waiting_price)
    await message.answer("Step 3: Price enter karo (₹ mein, e.g. <code>50</code>):", parse_mode="HTML")


@router.message(AddCountryState.waiting_price)
async def add_country_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    try:
        price = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Valid price enter karo!")
        return

    data = await state.get_data()
    country_id = await add_country(data["c_name"], data["c_flag"], price)
    await message.answer(
        f"✅ <b>Country Added!</b>\n\n"
        f"{data['c_flag']} <b>{data['c_name']}</b>\n"
        f"💰 Price: ₹{price:.0f}",
        parse_mode="HTML"
    )
    await state.clear()


# ─────────────────────────────────────────────────────────────────────────────
# BROADCAST
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:broadcast")
async def broadcast_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return

    await state.set_state(BroadcastState.waiting_message)
    await cb.message.edit_text(
        "📢 <b>Broadcast Message</b>\n\n"
        "Woh message bhejo jo sab users ko send karna hai:",
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(BroadcastState.waiting_message)
async def broadcast_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    users = await get_all_users()
    success = 0
    failed = 0

    status_msg = await message.answer(f"📤 Broadcast shuru... 0/{len(users)}")

    for i, user in enumerate(users):
        try:
            await message.bot.copy_message(
                chat_id=user["user_id"],
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            success += 1
        except Exception:
            failed += 1

        if (i + 1) % 20 == 0:
            try:
                await status_msg.edit_text(f"📤 Broadcast: {i+1}/{len(users)}")
            except Exception:
                pass

    await status_msg.edit_text(
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}",
        parse_mode="HTML"
    )
    await state.clear()


# ─────────────────────────────────────────────────────────────────────────────
# SET USER BALANCE
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:set_balance")
async def set_balance_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(SetBalanceState.waiting_user_id)
    await cb.message.edit_text("💰 User ID bhejo jiska balance set karna hai:")
    await cb.answer()


@router.message(SetBalanceState.waiting_user_id)
async def set_balance_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.strip())
        user = await get_user(uid)
        if not user:
            await message.answer("❌ User nahi mila!")
            return
        await state.update_data(target_user=uid)
        await state.set_state(SetBalanceState.waiting_amount)
        await message.answer(
            f"👤 User: <code>{uid}</code>\n"
            f"Current Balance: ₹{user['balance']:.2f}\n\n"
            f"Nayi balance amount bhejo:",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Valid User ID bhejo!")


@router.message(SetBalanceState.waiting_amount)
async def set_balance_amount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Valid amount bhejo!")
        return

    data = await state.get_data()
    uid = data["target_user"]
    await set_balance(uid, amount)
    await message.answer(
        f"✅ <b>Balance set!</b>\n"
        f"User <code>{uid}</code> ka balance: <b>₹{amount:.2f}</b>",
        parse_mode="HTML"
    )
    await state.clear()


# ─────────────────────────────────────────────────────────────────────────────
# BAN / UNBAN
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:ban_user")
async def ban_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(BanState.waiting_user_id)
    await cb.message.edit_text("🚫 Ban karne ke liye User ID bhejo\n(Unban ke liye /unban <id> use karo):")
    await cb.answer()


@router.message(BanState.waiting_user_id)
async def ban_user_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.strip())
        await ban_user(uid)
        await message.answer(f"🚫 User <code>{uid}</code> banned!", parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Valid User ID bhejo!")
    await state.clear()


@router.message(Command("unban"))
async def unban_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /unban <user_id>")
        return
    try:
        uid = int(args[1])
        await unban_user(uid)
        await message.answer(f"✅ User <code>{uid}</code> unbanned!", parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Valid User ID bhejo!")


# ─────────────────────────────────────────────────────────────────────────────
# BACK NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:back")
async def admin_back(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await state.clear()
    stats = await get_account_stats()
    revenue = await get_total_revenue()
    await cb.message.edit_text(
        f"👑 <b>Admin Panel</b>\n\n"
        f"📊 Accounts: {stats['total']} total | {stats['available']} available\n"
        f"💰 Revenue: <b>₹{revenue:.2f}</b>\n\n"
        f"Choose action:",
        reply_markup=admin_panel_kb(),
        parse_mode="HTML"
    )
    await cb.answer()
