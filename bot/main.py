import asyncio
import logging
from aiogram import Bot, Dispatcher
from app.config import settings
from bot.handlers import start, orders

# Logging sozlash
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    if not settings.BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi! .env faylni tekshiring.")
        return

    # Bot va Dispatcher obyektlari
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # Handlersni registratsiya qilish
    dp.include_router(start.router)
    dp.include_router(orders.router)

    logger.info("Bot ishga tushmoqda...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
