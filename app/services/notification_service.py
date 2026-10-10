import logging
from app.config import settings

logger = logging.getLogger(__name__)


def get_bot():
    """Bot instance'ni qaytaradi (yagona, umumiy session).

    Eski versiya har xabar uchun yangi Bot() yaratib, session'ni yopar edi.
    """
    if not settings.BOT_TOKEN:
        return None
    try:
        from bot.main import bot as shared_bot
        return shared_bot
    except Exception as e:  # noqa: BLE001
        logger.error("Bot instance olishda xato: %s", e)
        return None


async def notify_drivers_group(order, passenger) -> int | None:
    """
    Task 4.2 / Task 7.1 — Yangi buyurtmani haydovchilar guruhiga yuborish.
    Qaytaradi: message_id (keyin guruh xabarini o'chirish/yangilash uchun).
    """
    if not settings.DRIVERS_GROUP_ID or not settings.BOT_TOKEN:
        logger.warning("BOT_TOKEN yoki DRIVERS_GROUP_ID sozlanmagan, notification o'tkazib yuborildi")
        return None

    bot = get_bot()
    if not bot:
        return None

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from app.config import get_commission

    commission = get_commission(order.passenger_count)
    text = (
        f"🆕 <b>Yangi buyurtma!</b>\n\n"
        f"📍 <b>{order.from_location}</b> → <b>{order.to_location}</b>\n"
        f"📅 Sana: <b>{order.departure_date or 'Bugun'}</b>\n"
        f"⏰ Vaqt: <b>{order.departure_time or 'Hozir'}</b>\n"
        f"👥 {order.passenger_count} nafar\n"
        f"📞 {order.contact_phone or 'Noma`lum'}\n\n"
        f"💰 <i>Komissiya: {commission:,} UZS</i>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"🚀 Taklif yuborish · {commission:,} UZS",
            callback_data=f"take_order:{order.id}",
        )
    ]])

    try:
        msg = await bot.send_message(
            chat_id=settings.DRIVERS_GROUP_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        logger.info("Guruhga xabar yuborildi: message_id=%s order_id=%s", msg.message_id, order.id)
        return msg.message_id
    except Exception as e:  # noqa: BLE001
        logger.error("Guruhga xabar yuborishda xato: %s", e)
        return None


async def _passenger_by_order(order):
    from sqlalchemy import select
    from app.database import get_session_factory
    from app.models.user import User

    session_maker = get_session_factory()
    async with session_maker() as session:
        result = await session.execute(select(User).where(User.id == order.passenger_id))
        return result.scalar_one_or_none()


async def notify_passenger_new_offer(offer, order, driver):
    """
    Task 7.2 — Yo'lovchiga yangi taklif kelgani haqida notification.
    """
    bot = get_bot()
    if not bot:
        return

    passenger = await _passenger_by_order(order)
    if not passenger or not passenger.telegram_id:
        return

    text = (
        f"💬 <b>Yangi taklif keldi!</b>\n\n"
        f"🚗 Haydovchi: <b>{driver.full_name or 'Nomaʼlum'}</b>\n"
        f"🚙 Mashina: {driver.car_model or ''} {driver.car_color or ''}\n"
        f"💵 Narx: <b>{int(offer.proposed_price):,} UZS</b>\n"
        f"⏰ Joʻnash: {offer.proposed_time or 'Koʻrsatilmagan'}\n\n"
        f"📍 {order.from_location} → {order.to_location}"
    )

    try:
        await bot.send_message(passenger.telegram_id, text, parse_mode="HTML")
        logger.info("Yo'lovchiga taklif notification (offer_id=%s tg_id=%s)", offer.id, passenger.telegram_id)
    except Exception as e:  # noqa: BLE001
        logger.error("Yo'lovchiga xabar yuborishda xato: %s", e)


async def notify_match(order, driver, passenger):
    """
    Task 7.3 — Ikki tomonga match notification va kontaktlar ochilishi.
    """
    bot = get_bot()
    if not bot:
        return

    driver_text = (
        f"🎉 <b>Tabriklaymiz! Siz tanlangiz!</b>\n\n"
        f"👤 Yo'lovchi: <b>{passenger.full_name or 'Nomaʼlum'}</b>\n"
        f"📞 Telefon: <b>{passenger.phone_number or 'Koʻrsatilmagan'}</b>\n"
        f"📍 {order.from_location} → {order.to_location}"
    )

    passenger_text = (
        f"✅ <b>Haydovchi topildi!</b>\n\n"
        f"👤 Haydovchi: <b>{driver.full_name or 'Nomaʼlum'}</b>\n"
        f"📞 Telefon: <b>{driver.phone_number or 'Koʻrsatilmagan'}</b>\n"
        f"🚙 Mashina: {driver.car_model or ''} {driver.car_number or ''}\n"
        f"📍 {order.from_location} → {order.to_location}"
    )

    try:
        if driver.telegram_id:
            await bot.send_message(driver.telegram_id, driver_text, parse_mode="HTML")
        if passenger.telegram_id:
            await bot.send_message(passenger.telegram_id, passenger_text, parse_mode="HTML")
        logger.info("Match notification yuborildi: order_id=%s", order.id)
    except Exception as e:  # noqa: BLE001
        logger.error("Match notification xatosi: %s", e)


async def notify_order_cancelled(order, closed_offers=None):
    """Buyurtma bekor qilindi → guruh xabari o'chiriladi, haydovchilarga xabar ketadi."""
    bot = get_bot()
    if not bot:
        return

    # 1) Guruhdagi eski xabarni o'chirish (tugma ishlamay qolmasin)
    if settings.DRIVERS_GROUP_ID and order.tg_group_message_id:
        try:
            await bot.delete_message(settings.DRIVERS_GROUP_ID, order.tg_group_message_id)
            logger.info("Guruh xabari o'chirildi: %s", order.tg_group_message_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("Guruh xabarini o'chirib bo'lmadi: %s", e)

    # 2) Taklif yuborgan haydovchilarga shaxsiy xabar
    driver_ids = {o.driver_id for o in (closed_offers or [])}
    if not driver_ids:
        return

    from sqlalchemy import select
    from app.database import get_session_factory
    from app.models.user import User

    session_maker = get_session_factory()
    async with session_maker() as session:
        result = await session.execute(select(User).where(User.id.in_(driver_ids)))
        drivers = result.scalars().all()

    text = (
        f"❌ <b>Buyurtma bekor qilindi</b>\n\n"
        f"📍 {order.from_location} → {order.to_location}\n"
        f"💰 Komissiya hisobingizga qaytarildi."
    )
    for driver in drivers:
        if not driver.telegram_id:
            continue
        try:
            await bot.send_message(driver.telegram_id, text, parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            logger.warning("Cancel xatosi (user %s): %s", driver.id, e)

    logger.info("Bekor qilish notification: order_id=%s haydovchilar=%s", order.id, len(driver_ids))


async def notify_order_expired(order):
    """Muddati o'tgan buyurtma haqida haydovchilarga xabar."""
    bot = get_bot()
    if not bot:
        return
    if settings.DRIVERS_GROUP_ID and order.tg_group_message_id:
        try:
            await bot.delete_message(settings.DRIVERS_GROUP_ID, order.tg_group_message_id)
        except Exception:  # noqa: BLE001
            pass
    logger.info("Muddati o'tgan buyurtma yopildi: order_id=%s", order.id)


async def notify_drivers_personally(order):
    """
    Yangi buyurtma haqida mos keluvchi hudud haydovchilariga shaxsiy xabar yuborish.
    """
    bot = get_bot()
    if not bot:
        return

    from sqlalchemy import select, or_, and_
    from app.database import get_session_factory
    from app.models.user import User

    # working_cities: "Toshkent,Andijon" ko'rinishida → har bir shahar alohida tekshiriladi.
    # order.from_location to'liq manzil bo'lgani uchun from_city/to_city ishlatiladi.
    candidates: list[str] = []
    for value in (order.from_city, order.to_city, order.from_location, order.to_location):
        if value:
            candidates.append(value.strip())

    if not candidates:
        return

    conditions = []
    for value in candidates:
        conditions.append(User.working_cities.ilike(f"%{value}%"))

    session_maker = get_session_factory()
    async with session_maker() as session:
        result = await session.execute(
            select(User).where(
                User.role.in_(["driver", "investor"]),
                User.is_active.is_(True),
                or_(*conditions),
            )
        )
        drivers = result.scalars().all()

    if not drivers:
        return

    text = (
        f"🔔 <b>Sizning hududingizda yangi buyurtma!</b>\n\n"
        f"📍 {order.from_location} → {order.to_location}\n"
        f"📅 {order.departure_date or 'Bugun'}\n"
        f"⏰ {order.departure_time or 'Hozir'}\n"
        f"👥 {order.passenger_count} yo'lovchi"
    )

    for driver in drivers:
        if not driver.telegram_id:
            continue
        try:
            await bot.send_message(driver.telegram_id, text, parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            logger.warning("Driver serial notification error for user %s: %s", driver.id, e)
