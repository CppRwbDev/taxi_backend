from pydantic_settings import BaseSettings
from typing import Optional


from pydantic import field_validator

class Settings(BaseSettings):
    # --- Telegram ---
    BOT_TOKEN: str = ""
    DRIVERS_GROUP_ID: int = 0
    ADMIN_TELEGRAM_IDS: str = "" # Comma separated: 123456,7891011

    # --- Database ---
    DATABASE_URL: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if v:
            if v.startswith("postgresql://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
            v = v.replace("sslmode=require", "ssl=require")
            v = v.replace("&channel_binding=require", "")
            v = v.replace("?channel_binding=require", "")
        return v

    # --- Backend ---
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"
    SECRET_KEY: str = "change-me"

    # --- Commission rates (UZS) ---
    COMMISSION_1_PAX: int = 5000
    COMMISSION_2_PAX: int = 8000
    COMMISSION_3_PAX: int = 12000
    COMMISSION_4_PAX: int = 15000
    COMMISSION_5_PLUS_PAX: int = 25000

    # --- Admin accounts ---
    ADMIN1_USERNAME: str = "admin1"
    ADMIN1_PASSWORD_HASH: str = ""
    ADMIN2_USERNAME: str = "admin2"
    ADMIN2_PASSWORD_HASH: str = ""
    ADMIN_JWT_SECRET: str = "admin-secret"
    ADMIN_JWT_EXPIRE_MINUTES: int = 480

    # --- Dev accounts ---
    DEV1_USERNAME: str = "dev1"
    DEV1_PASSWORD_HASH: str = ""
    DEV2_USERNAME: str = "dev2"
    DEV2_PASSWORD_HASH: str = ""
    DEV_JWT_SECRET: str = "dev-secret"
    DEV_JWT_EXPIRE_MINUTES: int = 240

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "./logs/app.log"
    LOG_RETENTION_DAYS: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


def get_commission(passenger_count: int) -> int:
    """Yo'lovchilar soniga qarab komissiya narxi (UZS)."""
    mapping = {
        1: settings.COMMISSION_1_PAX,
        2: settings.COMMISSION_2_PAX,
        3: settings.COMMISSION_3_PAX,
        4: settings.COMMISSION_4_PAX,
    }
    if passenger_count >= 5:
        return settings.COMMISSION_5_PLUS_PAX
    return mapping.get(passenger_count, settings.COMMISSION_1_PAX)
