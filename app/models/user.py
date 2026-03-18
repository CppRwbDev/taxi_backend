from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean,
    Numeric, DateTime, text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    full_name = Column(String(255))
    username = Column(String(100))                      # TG @username
    photo_url = Column(String(500))                     # TG Profile picture URL
    phone_number = Column(String(20))
    role = Column(String(20), nullable=False)            # passenger | driver | investor
    language = Column(String(10), default="uz_latn")    # uz_latn | uz_cyrl
    theme = Column(String(10), default="dark")           # dark | light
    is_onboarded = Column(Boolean, default=False)
    balance = Column(Numeric(12, 2), default=0.00)      # Haydovchi balansi (UZS)

    # Haydovchi qo'shimcha ma'lumotlari
    car_model = Column(String(100))
    car_number = Column(String(20))
    car_color = Column(String(50))
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    orders = relationship("Order", back_populates="passenger", foreign_keys="Order.passenger_id")
    offers = relationship("Offer", back_populates="driver", foreign_keys="Offer.driver_id")
    transactions = relationship("Transaction", back_populates="user")

    def __repr__(self):
        return f"<User id={self.id} tg={self.telegram_id} role={self.role}>"
