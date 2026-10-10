"""Buyurtma/taklif hayot tsikli: muddat, bekor qilish, refund.

Bir joyda to'plangani uchun orders.py ham, offers.py ham shuni chaqiradi
(yo'nalish: plan_and_docs/02_Architecture.md dagi order_service/match_service o'rniga).
"""
import logging
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.offer import Offer
from app.models.order import Order
from app.models.transaction import Transaction
from app.models.user import User

logger = logging.getLogger(__name__)


async def refund_offer(
    db: AsyncSession,
    offer: Offer,
    reason: str,
) -> bool:
    """Taklif uchun yechilgan komissiyani qaytaradi (idempotent)."""
    commission = Decimal(offer.commission_paid or 0)
    if commission <= 0:
        return False

    already = await db.execute(
        select(Transaction.id).where(
            Transaction.related_offer_id == offer.id,
            Transaction.type == "refund",
        )
    )
    if already.first():
        return False

    driver = await db.execute(select(User).where(User.id == offer.driver_id))
    driver = driver.scalar_one_or_none()
    if not driver:
        return False

    driver.balance = Decimal(driver.balance) + commission
    db.add(
        Transaction(
            user_id=driver.id,
            amount=commission,
            type="refund",
            related_offer_id=offer.id,
            description=f"Komissiya qaytarildi — {reason} (buyurtma #{offer.order_id})",
            status="success",
        )
    )
    logger.info(
        "Refund: offer_id=%s driver_id=%s amount=%s reason=%s",
        offer.id, driver.id, commission, reason,
    )
    return True


async def reject_pending_offers(
    db: AsyncSession,
    order_id: int,
    exclude_offer_id: int | None,
    reason: str,
) -> list[Offer]:
    """Berilgan buyurtmaning pending takliflarini rejected + refund qiladi."""
    result = await db.execute(
        select(Offer).where(
            Offer.order_id == order_id,
            Offer.status == "pending",
        )
    )
    offers = list(result.scalars().all())
    changed: list[Offer] = []
    for offer in offers:
        if exclude_offer_id and offer.id == exclude_offer_id:
            continue
        offer.status = "rejected"
        await refund_offer(db, offer, reason)
        changed.append(offer)
    return changed


async def close_order_offers(db: AsyncSession, order: Order, reason: str) -> list[Offer]:
    """Buyurtma yopilganda (cancelled/completed) barcha pending takliflarni yopadi."""
    result = await db.execute(
        select(Offer).where(Offer.order_id == order.id, Offer.status == "pending")
    )
    offers = list(result.scalars().all())
    for offer in offers:
        offer.status = "cancelled"
        await refund_offer(db, offer, reason)
    return offers


async def cancel_order(
    db: AsyncSession,
    order: Order,
    reason: str,
) -> list[Offer]:
    """Buyurtmani bekor qiladi + takliflarni yopadi + komissiyalarni qaytaradi."""
    closed = await close_order_offers(db, order, reason)
    order.status = "cancelled"
    await db.flush()
    logger.info("Buyurtma bekor qilindi: order_id=%s reason=%s takliflar=%s", order.id, reason, len(closed))
    return closed


async def expire_if_needed(db: AsyncSession, order: Order) -> bool:
    """Muddati o'tgan buyurtmani bekor qiladi. Qaytaradi: o'zgartirildimi?"""
    from datetime import datetime, timezone

    if order.status not in ("searching", "has_offers"):
        return False
    if not order.expires_at:
        return False
    expires = order.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires > datetime.now(timezone.utc):
        return False
    await cancel_order(db, order, "muddati o'tdi (24 soat)")
    return True


async def expire_due_orders(session_factory, notify_fn=None) -> int:
    """Fon job: muddati o'tgan faol buyurtmalarni bekor qiladi. Qaytarilganlar soni."""
    async with session_factory() as session:
        try:
            result = await session.execute(
                select(Order).where(Order.status.in_(["searching", "has_offers"]))
            )
            orders = list(result.scalars().all())
            expired: list[Order] = []
            for order in orders:
                if await expire_if_needed(session, order):
                    expired.append(order)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Expiry job xatosi")
            return 0

    if notify_fn:
        for order in expired:
            try:
                await notify_fn(order)
            except Exception as e:  # noqa: BLE001
                logger.warning("Expiry notification xatosi (order_id=%s): %s", order.id, e)

    if expired:
        logger.info("Muddati o'tgan buyurtmalar bekor qilindi: %s", [o.id for o in expired])
    return len(expired)
