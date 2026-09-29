"""
handlers/user.py — All user-facing bot handlers
Commands: /start, /rent, /wallet, /referral, /myrentals, /help, /stock
Callbacks: country selection, payment verification, rental timer
"""
import logging
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import pytz

from config import ADMIN_IDS, RENT_DURATION, REFERRAL_BONUS, TIMEZONE
from database import (
    get_or_create_user, get_user, update_balance, set_referred_by,
    get_user_by_referral, get_countries, get_available_accounts,
    get_country, create_rental, get_active_rental_for_user,
    get_user_rental_history, create_payment, confirm_payment,
    get_payment_by_order
)
from payments import create_payment_link, is_payment_link_paid
from session_manager import change_2fa_password, generate_2fa_password
from keyboards import (
    main_menu_kb, countries_kb, payment_kb, wallet_pay_kb,
    rental_active_kb, back_kb
)

logger = logging.getLogger(__name__)
router = Router()
tz = pytz.timezone(TIMEZONE)


# ─────────────────────────────────────────────────────────────────────────────
# FSM STATES
# ─────────────────────────────────────────────────────────────────────────────

class RentState(StatesGroup):
    waiting_for_country = State()
    waiting_for_payment = State()
    confirming_payment = State()


class WalletState(StatesGroup):
    adding_amount = State()
    verifying_wallet_payment = State()


# ─────────────────────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name
    )

    # Handle referral link: /start ref_XXXXXXXX
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        ref_code = args[1][4:]
        referrer = await get_user_by_referral(ref_code)
        if referrer and referrer["user_id"] != message.from_user.id:
            if not user.get("referred_by"):
                await set_referred_by(message.from_user.id, referrer["user_id"])
                await update_balance(referrer["user_id"], REFERRAL_BONUS)
                try:
                    await message.bot.send_message(
                        referrer["user_id"],
                        f"🎉 <b>New Referral!</b>\n"
                        f"👤 {message.from_user.full_name} aapke referral se join kiya!\n"
                        f"💰 +₹{REFERRAL_BONUS} aapke wallet mein add ho gaye!",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

    await message.answer(
        f"👋 <b>Aaye ho {message.from_user.first_name}!</b> ✨\n\n"
        f"🤖 <b>RentBot</b> mein aapka swagat hai!\n\n"
        f"📱 Yahan aap <b>Telegram accounts</b> rent kar sakte ho.\n"
        f"⏱️ Har account <b>23 ghante 55 minute</b> ke liye milega.\n"
        f"🔐 Auto 2FA + Auto Logout protection ke saath.\n\n"
        f"👇 Neeche se option choose karo:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────────────────────
# RENT ACCOUNT
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.text == "🌍 Rent Account")
async def rent_start(message: Message, state: FSMContext):
    await state.clear()

    # Check if already has active rental
    active = await get_active_rental_for_user(message.from_user.id)
    if active:
        expires = datetime.strptime(active["expires_at"], "%Y-%m-%d %H:%M:%S")
        expires_local = pytz.utc.localize(expires).astimezone(tz)
        remaining = expires - datetime.utcnow()
        hours, rem = divmod(int(remaining.total_seconds()), 3600)
        minutes = rem // 60
        await message.answer(
            f"⚠️ <b>Aapke paas pehle se ek active rental hai!</b>\n\n"
            f"⏳ Time remaining: <b>{hours}h {minutes}m</b>\n"
            f"📅 Expires: <b>{expires_local.strftime('%d %b %Y, %I:%M %p')}</b>\n\n"
            f"Use /myrentals to see details.",
            parse_mode="HTML"
        )
        return

    countries = await get_countries(active_only=True)
    if not countries:
        await message.answer("😔 Abhi koi country available nahi hai. Baad mein try karo.")
        return

    # Count available accounts per country
    country_list = []
    for c in countries:
        accounts = await get_available_accounts(c["id"])
        if accounts:
            c["_stock"] = len(accounts)
            country_list.append(c)

    if not country_list:
        await message.answer(
            "😔 <b>Abhi koi account available nahi hai.</b>\n"
            "Thodi der baad try karo! 🙏",
            parse_mode="HTML"
        )
        return

    await state.set_state(RentState.waiting_for_country)
    await message.answer(
        "🌍 <b>Country choose karo:</b>\n\n"
        "💡 Price per 23h 55min rental hai.\n"
        "📦 Stock bracket mein dikh raha hai.",
        reply_markup=countries_kb(country_list),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("country:"), RentState.waiting_for_country)
async def country_selected(cb: CallbackQuery, state: FSMContext):
    country_id = int(cb.data.split(":")[1])
    country = await get_country(country_id)
    if not country:
        await cb.answer("Country nahi mili!", show_alert=True)
        return

    accounts = await get_available_accounts(country_id)
    if not accounts:
        await cb.answer("❌ Is country mein koi account nahi hai!", show_alert=True)
        return

    user = await get_user(cb.from_user.id)
    price = country["price_inr"]
    balance = user["balance"]

    await state.update_data(country_id=country_id, price=price)
    
    if balance >= price:
        await cb.message.edit_text(
            f"{country.get('flag_emoji','🌍')} <b>{country['name']}</b>\n\n"
            f"💰 Price: <b>₹{price:.0f}</b> for 23h 55min\n"
            f"📦 Stock: <b>{len(accounts)} accounts</b> available\n"
            f"👛 Your balance: <b>₹{balance:.2f}</b>\n\n"
            f"✅ You have enough balance!\n",
            parse_mode="HTML",
            reply_markup=wallet_pay_kb(price, f"rent_{cb.from_user.id}_{country_id}")
        )
    else:
        # Create payment link
        try:
            link = create_payment_link(
                amount_inr=price,
                description=f"Rent {country['name']}",
                user_id=cb.from_user.id,
                purpose="rent"
            )
            link_id = link["id"]
            short_url = link["short_url"]
            
            # Save pending payment in DB
            await create_payment(cb.from_user.id, link_id, price, "rent")
            
            await cb.message.edit_text(
                f"{country.get('flag_emoji','🌍')} <b>{country['name']}</b>\n\n"
                f"💰 Price: <b>₹{price:.0f}</b> for 23h 55min\n"
                f"📦 Stock: <b>{len(accounts)} accounts</b> available\n"
                f"👛 Your balance: <b>₹{balance:.2f}</b>\n\n"
                f"💳 Balance kam hai, Razorpay se pay karo.\n",
                parse_mode="HTML",
                reply_markup=payment_kb(link_id, short_url, price)
            )
        except Exception as e:
            logger.error(f"Failed to create payment link: {e}")
            await cb.answer("❌ Payment link generate nahi hua. Try again.", show_alert=True)
            return

    await state.set_state(RentState.waiting_for_payment)
    await cb.answer()


# ─────────────────────────────────────────────────────────────────────────────
# WALLET PAY CALLBACK
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wallet_pay:"))
async def wallet_pay(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    country_id = data.get("country_id")
    price = data.get("price")

    user = await get_user(cb.from_user.id)
    if not user or user["balance"] < price:
        await cb.answer("❌ Balance nahi hai!", show_alert=True)
        return

    await _complete_rental(cb.message, cb.from_user.id, country_id, price, paid_from_wallet=True)
    await state.clear()
    await cb.answer()


# ─────────────────────────────────────────────────────────────────────────────
# RAZORPAY VERIFY CALLBACK
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("verify_pay:"))
async def verify_payment_cb(cb: CallbackQuery, state: FSMContext):
    link_id = cb.data.split(":")[1]
    payment = await get_payment_by_order(link_id)
    if not payment:
        await cb.answer("❌ Payment record nahi mila!", show_alert=True)
        return

    if payment["status"] == "paid":
        await cb.answer("✅ Payment already verified!", show_alert=True)
        return

    await cb.answer("⏳ Checking payment...", show_alert=False)
    
    is_paid, payment_id = is_payment_link_paid(link_id)
    if is_paid:
        await confirm_payment(link_id, payment_id)
        
        # Give balance
        await update_balance(cb.from_user.id, payment["amount_inr"])
        
        if payment["purpose"] == "rent":
            # If it was for rent, now complete the rental
            data = await state.get_data()
            country_id = data.get("country_id")
            if country_id:
                await _complete_rental(cb.message, cb.from_user.id, country_id, payment["amount_inr"], paid_from_wallet=False)
            else:
                await cb.message.answer(f"✅ Payment of ₹{payment['amount_inr']} added to wallet.")
        else:
            await cb.message.answer(f"✅ Wallet topped up by ₹{payment['amount_inr']}.")
            
        await state.clear()
    else:
        await cb.message.answer("❌ Payment abhi tak receive nahi hua. Agar pay kar diya hai toh thodi der baad Verify dabao.")
        await cb.answer()


# ─────────────────────────────────────────────────────────────────────────────
# COMPLETE RENTAL (shared logic)
# ─────────────────────────────────────────────────────────────────────────────

async def _complete_rental(
    message: Message,
    user_id: int,
    country_id: int,
    price: float,
    paid_from_wallet: bool = False,
    payment_id: str = None
):
    accounts = await get_available_accounts(country_id)
    if not accounts:
        await message.answer("😔 Account abhi available nahi hua. Thodi der mein try karo.")
        return

    # Pick first available account
    account = accounts[0]
    account_id = account["id"]

    # Deduct from wallet if applicable
    if paid_from_wallet:
        await update_balance(user_id, -price)

    # Set expiry
    now_utc = datetime.utcnow()
    expires_utc = now_utc + timedelta(seconds=RENT_DURATION)
    expires_str = expires_utc.strftime("%Y-%m-%d %H:%M:%S")

    # Create rental in DB
    rental_id = await create_rental(user_id, account_id, expires_str, payment_id)

    # Change 2FA password automatically
    new_2fa = generate_2fa_password()

    # Send account details FIRST
    country = await get_country(country_id)
    expires_local = pytz.utc.localize(expires_utc).astimezone(pytz.timezone(TIMEZONE))

    await message.answer(
        f"✅ <b>Account Successfully Rented!</b> 🎉\n\n"
        f"📱 <b>Phone:</b> <code>{account['phone_number']}</code>\n"
        f"🔐 <b>New 2FA Password:</b> <code>{new_2fa}</code>\n"
        f"⚠️ <b>Important:</b> Login ke baad yeh password note karo!\n\n"
        f"⏰ <b>Expires:</b> {expires_local.strftime('%d %b %Y, %I:%M %p')} IST\n"
        f"⏱️ <b>Duration:</b> 23 hours 55 minutes\n\n"
        f"🚫 <b>Account editing allowed:</b> Profile pic, bio\n"
        f"🔒 <b>2FA auto-change ho chuka hai — security active hai!</b>\n\n"
        f"💡 <i>Time expire hone par auto-logout ho jayega.</i>",
        reply_markup=rental_active_kb(rental_id),
        parse_mode="HTML"
    )

    # Change 2FA in background
    try:
        await change_2fa_password(account["session_str"], new_2fa)
    except Exception as e:
        logger.error(f"2FA change failed for account {account_id}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# MY RENTALS
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.text == "📦 My Rentals")
@router.message(Command("myrentals"))
async def my_rentals(message: Message):
    active = await get_active_rental_for_user(message.from_user.id)
    history = await get_user_rental_history(message.from_user.id)

    if not history:
        await message.answer(
            "📦 <b>Koi rental history nahi hai.</b>\n\n"
            "🌍 Rent Account se start karo!",
            parse_mode="HTML"
        )
        return

    text = "📦 <b>Aapki Rental History:</b>\n\n"

    for r in history:
        status = "🟢 ACTIVE" if r.get("is_active") else "🔴 Ended"
        text += (
            f"{r.get('flag_emoji','🌍')} <b>{r.get('country_name','?')}</b> {status}\n"
            f"📱 <code>{r['phone_number']}</code>\n"
            f"⏰ Started: {r['started_at'][:16]}\n"
            f"─────────────────\n"
        )

    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# RENTAL TIME REMAINING
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rental_time:"))
async def rental_time_cb(cb: CallbackQuery):
    active = await get_active_rental_for_user(cb.from_user.id)
    if not active:
        await cb.answer("❌ Koi active rental nahi hai!", show_alert=True)
        return

    expires = datetime.strptime(active["expires_at"], "%Y-%m-%d %H:%M:%S")
    remaining = expires - datetime.utcnow()

    if remaining.total_seconds() <= 0:
        await cb.answer("⏰ Rental expire ho gaya!", show_alert=True)
        return

    hours, rem = divmod(int(remaining.total_seconds()), 3600)
    minutes, seconds = divmod(rem, 60)

    await cb.answer(
        f"⏱️ Time Remaining: {hours}h {minutes}m {seconds}s",
        show_alert=True
    )


# ─────────────────────────────────────────────────────────────────────────────
# WALLET
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.text == "💰 Wallet")
@router.message(Command("wallet"))
async def wallet_cmd(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if not user:
        user = await get_or_create_user(message.from_user.id)

    await message.answer(
        f"💰 <b>Aapka Wallet</b>\n\n"
        f"💵 Balance: <b>₹{user['balance']:.2f}</b>\n"
        f"🛒 Total Spent: <b>₹{user['total_spent']:.2f}</b>\n\n"
        f"📥 Balance add karne ke liye amount bhejo (e.g. <code>100</code>):",
        parse_mode="HTML"
    )
    await state.set_state(WalletState.adding_amount)


@router.message(WalletState.adding_amount)
async def wallet_add_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        if amount < 1:
            await message.answer("❌ Minimum ₹1 add kar sakte ho.")
            return
        if amount > 10000:
            await message.answer("❌ Maximum ₹10,000 ek baar mein.")
            return
    except ValueError:
        await message.answer("❌ Sirf number likhna hai (e.g. <code>100</code>)", parse_mode="HTML")
        return

    # Create Razorpay payment link
    try:
        link = create_payment_link(
            amount_inr=amount,
            description="Wallet Topup",
            user_id=message.from_user.id,
            purpose="wallet_topup"
        )
        link_id = link["id"]
        pay_url = link["short_url"]
        await create_payment(message.from_user.id, link_id, amount, "wallet_topup")
    except Exception as e:
        await message.answer(f"❌ Payment gateway error: {e}")
        await state.clear()
        return
    await message.answer(
        f"💳 <b>Wallet Topup — ₹{amount:.0f}</b>\n\n"
        f"Neeche button se pay karo:",
        reply_markup=payment_kb(link_id, pay_url, amount),
        parse_mode="HTML"
    )
    await state.update_data(pending_order_id=link_id, wallet_amount=amount)
    await state.set_state(WalletState.verifying_wallet_payment)


@router.message(WalletState.verifying_wallet_payment)
async def wallet_verify_payment(message: Message, state: FSMContext):
    payment_id = message.text.strip()
    if not payment_id.startswith("pay_"):
        await message.answer("❌ Invalid Payment ID. Format: <code>pay_XXXXXXXX</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    order_id = data.get("pending_order_id")
    wallet_amount = data.get("wallet_amount", 0)

    payment = await confirm_payment(order_id, payment_id)
    if payment:
        await update_balance(message.from_user.id, wallet_amount)
        user = await get_user(message.from_user.id)
        await message.answer(
            f"✅ <b>₹{wallet_amount:.0f} wallet mein add ho gaye!</b>\n"
            f"💵 New Balance: <b>₹{user['balance']:.2f}</b>",
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Payment verify nahi hua. Admin se contact karo.")

    await state.clear()


# ─────────────────────────────────────────────────────────────────────────────
# REFERRAL
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.text == "👥 Referral")
@router.message(Command("referral"))
async def referral_cmd(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return

    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user['referral_code']}"

    await message.answer(
        f"👥 <b>Referral Program</b> 💎\n\n"
        f"🔗 Aapka link:\n<code>{ref_link}</code>\n\n"
        f"💰 Har referral pe: <b>₹{REFERRAL_BONUS}</b> wallet mein\n\n"
        f"📤 Apne dosto ko share karo aur kamao!",
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ACCOUNT STOCK
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.text == "📋 Account Stock")
@router.message(Command("stock"))
async def stock_cmd(message: Message):
    from database import get_account_stats, get_countries, get_available_accounts
    stats = await get_account_stats()
    countries = await get_countries(active_only=True)

    text = (
        f"📦 <b>Account Stock</b>\n\n"
        f"📊 Total Accounts: <b>{stats['total']}</b>\n"
        f"✅ Available: <b>{stats['available']}</b>\n"
        f"🔴 Rented: <b>{stats['rented']}</b>\n\n"
        f"🌍 <b>By Country:</b>\n"
    )
    for c in countries:
        avail = await get_available_accounts(c["id"])
        text += f"{c.get('flag_emoji','🌐')} {c['name']}: <b>{len(avail)}</b> available\n"

    await message.answer(text, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# HELP
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.text == "ℹ️ Help")
@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "📖 <b>RentBot Help</b>\n\n"
        "🌍 <b>Rent Account</b> — Country choose karo, pay karo, account lo\n"
        "📦 <b>My Rentals</b> — Aapki rental history\n"
        "💰 <b>Wallet</b> — Balance add/check karo\n"
        "👥 <b>Referral</b> — Dosto ko invite karo, paise kamao\n"
        "📋 <b>Stock</b> — Kitne accounts available hain\n\n"
        "❓ <b>Problem?</b> Admin se contact karo.",
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────────────────────
# CANCEL
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel_pay")
@router.callback_query(F.data == "cancel")
async def cancel_cb(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ <b>Cancelled.</b>", parse_mode="HTML")
    await cb.answer()
