from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from decimal import Decimal


class OrderCreate(BaseModel):
    order_type: Literal["taxi", "cargo"] = "taxi"
    from_location: str = Field(..., min_length=2)
    to_location: str = Field(..., min_length=2)
    from_city: Optional[str] = None
    to_city: Optional[str] = None
    passenger_count: int = Field(default=1, ge=1, le=20)
    contact_phone: Optional[str] = None
    departure_date: str = "bugun"
    departure_time: str = "hozir"


class OrderOut(BaseModel):
    id: int
    order_type: str
    from_location: str
    to_location: str
    passenger_count: int
    contact_phone: Optional[str] = None
    departure_date: Optional[str] = None
    departure_time: Optional[str] = None
    status: str
    accepted_offer_id: Optional[int] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    offers_count: int = 0

    class Config:
        from_attributes = True


class OrderListItem(BaseModel):
    id: int
    order_type: str
    from_location: str
    to_location: str
    passenger_count: int
    status: str
    departure_date: Optional[str] = None
    departure_time: Optional[str] = None
    commission: Optional[int] = None   # Haydovchilar uchun
    offers_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True
