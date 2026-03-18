from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from app.config import settings

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """/start komandasi uchun handler."""
    
    # WebApp URL (Frontend Render URL)
    web_app_url = settings.FRONTEND_URL
    
    # Keyboard yaratish
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
      [
        InlineKeyboardButton(
          text="🚖 Viloyatlararo Taksi", 
          web_app=WebAppInfo(url=web_app_url)
        )
      ],
      [
        InlineKeyboardButton(text="📢 Hamjamiyat", url="https://t.me/frontendhub_uzb")
      ]
    ])
    
    welcome_text = (
      f"Assalomu alaykum, {message.from_user.full_name}! 👋\n\n"
      "Viloyatlararo taksi xizmatiga xush kelibsiz.\n"
      "Pastdagi tugma orqali ilovani ochishingiz mumkin."
    )
    
    await message.answer(welcome_text, reply_markup=keyboard)
