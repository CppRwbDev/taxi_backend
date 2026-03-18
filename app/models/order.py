from sqlalchemy import (
    Column, Integer, SmallInteger, String, ForeignKey,
    DateTime, Text, BigInteger
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    passenger_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_type = Column(String(20), default="taxi")      # taxi | cargo

    from_location = Column(String(255), nullable=False)
    to_location = Column(String(255), nullable=False)
    from_city = Column(String(100))                      # Qidirish uchun
    to_city = Column(String(100))

    passenger_count = Column(SmallInteger, default=1)
    contact_phone = Column(String(20))
    
    departure_date = Column(String(50))                  # bugun | ertaga | 20-mar
    departure_time = Column(String(20))                  # 14:30


    status = Column(String(20), default="searching", index=True)
    # searching | has_offers | matched | completed | cancelled

    accepted_offer_id = Column(Integer, ForeignKey("offers.id"), nullable=True)
    tg_group_message_id = Column(BigInteger, nullable=True)   # Gruppa xabari ID

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at = Column(
        DateTime(timezone=True),
        server_default=func.now() + func.make_interval(0, 0, 0, 1)  # +24 soat
    )

    # Relationships
    passenger = relationship("User", back_populates="orders", foreign_keys=[passenger_id])
    offers = relationship(
        "Offer",
        back_populates="order",
        foreign_keys="Offer.order_id",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Order id={self.id} {self.from_location}→{self.to_location} status={self.status}>"
