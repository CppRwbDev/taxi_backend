import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from decimal import Decimal

from app.database import get_db
from app.models.user import User
from app.models.order import Order
from app.models.transaction import Transaction
from app.routers.v1.users import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

async def check_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin huquqi zarur")
    return user

@router.get("/stats")
async def get_stats(
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db)
):
    """Admin panel uchun asosiy statistika."""
    users_count = await db.scalar(select(func.count(User.id)))
    orders_count = await db.scalar(select(func.count(Order.id)))
    
    # Umumiy tushum (komissiya tranzaksiyalari yig'indisi)
    revenue_res = await db.execute(
        select(func.sum(Transaction.amount))
        .where(Transaction.type.in_(["offer_commission", "order_commission"]))
    )
    total_revenue = revenue_res.scalar() or 0
    # Komissiya manfiy saqlangani uchun musbatga o'tkazamiz
    total_revenue = abs(float(total_revenue))

    return {
        "users_count": users_count,
        "orders_count": orders_count,
        "total_revenue": total_revenue
    }

@router.get("/users")
async def list_users(
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db)
):
    """Barcha foydalanuvchilar ro'yxati."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return users

@router.patch("/users/{user_id}/role")
async def change_user_role(
    user_id: int,
    role: str,
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db)
):
    """Foydalanuvchi rolini o'zgartirish."""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    
    if role not in ("passenger", "driver", "admin", "investor"):
         raise HTTPException(status_code=400, detail="Noto'g'ri rol")
         
    user.role = role
    await db.flush()
    return {"message": "Rol o'zgartirildi", "user_id": user_id, "new_role": role}

@router.patch("/users/{user_id}/status")
async def change_user_status(
    user_id: int,
    is_active: bool,
    admin: User = Depends(check_admin),
    db: AsyncSession = Depends(get_db)
):
    """Foydalanuvchini bloklash yoki faollashtirish."""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    
    user.is_active = is_active
    await db.flush()
    return {"message": "Status o'zgartirildi", "is_active": is_active}
