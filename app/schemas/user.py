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
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    role: Optional[str] = None
    language: Optional[str] = None
    theme: Optional[str] = None
    car_model: Optional[str] = None
    car_number: Optional[str] = None
    car_color: Optional[str] = None


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
    created_at: datetime

    class Config:
        from_attributes = True


class OnboardingRequest(BaseModel):
    language: str = Field(..., pattern="^(uz_latn|uz_cyrl)$")
    theme: str = Field(..., pattern="^(dark|light)$")
    role: str = Field(..., pattern="^(passenger|driver|investor)$")
