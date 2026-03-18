from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


class OfferCreate(BaseModel):
    order_id: int
    proposed_price: Decimal = Field(..., gt=0)
    proposed_time: Optional[str] = None   # "08:00", "Hozir", ...
    message: Optional[str] = None


class DriverInfo(BaseModel):
    full_name: Optional[str] = None
    car_model: Optional[str] = None
    car_number: Optional[str] = None
    car_color: Optional[str] = None
    phone_number: Optional[str] = None   # Faqat match bo'lsa ko'rinadi
    username: Optional[str] = None       # Faqat match bo'lsa

    class Config:
        from_attributes = True


class OfferOut(BaseModel):
    id: int
    order_id: int
    driver: DriverInfo
    proposed_price: Decimal
    proposed_time: Optional[str] = None
    message: Optional[str] = None
    commission_paid: Decimal
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class MatchResult(BaseModel):
    """Ikkala tomon kelishganda qaytariladigan ma'lumotlar."""
    driver: DriverInfo
