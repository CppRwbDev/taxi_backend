from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from app.config import settings
from app.database import get_session_factory
from app.models.user import User

router = Router()


def _webapp_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🚖 Viloyatlararo Taksi",
                web_app=WebAppInfo(url=url),
            )
        ],
        [
            InlineKeyboardButton(text="📢 Hamjamiyat", url="https://t.me/frontendhub_uzb"),
        ],
    ])


async def _get_user(telegram_id: int):
    session_maker = get_session_factory()
    async with session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()


async def _send_welcome(message: types.Message, payload: str | None = None):
    user = await _get_user(message.from_user.id)
    web_app_url = settings.FRONTEND_URL

    if payload == "register":
        # Haydovchi guruhidagi "Botga o'tish" tugmasi (?start=register)
        text = (
            "📝 <b>Ro'yxatdan o'tish</b>\n\n"
            "Pastdagi tugma orqali ilovani ochib, ro'yxatdan o'ting:\n"
            "rol → <b>Haydovchi</b>, ism, telefon va hududlarni kiriting.\n\n"
            "Ro'yxatdan o'tgandan so'ng taklif yuborish mumkin bo'ladi."
        )
        keyboard = _webapp_keyboard(web_app_url)
    elif user is None:
        text = (
            f"Assalomu alaykum, {message.from_user.full_name}! 👋\n\n"
            "Viloyatlararo taksi xizmatiga xush kelibsiz.\n"
            "Ilovani birinchi marta oching — ro'yxatdan o'tish 30 soniya vaqt oladi."
        )
        keyboard = _webapp_keyboard(web_app_url)
    elif not user.is_active:
        text = (
            "⛔ Hisobingiz bloklangan.\n"
            "Ma'lumot uchun administratorga murojaat qiling."
        )
        keyboard = None
    elif not user.is_onboarded:
        text = (
            f"Assalomu alaykum, {message.from_user.full_name}! 👋\n\n"
            "Hisobingiz tayyor, lekin sozlamalarni (til, rol) tanlash qolmoqda.\n"
            "Pastdagi tugma orqali davom eting."
        )
        keyboard = _webapp_keyboard(web_app_url)
    else:
        role_labels = {
            "driver": "Haydovchi",
            "investor": "Investor",
            "admin": "Administrator",
        }
        role_label = role_labels.get(user.role, "Yo'lovchi")
        text = (
            f"Assalomu alaykum, {message.from_user.full_name}! 👋\n\n"
            f"Sizning rollaringiz: <b>{role_label}</b>\n"
            "Pastdagi tugma orqali ilovani ochishingiz mumkin."
        )
        keyboard = _webapp_keyboard(web_app_url)

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep(message: types.Message):
    """/start <payload> — masalan ?start=register (guruhdagi ro'yxatdan o'tish tugmasi)."""
    payload = (message.text or "").split(maxsplit=1)
    await _send_welcome(message, payload[1].strip() if len(payload) > 1 else None)


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """/start komandasi uchun handler."""
    await _send_welcome(message)
