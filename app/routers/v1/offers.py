import logging
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.offer import Offer
from app.models.order import Order
from app.models.user import User
from app.models.transaction import Transaction
from app.schemas.offer import OfferCreate, OfferOut
from app.routers.v1.users import get_current_user
from app.config import get_commission

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", status_code=201)
async def send_offer(
    payload: OfferCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Task 5.3 — Haydovchi taklif yuboradi.
    Balans tekshiruvi → komissiya olinadi → yo'lovchiga notification.
    """
    if current_user.role not in ("driver", "investor"):
        raise HTTPException(status_code=403, detail="Faqat haydovchilar taklif yubora oladi")

    # Buyurtmani tekshirish
    order_res = await db.execute(select(Order).where(Order.id == payload.order_id))
    order = order_res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if order.status not in ("searching", "has_offers"):
        raise HTTPException(status_code=400, detail="Bu buyurtma endi qabul qilinmaydi")

    # Duplicate check
    dup_res = await db.execute(
        select(Offer).where(
            Offer.order_id == payload.order_id,
            Offer.driver_id == current_user.id,
        )
    )
    if dup_res.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Siz bu buyurtmaga allaqachon taklif yuborgansiz")

    # Balans tekshiruvi
    commission = Decimal(get_commission(order.passenger_count))
    if current_user.balance < commission:
        raise HTTPException(
            status_code=402,
            detail="Balans yetarli emas. Iltimos, to'ldiring.",
            headers={"X-Required": str(commission), "X-Current": str(current_user.balance)},
        )

    # Komissiyani olib qo'yish
    current_user.balance -= commission
    db.add(Transaction(
        user_id=current_user.id,
        amount=-commission,
        type="offer_commission",
        description=f"Taklif komissiyasi (buyurtma #{order.id})",
    ))

    # Taklif yaratish
    offer = Offer(
        order_id=payload.order_id,
        driver_id=current_user.id,
        proposed_price=payload.proposed_price,
        proposed_time=payload.proposed_time,
        message=payload.message,
        commission_paid=commission,
    )
    db.add(offer)

    # Buyurtma statusini yangilash
    if order.status == "searching":
        order.status = "has_offers"

    await db.flush()
    logger.info("Yangi taklif: offer_id=%s driver=%s order=%s", offer.id, current_user.id, order.id)

    # Yo'lovchiga notification (Task 7.2)
    try:
        from app.services.notification_service import notify_passenger_new_offer
        await notify_passenger_new_offer(offer, order, current_user)
    except Exception as e:
        logger.warning("Passenger notification xatosi: %s", e)

    return {
        "id": offer.id,
        "order_id": offer.order_id,
        "proposed_price": float(offer.proposed_price),
        "proposed_time": offer.proposed_time,
        "commission_paid": float(commission),
        "status": offer.status,
        "driver_balance_after": float(current_user.balance),
    }


@router.patch("/{offer_id}/accept")
async def accept_offer(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Task 4.4 — Yo'lovchi taklifni qabul qiladi.
    Match bo'ladi: ikki tomonga kontaktlar ochiladi.
    """
    offer_res = await db.execute(
        select(Offer, Order, User)
        .join(Order, Offer.order_id == Order.id)
        .join(User, Offer.driver_id == User.id)
        .where(Offer.id == offer_id)
    )
    row = offer_res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Taklif topilmadi")

    offer, order, driver = row
    if order.passenger_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu buyurtma sizniki emas")
    if offer.status != "pending":
        raise HTTPException(status_code=400, detail="Bu taklif allaqachon o'zgartirilgan")

    # Match!
    offer.status = "accepted"
    order.status = "matched"
    order.accepted_offer_id = offer.id

    # Boshqa takliflarni reject qilish
    await db.execute(
        select(Offer)
        .where(Offer.order_id == order.id, Offer.id != offer.id, Offer.status == "pending")
    )
    other_offers_res = await db.execute(
        select(Offer).where(
            Offer.order_id == order.id,
            Offer.id != offer.id,
            Offer.status == "pending",
        )
    )
    for other_offer in other_offers_res.scalars().all():
        other_offer.status = "rejected"

    await db.flush()
    logger.info("MATCH! order_id=%s driver_id=%s passenger_id=%s", order.id, driver.id, current_user.id)

    # Notification (Task 7.3)
    try:
        from app.services.notification_service import notify_match
        await notify_match(order, driver, current_user)
    except Exception as e:
        logger.warning("Match notification xatosi: %s", e)

    return {
        "message": "Taklif qabul qilindi! Kontaktlar ochildi.",
        "match": {
            "driver": {
                "full_name": driver.full_name,
                "phone_number": driver.phone_number,
                "telegram_username": driver.username,
                "car_model": driver.car_model,
                "car_number": driver.car_number,
                "car_color": driver.car_color,
            }
        },
    }


@router.patch("/{offer_id}/reject")
async def reject_offer(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offer_res = await db.execute(select(Offer).where(Offer.id == offer_id))
    offer = offer_res.scalar_one_or_none()
    if not offer:
        raise HTTPException(status_code=404, detail="Taklif topilmadi")
    offer.status = "rejected"
    return {"message": "Taklif rad etildi"}


@router.get("")
async def list_my_offers(
    status: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Haydovchining o'z takliflari tarixi."""
    query = (
        select(Offer, Order)
        .join(Order, Offer.order_id == Order.id)
        .where(Offer.driver_id == current_user.id)
    )
    if status:
        query = query.where(Offer.status == status)
    query = query.order_by(Offer.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)

    items = []
    for o, ord_ in result.all():
        items.append({
            "id": o.id,
            "order": {
                "from_location": ord_.from_location,
                "to_location": ord_.to_location,
                "passenger_count": ord_.passenger_count,
            },
            "proposed_price": float(o.proposed_price),
            "proposed_time": o.proposed_time,
            "status": o.status,
            "commission_paid": float(o.commission_paid),
            "created_at": o.created_at.isoformat(),
        })
    return {"total": len(items), "items": items}
