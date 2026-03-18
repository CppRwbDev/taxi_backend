import asyncio
from sqlalchemy import select, update
from app.database import get_session_factory
from app.models.user import User

async def make_admin():
    telegram_id_input = input("Admin qilmoqchi bo'lgan foydalanuvchining Telegram ID sini kiriting: ")
    try:
        tg_id = int(telegram_id_input)
    except ValueError:
        print("Xato: Telegram ID faqat raqamlardan iborat bo'lishi kerak!")
        return

    session_maker = get_session_factory()
    async with session_maker() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"Xato: {tg_id} ID li foydalanuvchi bazadan topilmadi. Avval botga kirib ro'yxatdan o'tgan bo'lishi kerak.")
            return
            
        user.role = "admin"
        await session.commit()
        print(f"Muvaffaqiyatli! Foydalanuvchi {user.full_name} ({user.telegram_id}) endi ADMIN rolida.")

if __name__ == "__main__":
    asyncio.run(make_admin())