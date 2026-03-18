from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy import select
from app.database import get_session_factory
from app.models.user import User
from app.config import settings

router = Router()

@router.callback_query(F.data.startswith("take_order:"))
async def handle_take_order(callback: types.CallbackQuery):
    """
    Task 5.1 — Guruhdagi 'Olish' tugmasini bosganda haydovchini tekshirish
    va unga shaxsiy xabarda WebApp ssilkasini yuborish.
    """
    order_id = callback.data.split(":")[1]
    telegram_id = callback.from_user.id
    
    session_maker = get_session_factory()
    async with session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        
    try:
        bot_info = await callback.bot.get_me()
        bot_username = bot_info.username
        
        if not user or user.role not in ("driver", "investor"):
            # Not registered or not a driver
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Botga o'tish", url=f"https://t.me/{bot_username}?start=register")]
            ])
            await callback.bot.send_message(
                chat_id=telegram_id,
                text="Siz haydovchi sifatida ro'yxatdan o'tmagansiz yoki profilingizni to'ldirmagansiz.\nIltimos, quyidagi tugma orqali botga o'ting.",
                reply_markup=keyboard
            )
            await callback.answer("Sizga shaxsiy xabar yubordik. Iltimos tekshiring.", show_alert=True)
            return
            
        # Is driver
        web_app_url = settings.FRONTEND_URL.rstrip('/')
        # Frontendda /driver/order/:orderId degan router ochamiz
        app_url = f"{web_app_url}/driver/order/{order_id}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Taklifni yuborish", web_app=WebAppInfo(url=app_url))]
        ])
        
        await callback.bot.send_message(
            chat_id=telegram_id,
            text=f"Buyurtma #{order_id} ga o'z narxingizni taklif qiling:",
            reply_markup=keyboard
        )
        await callback.answer("Taklif yuborish uchun botdagi xabarni oching", show_alert=True)
        
    except Exception as e:
        # If bot is blocked by user or cannot send message
        await callback.answer("Avval botimizga kirib /start tugmasini bosing!", show_alert=True)
