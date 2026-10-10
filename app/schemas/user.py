from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


class UserBase(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    phone_number: Optional[str] = None
    role: str = "passenger"
    language: str = "uz_latn"
    theme: str = "dark"


class UserCreate(UserBase):
    telegram_id: int


class UserUpdate(BaseModel):
    """Profil yangilash uchun ruxsat etilgan maydonlar.

    Ixtiyoriy (ichki/finans) maydonlar shu yerdan ataylab chetlab o'tiladi:
    role, balance, is_active, is_verified, telegram_id, photo_url, is_onboarded.
    """
    full_name: Optional[str] = Field(None, max_length=200)
    phone_number: Optional[str] = Field(None, max_length=30)
    # "admin" rolini faqat ADMIN_TELEGRAM_IDS orqali berish mumkin (auth.py)
    role: Optional[str] = Field(None, pattern="^(passenger|driver|investor)$")
    language: Optional[str] = Field(None, pattern="^(uz_latn|uz_cyrl)$")
    theme: Optional[str] = Field(None, pattern="^(dark|light)$")
    car_model: Optional[str] = Field(None, max_length=100)
    car_number: Optional[str] = Field(None, max_length=20)
    car_color: Optional[str] = Field(None, max_length=50)
    working_cities: Optional[str] = Field(None, max_length=500)


class UserOut(UserBase):
    id: int
    telegram_id: int
    is_onboarded: bool
    is_active: bool
    is_verified: bool
    balance: Decimal
    car_model: Optional[str] = None
    car_number: Optional[str] = None
    car_color: Optional[str] = None
    working_cities: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OnboardingRequest(BaseModel):
    language: str = Field(..., pattern="^(uz_latn|uz_cyrl)$")
    theme: str = Field(..., pattern="^(dark|light)$")
    role: str = Field(..., pattern="^(passenger|driver|investor)$")
    working_cities: Optional[str] = None
