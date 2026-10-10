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
from app.services.order_lifecycle import cancel_order, expire_if_needed
from app.utils.errors import api_error

router = APIRouter()
logger = logging.getLogger(__name__)

DRIVER_ROLES = ("driver", "investor")


def _now_utc():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _is_expired(order: Order) -> bool:
    if not order.expires_at:
        return False
    expires = order.expires_at
    if expires.tzinfo is None:
        from datetime import timezone as _tz
        expires = expires.replace(tzinfo=_tz.utc)
    return expires <= _now_utc()


@router.post("", response_model=OrderOut, status_code=201)
async def create_order(
    payload: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Task 4.2 — Yo'lovchi buyurtma yaratadi.
    DB ga yoziladi, so'ngra bot orqali haydovchilar guruhiga va shaxsan yuboriladi.
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
        message_id = await notify_drivers_group(order, current_user)
        if message_id:
            order.tg_group_message_id = message_id  # keyin o'chirish/yangilash uchun
        # Hududi mos haydovchilarga shaxsan ham yuboramiz
        await notify_drivers_personally(order)
    except Exception as e:
        logger.warning("Bot notification xatosi: %s", e)
        # Buyurtma baribir saqlanadi, bot xatosi kritik emas

    await db.flush()
    offers_count = 0
    return {**order.__dict__, "offers_count": offers_count}


@router.get("", response_model=list[OrderListItem])
async def list_orders(
    status: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Yo'lovchi (va admin): o'zining buyurtmalari.
    Haydovchi: barcha aktiv yo'lovchi buyurtmalari (lenta).
    """
    if current_user.role in ("passenger", "admin"):
        query = select(Order).where(Order.passenger_id == current_user.id)
    else:
        # Haydovchi aktiv buyurtmalarni ko'radi (o'zining emas, muddati o'tganlar emas)
        query = select(Order).where(
            Order.status.in_(["searching", "has_offers"]),
            Order.passenger_id != current_user.id,
        )

    if status:
        query = query.where(Order.status == status)

    query = query.order_by(Order.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    orders = list(result.scalars().all())

    # Muddati o'tganlar lenta va ro'yxatdan chiqariladi (fon job ularni bekor qiladi)
    orders = [o for o in orders if not (o.status in ("searching", "has_offers") and _is_expired(o))]

    # N+1 ni yo'qotish: barcha orderlar uchun offers_count bitta so'rovda
    counts: dict[int, int] = {}
    if orders:
        ids = [o.id for o in orders]
        cnt_res = await db.execute(
            select(Offer.order_id, func.count(Offer.id))
            .where(Offer.order_id.in_(ids))
            .group_by(Offer.order_id)
        )
        counts = {row[0]: row[1] for row in cnt_res.all()}

    items = []
    for o in orders:
        item_data = {
            "id": o.id,
            "order_type": o.order_type,
            "from_location": o.from_location,
            "to_location": o.to_location,
            "passenger_count": o.passenger_count,
            "status": o.status,
            "departure_date": o.departure_date,
            "departure_time": o.departure_time,
            "offers_count": counts.get(o.id, 0),
            "created_at": o.created_at,
        }
        if current_user.role in DRIVER_ROLES:
            item_data["commission"] = get_commission(o.passenger_count)
        items.append(item_data)

    return items


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()
    if not order:
        raise api_error(404, "Buyurtma topilmadi")

    # Ruxsat: egasi, admin yoki faol buyurtmani ko'rayotgan haydovchi
    is_owner = order.passenger_id == current_user.id
    is_admin = current_user.role == "admin"
    is_driver = current_user.role in DRIVER_ROLES

    if not (is_owner or is_admin or is_driver):
        raise api_error(403, "Bu buyurtmaga ruxsatingiz yo'q")
    if is_driver and not (is_owner or is_admin):
        if order.status not in ("searching", "has_offers"):
            raise api_error(403, "Bu buyurtma endi ochiq emas", code="ORDER_NOT_ACTIVE")

    if await expire_if_needed(db, order):
        # Bekor qilish yozuvini saqlab qolamiz (rollback bo'lmasligi uchun)
        await db.commit()
        raise api_error(400, "Buyurtma muddati o'tgan", code="ORDER_EXPIRED")

    count_res = await db.execute(select(func.count(Offer.id)).where(Offer.order_id == order_id))
    offers_count = count_res.scalar_one()

    data = {**order.__dict__, "offers_count": offers_count}
    # Telefon raqami faqat egasi/admin yoki match bo'lgan haydovchida ko'rinadi
    accepted_driver_id = None
    if order.accepted_offer_id:
        acc = await db.execute(select(Offer).where(Offer.id == order.accepted_offer_id))
        acc_offer = acc.scalar_one_or_none()
        accepted_driver_id = acc_offer.driver_id if acc_offer else None

    can_see_phone = is_owner or is_admin or (accepted_driver_id == current_user.id)
    if not can_see_phone:
        data["contact_phone"] = None
    return data


@router.get("/{order_id}/offers")
async def get_order_offers(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Task 4.3 — Buyurtmaga kelgan takliflarni ko'rish (polling uchun).

    Faqat buyurtma egasi yoki admin ko'ra oladi (haydovchi boshqaning takliflarini ko'rmaydi).
    """
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise api_error(404, "Buyurtma topilmadi")

    if order.passenger_id != current_user.id and current_user.role != "admin":
        raise api_error(403, "Bu buyurtmaga ruxsatingiz yo'q")

    if await expire_if_needed(db, order):
        return {"order_id": order_id, "order_status": "cancelled", "offers": []}

    offers_res = await db.execute(
        select(Offer, User)
        .join(User, Offer.driver_id == User.id)
        .where(Offer.order_id == order_id, Offer.status == "pending")
        .order_by(Offer.created_at.asc())
    )
    rows = offers_res.all()

    return {
        "order_id": order_id,
        "order_status": order.status,
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
async def cancel(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Task 6.3 — Buyurtmani bekor qilish + takliflarni yopish + komissiyalarni qaytarish."""
    result = await db.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()
    if not order:
        raise api_error(404, "Buyurtma topilmadi")
    if order.passenger_id != current_user.id and current_user.role != "admin":
        raise api_error(403, "Bu buyurtma sizniki emas")
    if order.status in ("matched", "completed", "cancelled"):
        raise api_error(
            400,
            f"Buyurtma {order.status} statusida, bekor qilib bo'lmaydi",
            code="ORDER_NOT_CANCELLABLE",
        )

    closed = await cancel_order(db, order, reason="yo'lovchi bekor qildi")
    refunded_total = sum(float(o.commission_paid or 0) for o in closed)

    # Guruh xabarini o'chirish + taklif yuborgan haydovchilarni xabardor qilish
    try:
        from app.services.notification_service import notify_order_cancelled
        await notify_order_cancelled(order, closed)
    except Exception as e:
        logger.warning("Cancel notification xatosi: %s", e)

    logger.info("Buyurtma bekor qilindi: order_id=%s qaytarildi=%s", order_id, refunded_total)
    return {
        "message": "Buyurtma bekor qilindi",
        "refunded_amount": refunded_total,
        "refunded_offers": len(closed),
    }


@router.post("/{order_id}/complete")
async def complete_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Task: buyurtmani yakunlash — yo'lovchi tasdiqlaydi (matched → completed)."""
    result = await db.execute(select(Order).where(Order.id == order_id).with_for_update())
    order = result.scalar_one_or_none()
    if not order:
        raise api_error(404, "Buyurtma topilmadi")
    if order.passenger_id != current_user.id and current_user.role != "admin":
        raise api_error(403, "Bu buyurtma sizniki emas")
    if order.status != "matched":
        raise api_error(
            400,
            f"Faqat 'matched' statusidagi buyurtmani yakunlash mumkin (hozir: {order.status})",
            code="ORDER_NOT_MATCHED",
        )

    order.status = "completed"
    await db.flush()
    logger.info("Buyurtma yakunlandi: order_id=%s driver=%s", order_id, order.accepted_offer_id)
    return {"message": "Buyurtma yakunlandi", "order_id": order_id, "status": order.status}
