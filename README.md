# RentBot — Telegram Account Rental Bot

## 🚀 Setup Instructions

### Step 1 — Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2 — Configure `.env` file

Kholao `.env` file aur ye fill karo:

| Variable | Kahan se milega | Example |
|---|---|---|
| `BOT_TOKEN` | BotFather | `1234567890:AAF...` |
| `API_ID` | my.telegram.org | `12345678` |
| `API_HASH` | my.telegram.org | `abcdef1234...` |
| `ADMIN_IDS` | Apna Telegram User ID | `987654321` |
| `RAZORPAY_KEY_ID` | Razorpay Dashboard | `rzp_live_XXX` |
| `RAZORPAY_KEY_SECRET` | Razorpay Dashboard | `XXXXXXXXXXXXXXX` |

#### API_ID aur API_HASH kaise milega?
1. [my.telegram.org](https://my.telegram.org) pe jao
2. "API Development Tools" click karo
3. App create karo
4. `api_id` aur `api_hash` copy karo

#### Apna User ID kaise pata karo?
- [@userinfobot](https://t.me/userinfobot) pe `/start` bhejo
- Woh aapka ID bata dega

### Step 3 — Run Bot
```bash
python main.py
```

---

## 📁 File Structure

```
RENT BOT/
├── main.py              # Entry point
├── config.py            # Config loader
├── database.py          # SQLite database
├── payments.py          # Razorpay integration
├── session_manager.py   # Pyrogram session handling
├── scheduler.py         # Auto-logout background tasks
├── keyboards.py         # All keyboards/buttons
├── handlers/
│   ├── user.py          # User commands
│   └── admin.py         # Admin commands
├── .env                 # Your secrets (PRIVATE!)
├── requirements.txt     # Dependencies
└── rentbot.db           # Auto-created database
```

---

## 🤖 Bot Commands

### User Commands
| Command | Description |
|---|---|
| `/start` | Bot start karo |
| `/rent` | Account rent karo |
| `/myrentals` | Rental history dekho |
| `/wallet` | Balance add/check karo |
| `/referral` | Referral link lo |
| `/stock` | Available accounts dekho |
| `/help` | Help |

### Admin Commands
| Command | Description |
|---|---|
| `/admin` | Admin panel open karo |
| `/unban <id>` | User unban karo |

---

## 🔥 Features

- ✅ **23h 55min Auto Logout** — Timer expire hone par automatic logout
- ✅ **2FA Auto-Change** — Har session pe unique 2FA password set hota hai
- ✅ **Razorpay Payment** — Online payment gateway
- ✅ **Wallet System** — Users balance recharge kar sakte hain
- ✅ **Referral System** — ₹20 per referral (admin se change karo `.env` mein)
- ✅ **Country-wise Pricing** — Alag-alag countries ke liye alag price
- ✅ **Admin Panel** — Complete management interface
- ✅ **30-min Warning** — Rental expire hone se 30 min pehle user ko notification
- ✅ **Broadcast** — Sab users ko ek saath message
- ✅ **Ban/Unban** — Users ban kar sako
- ✅ **Account Stock** — Real-time availability

---

## ⚠️ Important Notes

1. **BOT TOKEN REGENERATE KARO** — Jo token aapne share kiya tha wo public ho gaya. BotFather mein jao aur `/revoke` karo.
2. **`.env` file kabhi share mat karna** — Isme saare secrets hain.
3. **my.telegram.org** pe jaake API credentials lo — warna accounts add nahi honge.
4. Bot ko **24/7 run karna hai** — VPS/server use karo ya services jaise Railway, Heroku.

---

## 🔐 Security

- 2FA password har rental ke baad automatically change hota hai
- Rental expire hone par `ResetAuthorizations()` call hoti hai — user ke saare sessions terminate
- Admin commands sirf `.env` mein listed admin IDs ke liye kaam karte hain

---

## 💡 Razorpay Setup

1. [dashboard.razorpay.com](https://dashboard.razorpay.com) pe login karo
2. Settings → API Keys → Generate Key
3. `Key ID` aur `Key Secret` `.env` mein dalo
4. Test mode mein pehle try karo!
