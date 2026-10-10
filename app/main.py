import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.utils.logger import setup_logging
from app.middleware.logging_middleware import LoggingMiddleware
from bot.main import start_bot, stop_bot

# Loglashni ishga tushirish
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup va Shutdown hodisalari."""
    logger.info("🚀 Viloyatlararo Taksi API ishga tushmoqda...")
    logger.info("Frontend URL: %s", settings.FRONTEND_URL)

    # Telegram botni fonda ishga tushirish
    bot_task = asyncio.create_task(start_bot())

    # Buyurtma muddati (expires_at) fon tekshiruvi — Task 7.4
    expiry_task = None
    if settings.ORDER_EXPIRY_JOB_ENABLED:
        async def _expiry_loop():
            from app.database import get_session_factory
            from app.services.order_lifecycle import expire_due_orders
            from app.services.notification_service import notify_order_expired
            while True:
                await asyncio.sleep(settings.ORDER_EXPIRY_INTERVAL_SECONDS)
                try:
                    n = await expire_due_orders(get_session_factory(), notify_order_expired)
                    if n:
                        logger.info("Expiry job: %s ta buyurtma bekor qilindi", n)
                except Exception as e:  # noqa: BLE001
                    logger.error("Expiry job xatosi: %s", e)

        expiry_task = asyncio.create_task(_expiry_loop())
        logger.info(
            "⏳ Expiry job yoqilgan (har %ss)",
            settings.ORDER_EXPIRY_INTERVAL_SECONDS,
        )

    yield

    logger.info("🛑 API to'xtatildi.")
    if expiry_task:
        expiry_task.cancel()
        try:
            await expiry_task
        except asyncio.CancelledError:
            pass
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass
    await stop_bot()


app = FastAPI(
    title="Viloyatlararo Taksi API",
    description="Telegram Mini App uchun backend — yo'lovchi va haydovchi platformasi",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ==========================================
# CORS — Frontend dan so'rovlarga ruxsat
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Loglash middleware
app.add_middleware(LoggingMiddleware)

# Rate limiting (API endpointlar uchun)
from app.middleware.rate_limit import RateLimitMiddleware  # noqa: E402
app.add_middleware(RateLimitMiddleware)

# Yagona xato shakli: {detail, code, ...}
from app.utils.errors import install_exception_handlers  # noqa: E402
install_exception_handlers(app)


# ==========================================
# ROUTERS — import
# ==========================================
from app.routers.v1 import auth, users, orders, offers, balance, admin  # noqa: E402

app.include_router(auth.router,    prefix="/api/v1/auth",    tags=["Auth"])
app.include_router(users.router,   prefix="/api/v1/users",   tags=["Users"])
app.include_router(orders.router,  prefix="/api/v1/orders",  tags=["Orders"])
app.include_router(offers.router,  prefix="/api/v1/offers",  tags=["Offers"])
app.include_router(balance.router, prefix="/api/v1/balance", tags=["Balance"])
app.include_router(admin.router,   prefix="/api/v1/admin",   tags=["Admin"])


# ==========================================
# HEALTH CHECK
# ==========================================
@app.get("/health", tags=["Health"])
async def health_check():
    """Task 1.5 — Bazaga ulanishni tekshirish."""
    try:
        from app.database import get_engine
        from sqlalchemy import text
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.error("DB health check failed: %s", e)
        db_status = "error"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        "version": "1.0.0",
    }


@app.get("/", tags=["Health"])
async def root():
    return {"message": "Viloyatlararo Taksi API ishlayapti 🚕"}
