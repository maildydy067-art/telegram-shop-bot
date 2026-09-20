import asyncio
import sys
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from keep_alive import keep_alive

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from config import BOT_TOKEN
from database.database import init_db
from sheets_manager import auto_sync_sheets, sheets
from handlers import admin, user

async def main():
    keep_alive()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    logging.info("🔄 Initializing Database...")
    await init_db()
    
    logging.info("🔄 Syncing Google Sheets for the first time...")
    await asyncio.to_thread(sheets.sync_accounts)
    
    logging.info("🤖 Starting Bot...")
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    dp.include_router(admin.router)
    dp.include_router(user.router)
    
    asyncio.create_task(auto_sync_sheets())
    
    try:
        logging.info("✅ Bot successfully started!")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logging.info("Bot session closed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")