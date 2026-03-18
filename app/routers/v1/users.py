import logging
from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserOut, UserUpdate
from app.utils.telegram_auth import validate_telegram_init_data

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_current_user(
    authorization: str = Header(..., alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency: Authorization headerdan initData ni oladi,
    tekshiradi va joriy foydalanuvchini qaytaradi.
    Header format: 'tma_<url_encoded_init_data>'
    """
    if not authorization.startswith("tma_"):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    init_data = authorization[4:]  # 'tma_' ni kesib tashlash
    try:
        tg_user = validate_telegram_init_data(init_data)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Telegram auth data")

    result = await db.execute(select(User).where(User.telegram_id == tg_user["id"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found, please /start first")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is blocked")
    return user


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    """Joriy foydalanuvchi profilini olish."""
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Profil va sozlamalarni yangilash."""
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)
    await db.flush()
    logger.info("Profil yangilandi: user_id=%s fields=%s", current_user.id, list(update_data.keys()))
    return current_user
