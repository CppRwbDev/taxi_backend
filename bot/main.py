import asyncio
import logging
from aiogram import Bot, Dispatcher
from app.config import settings
from bot.handlers import start, orders

# Logging sozlash
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=settings.BOT_TOKEN) if settings.BOT_TOKEN else None
dp = Dispatcher()

if bot:
    dp.include_router(start.router)
    dp.include_router(orders.router)

async def start_bot():
    if not bot:
        logger.error("BOT_TOKEN topilmadi! .env faylni tekshiring.")
        return
    logger.info("Bot ishga tushmoqda...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot polling xatosi: {e}")

async def stop_bot():
    if bot:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(start_bot())
