from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func
from typing import AsyncGenerator


class Base(DeclarativeBase):
    """Barcha modellar shu Base dan merosxo'r bo'ladi."""
    pass


# Engine va sessionni lazy yaratish — importda emas, birinchi ishlatilganda
_engine = None
_AsyncSessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        from app.config import settings
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory():
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency — har so'rov uchun yangi DB session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Jadvallarni yaratish (development). Production da Alembic ishlatiladi."""
    engine = get_engine()
    async with engine.begin() as conn:
        from app.models import user, order, offer, transaction  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)


# Alembic uchun engine ham, /health tekshiruvi uchun ham ishlatiladi.
# Eski versiyada @property module darajasida edi -> engine.connect() doim xato berardi.
def get_sync_ready_engine():
    return get_engine()


# Kelegi uchun nom (eski importlarni sindirmaslik uchun)
engine = get_engine
