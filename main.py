"""
main.py — Entry point for Rent Bot
Initializes bot, database, scheduler, and starts polling
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, ADMIN_IDS
from database import init_db
from scheduler import start_scheduler, set_bot
from handlers import user as user_handlers
from handlers import admin as admin_handlers

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("rentbot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP / SHUTDOWN
# ─────────────────────────────────────────────────────────────────────────────

async def on_startup(bot: Bot):
    logger.info("🚀 RentBot starting up...")

    # Initialize database
    await init_db()
    logger.info("✅ Database initialized")

    # Start background scheduler
    set_bot(bot)
    start_scheduler()
    logger.info("✅ Scheduler started")

    # Notify admins
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🟢 <b>RentBot is ONLINE!</b>\n\n"
                "✅ Database: Ready\n"
                "✅ Scheduler: Running\n"
                "✅ Payment Gateway: Ready\n\n"
                "Use /admin to open admin panel.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")


async def on_shutdown(bot: Bot):
    logger.info("🔴 RentBot shutting down...")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "🔴 <b>RentBot is OFFLINE!</b>", parse_mode="HTML")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register routers
    dp.include_router(admin_handlers.router)   # Admin first (priority)
    dp.include_router(user_handlers.router)

    # Lifecycle hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("✅ Bot configured. Starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
