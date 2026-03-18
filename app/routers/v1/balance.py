import logging
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.models.transaction import Transaction
from app.routers.v1.users import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


class TopUpRequest(BaseModel):
    amount: Decimal
    payment_provider: str = "manual"
    payment_id: str = ""


@router.get("")
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Haydovchi balansini va tranzaksiyalar tarixini ko'rish."""
    txn_result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(desc(Transaction.created_at))
        .limit(20)
    )
    transactions = txn_result.scalars().all()

    return {
        "balance": float(current_user.balance),
        "currency": "UZS",
        "transactions": [
            {
                "id": t.id,
                "type": t.type,
                "amount": float(t.amount),
                "description": t.description,
                "created_at": t.created_at.isoformat(),
            }
            for t in transactions
        ],
    }


@router.post("/topup")
async def top_up_balance(
    payload: TopUpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Task 6.1 — Balans to'ldirish.
    MVP: admin manual top-up. Kelajakda Payme/Click webhook.
    """
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Summa 0 dan katta bo'lishi kerak")

    current_user.balance += payload.amount
    txn = Transaction(
        user_id=current_user.id,
        amount=payload.amount,
        type="top_up",
        description="Balans to'ldirildi",
        payment_provider=payload.payment_provider,
        payment_id=payload.payment_id,
        status="success",
    )
    db.add(txn)
    await db.flush()
    logger.info("Balans to'ldirildi: user_id=%s amount=%s", current_user.id, payload.amount)

    return {
        "message": "Balans to'ldirildi",
        "amount_added": float(payload.amount),
        "new_balance": float(current_user.balance),
    }
