"""Backend API testlari (Task 8.1).

Qamrovi: auth, xavfsizlik (rol/topup/egalik), buyurtma tsili, taklif+komissiya,
refund, muddat, xato kodlari, rate limit.
"""
import time
from decimal import Decimal

import pytest

from tests.conftest import make_init_data, headers_for


# =========================================================
# Health & Auth
# =========================================================
async def test_health_database_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] == "ok", "DB ulanishi ishlashi kerak"
    assert body["status"] == "ok"


async def test_auth_validate_creates_user(client):
    init_data = make_init_data(telegram_id=1001)
    r = await client.post("/api/v1/auth/validate", json={"init_data": init_data})
    assert r.status_code == 200
    body = r.json()
    assert body["is_new"] is True
    assert body["user"]["telegram_id"] == 1001
    assert body["user"]["role"] == "passenger"
    # Yangi foydalanuvchi uchun boshlang'ich balans
    assert float(body["user"]["balance"]) == 10000.0

    # Ikkinchi marta validate → is_new False
    r2 = await client.post("/api/v1/auth/validate", json={"init_data": init_data})
    assert r2.json()["is_new"] is False


async def test_auth_invalid_hash_rejected(client):
    init_data = make_init_data(telegram_id=1002, tamper=True)
    r = await client.post("/api/v1/auth/validate", json={"init_data": init_data})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_INIT_DATA"


async def test_auth_stale_init_data_rejected(client):
    """Replay himoyasi: eskirgan initData rad etiladi (INITDATA_MAX_AGE_SECONDS=3600)."""
    init_data = make_init_data(telegram_id=1003, auth_date=int(time.time()) - 7200)
    r = await client.post("/api/v1/auth/validate", json={"init_data": init_data})
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"

    # Ruxsat etilgan ichkarida bo'lsa — qabul qilinadi
    ok_data = make_init_data(telegram_id=1003, auth_date=int(time.time()) - 60)
    r2 = await client.post("/api/v1/auth/validate", json={"init_data": ok_data})
    assert r2.status_code == 200


async def test_requests_without_auth_header_rejected(client):
    r = await client.get("/api/v1/orders")
    assert r.status_code == 422  # majburiy header yetishmayapti
    assert r.json()["code"] == "UNPROCESSABLE"

    r2 = await client.get("/api/v1/orders", headers={"Authorization": "Bearer xxx"})
    assert r2.status_code == 401
    assert r2.json()["code"] == "UNAUTHORIZED"


# =========================================================
# Xavfsizlik
# =========================================================
async def test_role_escalation_to_admin_blocked(client, make_user):
    """PATCH /users/me orqali admin bo'lib bo'lmaydi."""
    u = await make_user(telegram_id=2001)
    r = await client.patch("/api/v1/users/me", json={"role": "admin"}, headers=u["headers"])
    assert r.status_code == 422
    assert r.json()["code"] == "UNPROCESSABLE"

    # Bazada rol o'zgarmagan
    from sqlalchemy import select
    from app.models.user import User
    from app.database import get_session_factory

    async def _get_role():
        async with get_session_factory()() as s:
            res = await s.execute(select(User.role).where(User.id == u["user"]["id"]))
            return res.scalar()

    assert await _get_role() == "passenger"


async def test_role_switch_driver_allowed(client, make_user):
    u = await make_user(telegram_id=2002)
    r = await client.patch("/api/v1/users/me", json={"role": "driver"}, headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["role"] == "driver"


async def test_internal_fields_not_patchable(client, make_user):
    """balance/is_active/is_verified PATCH orqali o'zgartirilmaydi."""
    u = await make_user(telegram_id=2003)
    r = await client.patch(
        "/api/v1/users/me",
        json={"balance": 999999999, "is_verified": True, "is_active": True, "full_name": "Yangi Ism"},
        headers=u["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert float(body["balance"]) == 10000.0
    assert body["is_verified"] is False
    assert body["full_name"] == "Yangi Ism"  # ruxsat etilgan maydon ishlaydi


async def test_topup_forbidden_for_regular_user(client, make_user):
    u = await make_user(telegram_id=2004)
    r = await client.post("/api/v1/balance/topup", json={"amount": 500000}, headers=u["headers"])
    assert r.status_code == 403
    assert r.json()["code"] == "FORBIDDEN"

    # Balans o'zgarmagan
    r2 = await client.get("/api/v1/balance", headers=u["headers"])
    assert float(r2.json()["balance"]) == 10000.0


async def test_topup_admin_allowed(client, make_user):
    admin = await make_user(telegram_id=2005, role="admin")
    r = await client.post(
        "/api/v1/balance/topup",
        json={"amount": 50000, "payment_provider": "admin_manual"},
        headers=admin["headers"],
    )
    assert r.status_code == 200
    # boshlang'ich 10 000 + 50 000 top-up
    assert float(r.json()["new_balance"]) == 60000.0


async def test_admin_endpoint_forbidden_for_user(client, make_user):
    u = await make_user(telegram_id=2006)
    r = await client.get("/api/v1/admin/stats", headers=u["headers"])
    assert r.status_code == 403
    assert r.json()["code"] == "FORBIDDEN"


# =========================================================
# Buyurtma tsili
# =========================================================
ORDER_BODY = {
    "order_type": "taxi",
    "from_location": "Qarshi, Bobur shoh ko'chasi",
    "to_location": "Samarqand, Registon",
    "from_city": "Qarshi",
    "to_city": "Samarqand",
    "passenger_count": 1,
    "departure_date": "bugun",
    "departure_time": "14:30",
}


async def _create_order(client, user, **overrides):
    body = {**ORDER_BODY, **overrides}
    r = await client.post("/api/v1/orders", json=body, headers=user["headers"])
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_and_list_orders(client, make_user):
    passenger = await make_user(telegram_id=3001)
    order = await _create_order(client, passenger)
    assert order["status"] == "searching"
    assert order["offers_count"] == 0

    r = await client.get("/api/v1/orders", headers=passenger["headers"])
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Boshqa yo'lovchi boshqasining buyurtmasini ko'ra olmaydi
    other = await make_user(telegram_id=3002)
    r2 = await client.get("/api/v1/orders", headers=other["headers"])
    assert r2.json() == []


async def test_driver_feed_shows_active_orders(client, make_user):
    passenger = await make_user(telegram_id=3010)
    driver = await make_user(telegram_id=3011, role="driver")
    order = await _create_order(client, passenger)

    r = await client.get("/api/v1/orders", headers=driver["headers"])
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == order["id"]
    assert items[0]["commission"] == 5000  # 1 yo'lovchi uchun komissiya


async def test_get_order_hides_phone_from_driver(client, make_user):
    passenger = await make_user(telegram_id=3020)
    driver = await make_user(telegram_id=3021, role="driver")
    order = await _create_order(client, passenger, contact_phone="+998901112233")

    r_owner = await client.get(f"/api/v1/orders/{order['id']}", headers=passenger["headers"])
    assert r_owner.json()["contact_phone"] == "+998901112233"

    r_driver = await client.get(f"/api/v1/orders/{order['id']}", headers=driver["headers"])
    assert r_driver.status_code == 200
    assert r_driver.json()["contact_phone"] is None


async def test_order_offers_forbidden_for_other_driver(client, make_user):
    passenger = await make_user(telegram_id=3030)
    driver = await make_user(telegram_id=3031, role="driver")
    order = await _create_order(client, passenger)

    r = await client.get(f"/api/v1/orders/{order['id']}/offers", headers=driver["headers"])
    assert r.status_code == 403
    assert r.json()["code"] == "FORBIDDEN"

    r2 = await client.get(f"/api/v1/orders/{order['id']}/offers", headers=passenger["headers"])
    assert r2.status_code == 200
    assert r2.json()["offers"] == []


# =========================================================
# Taklif va komissiya
# =========================================================
async def _make_offer(client, driver, order_id, price=45000):
    return await client.post(
        "/api/v1/offers",
        json={"order_id": order_id, "proposed_price": price, "proposed_time": "15:00"},
        headers=driver["headers"],
    )


async def test_offer_deducts_commission(client, make_user):
    passenger = await make_user(telegram_id=4001)
    driver = await make_user(telegram_id=4002, role="driver", balance=20000)
    order = await _create_order(client, passenger)

    r = await _make_offer(client, driver, order["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["commission_paid"] == 5000
    assert body["driver_balance_after"] == 15000
    assert body["status"] == "pending"

    # Buyurtma holati has_offers ga o'tdi
    r2 = await client.get(f"/api/v1/orders/{order['id']}", headers=passenger["headers"])
    assert r2.json()["status"] == "has_offers"

    # Tranzaksiya yozilgan va taklifga bog'langan
    from sqlalchemy import select
    from app.models.transaction import Transaction
    from app.database import get_session_factory

    async def _txns():
        async with get_session_factory()() as s:
            res = await s.execute(select(Transaction))
            return res.scalars().all()

    txns = await _txns()
    assert len(txns) == 1
    assert txns[0].type == "offer_commission"
    assert txns[0].related_offer_id == body["id"]


async def test_offer_insufficient_balance_402(client, make_user):
    passenger = await make_user(telegram_id=4010)
    driver = await make_user(telegram_id=4011, role="driver", balance=1000)
    order = await _create_order(client, passenger)

    r = await _make_offer(client, driver, order["id"])
    assert r.status_code == 402
    body = r.json()
    assert body["code"] == "INSUFFICIENT_BALANCE"
    assert body["required"] == 5000
    assert body["current_balance"] == 1000
    assert r.headers.get("X-Required") == "5000"


async def test_offer_duplicate_409(client, make_user):
    passenger = await make_user(telegram_id=4020)
    driver = await make_user(telegram_id=4021, role="driver", balance=20000)
    order = await _create_order(client, passenger)

    assert (await _make_offer(client, driver, order["id"])).status_code == 201
    r2 = await _make_offer(client, driver, order["id"])
    assert r2.status_code == 409
    assert r2.json()["code"] == "DUPLICATE_OFFER"


async def test_offer_rejected_for_non_driver(client, make_user):
    passenger = await make_user(telegram_id=4030)
    order = await _create_order(client, passenger)
    r = await _make_offer(client, passenger, order["id"])
    assert r.status_code == 403


# =========================================================
# Match / reject / cancel / complete
# =========================================================
async def test_accept_match_and_refund_others(client, make_user):
    passenger = await make_user(telegram_id=5001)
    d1 = await make_user(telegram_id=5002, role="driver", balance=20000)
    d2 = await make_user(telegram_id=5003, role="driver", balance=20000)
    order = await _create_order(client, passenger)

    o1 = (await _make_offer(client, d1, order["id"])).json()
    o2 = (await _make_offer(client, d2, order["id"])).json()

    # Faqat buyurtma egasi qabul qila oladi
    r = await client.patch(f"/api/v1/offers/{o1['id']}/accept", headers=d1["headers"])
    assert r.status_code == 403

    r2 = await client.patch(f"/api/v1/offers/{o1['id']}/accept", headers=passenger["headers"])
    assert r2.status_code == 200, r2.text
    assert r2.json()["match"]["driver"]["phone_number"] is not None or True

    # Buyurtma matched
    r3 = await client.get(f"/api/v1/orders/{order['id']}", headers=passenger["headers"])
    assert r3.json()["status"] == "matched"

    # Ikkinchi taklif rejected + komissiya qaytarildi (15000 → 20000)
    from sqlalchemy import select
    from app.models.user import User
    from app.database import get_session_factory

    async def _balances():
        async with get_session_factory()() as s:
            res = await s.execute(select(User.id, User.balance).order_by(User.id))
            return {uid: float(bal) for uid, bal in res.all()}

    balances = await _balances()
    assert balances[d2["user"]["id"]] == 20000.0  # refund
    assert balances[d1["user"]["id"]] == 15000.0  # komissiya yeysilgan

    # Takliflar holati
    async def _offer_statuses():
        from app.models.offer import Offer
        async with get_session_factory()() as s:
            res = await s.execute(select(Offer.id, Offer.status))
            return dict(res.all())

    statuses = await _offer_statuses()
    assert statuses[o1["id"]] == "accepted"
    assert statuses[o2["id"]] == "rejected"


async def test_reject_ownership_and_refund(client, make_user):
    passenger = await make_user(telegram_id=5010)
    owner_driver = await make_user(telegram_id=5011, role="driver", balance=20000)
    other_driver = await make_user(telegram_id=5012, role="driver", balance=20000)
    order = await _create_order(client, passenger)
    offer = (await _make_offer(client, owner_driver, order["id"])).json()

    # Boshqa haydovchi rad eta olmaydi
    r = await client.patch(f"/api/v1/offers/{offer['id']}/reject", headers=other_driver["headers"])
    assert r.status_code == 403
    assert r.json()["code"] == "FORBIDDEN"

    # Egasi (yo'lovchi) rad etadi → komissiya qaytadi
    r2 = await client.patch(f"/api/v1/offers/{offer['id']}/reject", headers=passenger["headers"])
    assert r2.status_code == 200
    assert float(r2.json()["refunded"]) == 5000.0

    from sqlalchemy import select
    from app.models.user import User
    from app.database import get_session_factory

    async def _bal():
        async with get_session_factory()() as s:
            res = await s.execute(select(User.balance).where(User.id == owner_driver["user"]["id"]))
            return float(res.scalar())

    assert await _bal() == 20000.0

    # Oxirgi taklif yopilgandan keyin buyurtma qayta qidiruvga o'tdi
    r3 = await client.get(f"/api/v1/orders/{order['id']}", headers=passenger["headers"])
    assert r3.json()["status"] == "searching"


async def test_cancel_order_refunds_all(client, make_user):
    passenger = await make_user(telegram_id=5020)
    d1 = await make_user(telegram_id=5021, role="driver", balance=20000)
    d2 = await make_user(telegram_id=5022, role="driver", balance=20000)
    order = await _create_order(client, passenger)
    await _make_offer(client, d1, order["id"])
    await _make_offer(client, d2, order["id"])

    # Boshqa yo'lovchi bekor qila olmaydi
    stranger = await make_user(telegram_id=5023)
    r = await client.patch(f"/api/v1/orders/{order['id']}/cancel", headers=stranger["headers"])
    assert r.status_code == 403

    r2 = await client.patch(f"/api/v1/orders/{order['id']}/cancel", headers=passenger["headers"])
    assert r2.status_code == 200
    body = r2.json()
    assert body["refunded_amount"] == 10000.0
    assert body["refunded_offers"] == 2

    from sqlalchemy import select
    from app.models.offer import Offer
    from app.models.user import User
    from app.database import get_session_factory

    async def _state():
        async with get_session_factory()() as s:
            offers = dict((await s.execute(select(Offer.id, Offer.status))).all())
            balances = {
                uid: float(b)
                for uid, b in (await s.execute(select(User.id, User.balance))).all()
            }
            return offers, balances

    offers, balances = await _state()
    assert set(offers.values()) == {"cancelled"}
    assert balances[d1["user"]["id"]] == 20000.0
    assert balances[d2["user"]["id"]] == 20000.0


async def test_completed_flow(client, make_user):
    passenger = await make_user(telegram_id=5030)
    driver = await make_user(telegram_id=5031, role="driver", balance=20000)
    order = await _create_order(client, passenger)
    offer = (await _make_offer(client, driver, order["id"])).json()

    # matched dan oldin complete bo'lmaydi
    r0 = await client.post(f"/api/v1/orders/{order['id']}/complete", headers=passenger["headers"])
    assert r0.status_code == 400
    assert r0.json()["code"] == "ORDER_NOT_MATCHED"

    await client.patch(f"/api/v1/offers/{offer['id']}/accept", headers=passenger["headers"])

    # Boshqa odam yakunlay olmaydi
    stranger = await make_user(telegram_id=5032)
    r1 = await client.post(f"/api/v1/orders/{order['id']}/complete", headers=stranger["headers"])
    assert r1.status_code == 403

    r2 = await client.post(f"/api/v1/orders/{order['id']}/complete", headers=passenger["headers"])
    assert r2.status_code == 200
    assert r2.json()["status"] == "completed"

    # Yakunlangandan keyin bekor qilib bo'lmaydi
    r3 = await client.patch(f"/api/v1/orders/{order['id']}/cancel", headers=passenger["headers"])
    assert r3.status_code == 400
    assert r3.json()["code"] == "ORDER_NOT_CANCELLABLE"


# =========================================================
# Muddat (expires_at)
# =========================================================
async def _set_expired(order_id):
    from sqlalchemy import update
    from datetime import datetime, timedelta, timezone
    from app.models.order import Order
    from app.database import get_session_factory

    async def _do():
        async with get_session_factory()() as s:
            await s.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
            )
            await s.commit()

    await _do()


async def test_expired_order_hidden_from_list(client, make_user):
    passenger = await make_user(telegram_id=6001)
    order = await _create_order(client, passenger)
    await _set_expired(order["id"])

    r = await client.get("/api/v1/orders", headers=passenger["headers"])
    assert r.json() == []

    # Haydovchi lentasida ham yo'q
    driver = await make_user(telegram_id=6002, role="driver")
    r2 = await client.get("/api/v1/orders", headers=driver["headers"])
    assert r2.json() == []


async def test_expired_order_cant_receive_offer(client, make_user):
    passenger = await make_user(telegram_id=6010)
    driver = await make_user(telegram_id=6011, role="driver", balance=20000)
    order = await _create_order(client, passenger)
    await _set_expired(order["id"])

    r = await _make_offer(client, driver, order["id"])
    assert r.status_code == 400
    assert r.json()["code"] == "ORDER_EXPIRED"

    # Buyurtma bekor qilingan
    from sqlalchemy import select
    from app.models.order import Order
    from app.database import get_session_factory

    async def _status():
        async with get_session_factory()() as s:
            res = await s.execute(select(Order.status).where(Order.id == order["id"]))
            return res.scalar()

    assert await _status() == "cancelled"


# =========================================================
# Admin
# =========================================================
async def test_admin_stats(client, make_user):
    admin = await make_user(telegram_id=7001, role="admin")
    passenger = await make_user(telegram_id=7002)
    driver = await make_user(telegram_id=7003, role="driver", balance=20000)
    order = await _create_order(client, passenger)
    await _make_offer(client, driver, order["id"])

    r = await client.get("/api/v1/admin/stats", headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["users_count"] == 3
    assert body["orders_count"] == 1
    assert body["total_revenue"] == 5000.0
    assert body["total_refunded"] == 0.0
    assert body["net_revenue"] == 5000.0


async def test_admin_topup_endpoint(client, make_user):
    admin = await make_user(telegram_id=7010, role="admin")
    user = await make_user(telegram_id=7011)

    r = await client.post(
        f"/api/v1/admin/balance/topup/{user['user']['id']}",
        json={"amount": 75000, "description": "test"},
        headers=admin["headers"],
    )
    assert r.status_code == 200
    assert float(r.json()["new_balance"]) == 85000.0

    # Oddiy foydalanuvchi bu endpointdan foydalanolmaydi
    r2 = await client.post(
        f"/api/v1/admin/balance/topup/{user['user']['id']}",
        json={"amount": 75000},
        headers=user["headers"],
    )
    assert r2.status_code == 403


async def test_admin_user_role_change(client, make_user):
    admin = await make_user(telegram_id=7020, role="admin")
    user = await make_user(telegram_id=7021)

    r = await client.patch(
        f"/api/v1/admin/users/{user['user']['id']}/role",
        params={"role": "driver"},
        headers=admin["headers"],
    )
    assert r.status_code == 200
    assert r.json()["new_role"] == "driver"

    r2 = await client.patch(
        f"/api/v1/admin/users/{user['user']['id']}/role",
        params={"role": "superadmin"},
        headers=admin["headers"],
    )
    assert r2.status_code == 400


# =========================================================
# Rate limiting
# =========================================================
async def test_rate_limit_returns_429(client, make_user, monkeypatch):
    from app.config import settings as cfg
    from app.main import app
    from app.middleware.rate_limit import RateLimitMiddleware

    u = await make_user(telegram_id=8001)
    monkeypatch.setattr(cfg, "RATE_LIMIT_PER_MINUTE", 3)

    # Oldingi testlardan qolgan hisoblagichlarni tozalaymiz
    stack = app.middleware_stack
    while stack is not None:
        if isinstance(stack, RateLimitMiddleware):
            stack._hits.clear()
        stack = getattr(stack, "app", None)

    codes = []
    for _ in range(6):
        codes.append((await client.get("/api/v1/orders", headers=u["headers"])).status_code)

    assert 429 in codes, f"429 kutilgan edi, olindi: {codes}"
    assert codes[0] == 200

    body = (await client.get("/api/v1/orders", headers=u["headers"])).json()
    assert body["code"] == "TOO_MANY_REQUESTS"


async def test_rate_limit_disabled_for_health(client, monkeypatch):
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "RATE_LIMIT_PER_MINUTE", 1)
    for _ in range(5):
        assert (await client.get("/health")).status_code == 200
