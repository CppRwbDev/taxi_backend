import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserOut, OnboardingRequest
from app.utils.telegram_auth import validate_telegram_init_data

router = APIRouter()
logger = logging.getLogger(__name__)


class ValidateRequest(BaseModel):
    init_data: str


class AuthResponse(BaseModel):
    user: UserOut
    is_new: bool


@router.post("/validate", response_model=AuthResponse)
async def validate_and_login(payload: ValidateRequest, db: AsyncSession = Depends(get_db)):
    """
    Task 2.3 — Telegram WebApp initData ni tekshiradi.
    Foydalanuvchi yangi bo'lsa DB ga yozadi, mavjud bo'lsa qaytaradi.
    """
    try:
        tg_user = validate_telegram_init_data(payload.init_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    telegram_id = tg_user["id"]

    # DBdan qidirish
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    is_new = False

    if not user:
        is_new = True
        user = User(
            telegram_id=telegram_id,
            full_name=tg_user.get("first_name", "") + " " + tg_user.get("last_name", ""),
            username=tg_user.get("username"),
            photo_url=tg_user.get("photo_url"),
            role="passenger",  # Default rol, onboarding da o'zgartiriladi
            balance=10000.0, # Test uchun bonus
        )
        db.add(user)
    else:
        # Update user details on login
        user.full_name = tg_user.get("first_name", "") + " " + tg_user.get("last_name", "")
        user.username = tg_user.get("username")
        if tg_user.get("photo_url"):
            user.photo_url = tg_user.get("photo_url")

    await db.flush()
    await db.refresh(user)

    return {"user": user, "is_new": is_new}


@router.post("/onboarding", response_model=UserOut)
async def complete_onboarding(
    payload: OnboardingRequest,
    init_data: str,
    db: AsyncSession = Depends(get_db),
):
    """Onboardingni yakunlash — til, fon, rolni saqlash."""
    try:
        tg_user = validate_telegram_init_data(init_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await db.execute(select(User).where(User.telegram_id == tg_user["id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.language = payload.language
    user.theme = payload.theme
    user.role = payload.role
    user.is_onboarded = True
    await db.flush()
    logger.info("Onboarding yakunlandi: user_id=%s role=%s", user.id, user.role)
    return user
