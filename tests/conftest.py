"""Pytest konfiguratsiyasi.

Muhit (app import qilinishdan oldin o'rnatiladi):
- DATABASE_URL → lokal test bazasi (prod'ga tegmaydi)
- BOT_TOKEN → bo'sh (Telegram ga xabar yuborilmaydi)

Barcha testlar async — bitta event loop (session scope) ichida ishlaydi,
shu sababli asyncpg connection pool bir xil loopga bog'lanadi.
"""
import os
import hashlib
import hmac
import json
import time
import urllib.parse

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://saidjon@127.0.0.1:54329/taxi_test"
)
os.environ["BOT_TOKEN"] = ""
os.environ["DRIVERS_GROUP_ID"] = "0"
os.environ["ADMIN_TELEGRAM_IDS"] = ""
os.environ["ORDER_EXPIRY_JOB_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "true"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "100000"
os.environ["INITDATA_MAX_AGE_SECONDS"] = "3600"

import asyncio  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.database import get_session_factory  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    """Barcha testlar uchun yagona event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def make_init_data(
    telegram_id: int = 111222333,
    first_name: str = "Test",
    last_name: str = "User",
    auth_date: int | None = None,
    tamper: bool = False,
) -> str:
    """Telegram WebApp initData yaratadi (lokal HMAC, bot token bilan)."""
    if auth_date is None:
        auth_date = int(time.time())
    user = json.dumps(
        {"id": telegram_id, "first_name": first_name, "last_name": last_name, "username": "tester"},
        separators=(",", ":"),
    )
    fields = {"user": user, "auth_date": str(auth_date)}
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", (settings.BOT_TOKEN or "").encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["hash"] = "0" * 64
    return urllib.parse.urlencode(fields)


def headers_for(init_data: str) -> dict:
    return {"Authorization": f"tma_{init_data}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
async def client():
    """ASGI client + app lifespan (startup/shutdown) bilan."""
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


@pytest.fixture(autouse=True)
async def clean_db():
    """Har bir testdan oldin jadvallarni tozalaydi."""
    from sqlalchemy import text

    async with get_session_factory()() as session:
        await session.execute(text("DELETE FROM transactions"))
        # orders.accepted_offer_id → offers FK (rollbackni kesmaslik uchun avval bo'shatamiz)
        await session.execute(text("UPDATE orders SET accepted_offer_id = NULL"))
        await session.execute(text("DELETE FROM offers"))
        await session.execute(text("DELETE FROM orders"))
        await session.execute(text("DELETE FROM users"))
        await session.commit()
    yield


@pytest.fixture()
async def make_user(client):
    """Telegram orqali foydalanuvchi yaratadi, rolni/balansni o'rnatadi."""

    async def _make(telegram_id: int, role: str = "passenger", balance: float | None = None):
        init_data = make_init_data(telegram_id=telegram_id)
        r = await client.post("/api/v1/auth/validate", json={"init_data": init_data})
        assert r.status_code == 200, r.text
        user = r.json()["user"]

        if role == "admin":
            from sqlalchemy import update
            from app.models.user import User

            async with get_session_factory()() as session:
                await session.execute(
                    update(User).where(User.id == user["id"]).values(role="admin")
                )
                await session.commit()
            user["role"] = "admin"
        elif role != "passenger":
            r2 = await client.patch(
                "/api/v1/users/me", json={"role": role}, headers=headers_for(init_data)
            )
            assert r2.status_code == 200, r2.text
            user = r2.json()

        if balance is not None:
            from decimal import Decimal
            from sqlalchemy import update
            from app.models.user import User

            async with get_session_factory()() as session:
                await session.execute(
                    update(User).where(User.id == user["id"]).values(balance=Decimal(str(balance)))
                )
                await session.commit()
            user["balance"] = balance

        return {"init_data": init_data, "headers": headers_for(init_data), "user": user}

    return _make
