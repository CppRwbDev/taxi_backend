import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.order import Order
from app.models.offer import Offer
from app.models.user import User
from app.schemas.order import OrderCreate, OrderOut, OrderListItem
from app.routers.v1.users import get_current_user
from app.config import get_commission

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(
    payload: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Task 4.2 — Yo'lovchi buyurtma yaratadi.
    DB ga yoziladi, so'ngra bot orqali haydovchilar guruhiga yuboriladi.
    """
    order = Order(
        passenger_id=current_user.id,
        order_type=payload.order_type,
        from_location=payload.from_location,
        to_location=payload.to_location,
        from_city=payload.from_city,
        to_city=payload.to_city,
        passenger_count=payload.passenger_count,
        contact_phone=payload.contact_phone or current_user.phone_number,
        departure_date=payload.departure_date,
        departure_time=payload.departure_time,
        status="searching",
    )
    db.add(order)
    await db.flush()
    await db.refresh(order)

    logger.info("Yangi buyurtma: id=%s %s→%s", order.id, order.from_location, order.to_location)

    # Bot orqali haydovchilar guruhiga va shaxsan yuborish
    try:
        from app.services.notification_service import notify_drivers_group, notify_drivers_personally
        await notify_drivers_group(order, current_user)
        # Hududi mos haydovchilarga shaxsan ham yuboramiz
        await notify_drivers_personally(order)
    except Exception as e:
        logger.warning("Bot notification xatosi: %s", e)
        # Buyurtma baribir saqlanadi, bot xatosi kritik emas

    return {**order.__dict__, "offers_count": 0}


@router.get("", response_model=list[OrderListItem])
async def list_orders(
    status: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Yo'lovchi: o'zining buyurtmalari.
    Haydovchi: barcha aktiv yo'lovchi buyurtmalari (lenta).
    """
    if current_user.role == "passenger":
        query = select(Order).where(Order.passenger_id == current_user.id)
    else:
        # Haydovchi aktiv buyurtmalarni ko'radi (o'zining emas)
        query = select(Order).where(
            Order.status.in_(["searching", "has_offers"]),
            Order.passenger_id != current_user.id,
        )

    if status:
        query = query.where(Order.status == status)

    query = query.order_by(Order.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    orders = result.scalars().all()

    commission = get_commission
    items = []
    for o in orders:
        # Har bir buyurtma uchun offer_count
        count_res = await db.execute(
            select(func.count(Offer.id)).where(Offer.order_id == o.id)
        )
        offers_count = count_res.scalar_one()
        item_data = {
            "id": o.id,
            "order_type": o.order_type,
            "from_location": o.from_location,
            "to_location": o.to_location,
            "passenger_count": o.passenger_count,
            "status": o.status,
            "departure_date": o.departure_date,
            "departure_time": o.departure_time,
            "offers_count": offers_count,
            "created_at": o.created_at,
        }
        if current_user.role in ("driver", "investor"):
            item_data["commission"] = commission(o.passenger_count)
        items.append(item_data)

    return items


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    count_res = await db.execute(select(func.count(Offer.id)).where(Offer.order_id == order_id))
    offers_count = count_res.scalar_one()
    return {**order.__dict__, "offers_count": offers_count}


@router.get("/{order_id}/offers")
async def get_order_offers(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Task 4.3 — Buyurtmaga kelgan takliflarni ko'rish (polling uchun)."""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    offers_res = await db.execute(
        select(Offer, User)
        .join(User, Offer.driver_id == User.id)
        .where(Offer.order_id == order_id, Offer.status == "pending")
        .order_by(Offer.created_at.asc())
    )
    rows = offers_res.all()

    return {
        "order_id": order_id,
        "offers": [
            {
                "id": o.id,
                "driver": {
                    "full_name": u.full_name,
                    "car_model": u.car_model,
                    "car_color": u.car_color,
                    "car_number": u.car_number,
                    # Kontaktlar hali yashirin
                },
                "proposed_price": float(o.proposed_price),
                "proposed_time": o.proposed_time,
                "status": o.status,
                "created_at": o.created_at.isoformat(),
            }
            for o, u in rows
        ],
    }


@router.patch("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.passenger_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu buyurtma sizniki emas")
    if order.status in ("matched", "completed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Buyurtma {order.status} statusida, bekor qilib bo'lmaydi")

    order.status = "cancelled"
    logger.info("Buyurtma bekor qilindi: order_id=%s", order_id)
    return {"message": "Buyurtma bekor qilindi", "refunded_amount": 0}
