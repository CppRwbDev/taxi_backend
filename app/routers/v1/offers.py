import logging
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.offer import Offer
from app.models.order import Order
from app.models.user import User
from app.models.transaction import Transaction
from app.schemas.offer import OfferCreate, OfferOut
from app.routers.v1.users import get_current_user
from app.config import get_commission
from app.services.order_lifecycle import refund_offer, reject_pending_offers, expire_if_needed
from app.utils.errors import api_error

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
    Balans tekshiruvi (FOR UPDATE) → komissiya olinadi → yo'lovchiga notification.
    """
    if current_user.role not in ("driver", "investor"):
        raise HTTPException(status_code=403, detail="Faqat haydovchilar taklif yubora oladi")

    # Buyurtmani tekshirish (bloklangan holda o'qish — yarish (race) himoyasi)
    order_res = await db.execute(
        select(Order).where(Order.id == payload.order_id).with_for_update()
    )
    order = order_res.scalar_one_or_none()
    if not order:
        raise api_error(404, "Buyurtma topilmadi")
    if await expire_if_needed(db, order):
        # Muddat o'tgani bazaga yozildi (keyingi so'rovlar uchun) — commit qilib
        # keyin xato qaytaramiz, aks holda get_db rollback qilardi.
        await db.commit()
        raise api_error(400, "Buyurtma muddati o'tgan", code="ORDER_EXPIRED")
    if order.status not in ("searching", "has_offers"):
        raise api_error(400, "Bu buyurtma endi qabul qilinmaydi", code="ORDER_NOT_ACTIVE")

    # Duplicate check
    dup_res = await db.execute(
        select(Offer).where(
            Offer.order_id == payload.order_id,
            Offer.driver_id == current_user.id,
        )
    )
    if dup_res.scalar_one_or_none():
        raise api_error(
            409,
            "Siz bu buyurtmaga allaqachon taklif yuborgansiz",
            code="DUPLICATE_OFFER",
        )

    # Balans tekshiruvi (aynigan holda — boshqa so'rov bilan parallel yozmaslik uchun)
    user_res = await db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    )
    driver = user_res.scalar_one()

    commission = Decimal(get_commission(order.passenger_count))
    if driver.balance < commission:
        raise api_error(
            402,
            "Balans yetarli emas. Iltimos, to'ldiring.",
            code="INSUFFICIENT_BALANCE",
            required=float(commission),
            current_balance=float(driver.balance),
            headers={"X-Required": str(commission), "X-Current": str(driver.balance)},
        )

    # Komissiyani olib qo'yish
    driver.balance = Decimal(driver.balance) - commission
    offer = Offer(
        order_id=payload.order_id,
        driver_id=driver.id,
        proposed_price=payload.proposed_price,
        proposed_time=payload.proposed_time,
        message=payload.message,
        commission_paid=commission,
    )
    db.add(offer)
    await db.flush()
    await db.refresh(offer)

    db.add(
        Transaction(
            user_id=driver.id,
            amount=-commission,
            type="offer_commission",
            related_offer_id=offer.id,
            description=f"Taklif komissiyasi (buyurtma #{order.id})",
            status="success",
        )
    )

    # Buyurtma statusini yangilash
    if order.status == "searching":
        order.status = "has_offers"

    await db.flush()
    logger.info("Yangi taklif: offer_id=%s driver=%s order=%s", offer.id, driver.id, order.id)

    # Yo'lovchiga notification (Task 7.2)
    try:
        from app.services.notification_service import notify_passenger_new_offer
        await notify_passenger_new_offer(offer, order, driver)
    except Exception as e:
        logger.warning("Passenger notification xatosi: %s", e)

    return {
        "id": offer.id,
        "order_id": offer.order_id,
        "proposed_price": float(offer.proposed_price),
        "proposed_time": offer.proposed_time,
        "commission_paid": float(commission),
        "status": offer.status,
        "driver_balance_after": float(driver.balance),
    }


@router.patch("/{offer_id}/accept")
async def accept_offer(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Task 4.4 — Yo'lovchi taklifni qabul qiladi.
    Match bo'ladi: ikki tomonga kontaktlar ochiladi, boshqa takliflar yopiladi.
    """
    offer_row = await db.execute(select(Offer).where(Offer.id == offer_id).with_for_update())
    offer = offer_row.scalar_one_or_none()
    if not offer:
        raise api_error(404, "Taklif topilmadi")

    order = (
        await db.execute(select(Order).where(Order.id == offer.order_id))
    ).scalar_one_or_none()
    driver = (
        await db.execute(select(User).where(User.id == offer.driver_id))
    ).scalar_one_or_none()
    if not order or not driver:
        raise api_error(404, "Taklifga bog'liq ma'lumot topilmadi")

    if order.passenger_id != current_user.id:
        raise api_error(403, "Bu buyurtma sizniki emas")
    if offer.status != "pending":
        raise api_error(400, "Bu taklif allaqachon o'zgartirilgan", code="OFFER_NOT_PENDING")
    if order.status not in ("searching", "has_offers"):
        raise api_error(
            400,
            f"Buyurtma {order.status} statusida, taklifni qabul qilib bo'lmaydi",
            code="ORDER_NOT_ACTIVE",
        )

    # Match!
    offer.status = "accepted"
    order.status = "matched"
    order.accepted_offer_id = offer.id

    # Boshqa takliflarni reject qilish + komissiyalarini qaytarish
    closed = await reject_pending_offers(
        db, order_id=order.id, exclude_offer_id=offer.id, reason="boshqa taklif tanlandi"
    )

    await db.flush()
    logger.info(
        "MATCH! order_id=%s driver_id=%s passenger_id=%s yopilgan=%s",
        order.id, driver.id, current_user.id, len(closed),
    )

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
    """
    Taklifni rad etish (yo'lovchi) yoki o'z taklifini qaytarish (haydovchi).
    Komissiya qaytariladi (Task 6.3 mantiqi).
    """
    offer_row = await db.execute(select(Offer).where(Offer.id == offer_id).with_for_update())
    offer = offer_row.scalar_one_or_none()
    if not offer:
        raise api_error(404, "Taklif topilmadi")

    order = (
        await db.execute(select(Order).where(Order.id == offer.order_id))
    ).scalar_one_or_none()
    if not order:
        raise api_error(404, "Taklif topilmadi")

    is_owner_passenger = order.passenger_id == current_user.id
    is_owner_driver = offer.driver_id == current_user.id
    is_admin = current_user.role == "admin"

    if not (is_owner_passenger or is_owner_driver or is_admin):
        raise api_error(403, "Bu taklifga ruxsatingiz yo'q", code="FORBIDDEN")
    if offer.status != "pending":
        raise api_error(400, "Bu taklif allaqachon o'zgartirilgan", code="OFFER_NOT_PENDING")
    if order.status in ("matched", "completed", "cancelled"):
        raise api_error(
            400,
            f"Buyurtma {order.status} statusida, taklifni rad etib bo'lmaydi",
            code="ORDER_NOT_ACTIVE",
        )

    offer.status = "rejected"
    refunded = await refund_offer(db, offer, "taklif rad etildi")

    # Faol taklif qolmagan bo'lsa — buyurtma qayta qidiruvga o'tadi
    pending_count = await db.scalar(
        select(func.count(Offer.id)).where(
            Offer.order_id == order.id, Offer.status == "pending"
        )
    )
    if pending_count == 0 and order.status == "has_offers":
        order.status = "searching"

    await db.flush()
    logger.info(
        "Taklif rad etildi: offer_id=%s by user_id=%s refunded=%s",
        offer.id, current_user.id, refunded,
    )
    return {
        "message": "Taklif rad etildi",
        "refunded": float(offer.commission_paid or 0) if refunded else 0.0,
    }


@router.get("")
async def list_my_offers(
    status: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Haydovchining o'z takliflari tarixi."""
    base = (
        select(Offer, Order)
        .join(Order, Offer.order_id == Order.id)
        .where(Offer.driver_id == current_user.id)
    )
    if status:
        base = base.where(Offer.status == status)

    # Jami soni (limitdan oldin) — avvalgi versiyada noto'g'ri hisoblanardi
    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )

    result = await db.execute(base.order_by(Offer.created_at.desc()).limit(limit).offset(offset))

    items = []
    for o, ord_ in result.all():
        items.append({
            "id": o.id,
            "order": {
                "from_location": ord_.from_location,
                "to_location": ord_.to_location,
                "passenger_count": ord_.passenger_count,
                "departure_date": ord_.departure_date,
                "departure_time": ord_.departure_time,
                "status": ord_.status,
            },
            "proposed_price": float(o.proposed_price),
            "proposed_time": o.proposed_time,
            "status": o.status,
            "commission_paid": float(o.commission_paid),
            "refunded": o.status in ("rejected", "cancelled"),
            "created_at": o.created_at.isoformat(),
        })
    return {"total": total or 0, "items": items}
