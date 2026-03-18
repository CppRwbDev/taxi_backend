import asyncio
from sqlalchemy import text
from app.database import get_engine

async def add_photo_url_column():
    engine = get_engine()
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN photo_url VARCHAR(500);"))
            print("photo_url column added successfully.")
        except Exception as e:
            print(f"Column might already exist or error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(add_photo_url_column())