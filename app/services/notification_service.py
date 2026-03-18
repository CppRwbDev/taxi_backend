import logging
from app.config import settings

logger = logging.getLogger(__name__)


async def get_bot():
    """aiogram bot instance ni olish."""
    try:
        from aiogram import Bot
        return Bot(token=settings.BOT_TOKEN)
    except Exception as e:
        logger.error("Bot instance yaratishda xato: %s", e)
        return None


async def notify_drivers_group(order, passenger):
    """
    Task 4.2 / Task 7.1 — Yangi buyurtmani haydovchilar guruhiga yuborish.
    """
    if not settings.DRIVERS_GROUP_ID or not settings.BOT_TOKEN:
        logger.warning("BOT_TOKEN yoki DRIVERS_GROUP_ID sozlanmagan, notification o'tkazib yuborildi")
        return

    bot = await get_bot()
    if not bot:
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from app.config import get_commission

    commission = get_commission(order.passenger_count)
    text = (
        f"🆕 <b>Yangi buyurtma!</b>\n\n"
        f"📍 <b>{order.from_location}</b> → <b>{order.to_location}</b>\n"
        f"👥 {order.passenger_count} nafar\n"
        f"📞 {order.contact_phone or 'Ko\\'rsatilmagan'}\n\n"
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
    except Exception as e:
        logger.error("Guruhga xabar yuborishda xato: %s", e)
    finally:
        await bot.session.close()


async def notify_passenger_new_offer(offer, order, driver):
    """
    Task 7.2 — Yo'lovchiga yangi taklif kelgani haqida notification.
    """
    if not settings.BOT_TOKEN:
        return

    bot = await get_bot()
    if not bot:
        return

    from sqlalchemy import select
    from app.database import get_session_factory
    from app.models.user import User

    session_maker = get_session_factory()
    async with session_maker() as session:
        result = await session.execute(select(User).where(User.id == order.passenger_id))
        passenger = result.scalar_one_or_none()

    if not passenger or not passenger.telegram_id:
        await bot.session.close()
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
        logger.info("Yo'lovchiga taklif notification (offer_id=%s, tg_id=%s)", offer.id, passenger.telegram_id)
    except Exception as e:
        logger.error("Yo'lovchiga xabar yuborishda xato: %s", e)
    finally:
        await bot.session.close()


async def notify_match(order, driver, passenger):
    """
    Task 7.3 — Ikki tomonga match notification va kontaktlar ochilishi.
    """
    if not settings.BOT_TOKEN:
        return

    bot = await get_bot()
    if not bot:
        return

    # Haydovchiga
    driver_text = (
        f"🎉 <b>Tabriklaymiz! Siz tanlangiz!</b>\n\n"
        f"👤 Yo'lovchi: <b>{passenger.full_name or 'Nomaʼlum'}</b>\n"
        f"📞 Telefon: <b>{passenger.phone_number or 'Koʻrsatilmagan'}</b>\n"
        f"📍 {order.from_location} → {order.to_location}"
    )

    # Yo'lovchiga
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
    except Exception as e:
        logger.error("Match notification xatosi: %s", e)
    finally:
        await bot.session.close()
