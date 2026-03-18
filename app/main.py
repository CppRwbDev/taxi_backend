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
    
    yield
    
    logger.info("🛑 API to'xtatildi.")
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
        from app.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.error("DB health check failed: %s", e)
        db_status = "error"

    return {
        "status": "ok",
        "database": db_status,
        "version": "1.0.0",
    }


@app.get("/", tags=["Health"])
async def root():
    return {"message": "Viloyatlararo Taksi API ishlayapti 🚕"}
