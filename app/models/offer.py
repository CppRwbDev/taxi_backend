from sqlalchemy import (
    Column, Integer, String, ForeignKey,
    DateTime, Text, Numeric, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Offer(Base):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    proposed_price = Column(Numeric(12, 2), nullable=False)  # UZS
    proposed_time = Column(String(50))                        # "08:00", "Hozir" ...
    message = Column(Text)                                    # Ixtiyoriy izoh
    commission_paid = Column(Numeric(12, 2), default=0.00)   # To'langan komissiya

    status = Column(String(20), default="pending", index=True)
    # pending | accepted | rejected | cancelled

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Bir haydovchi bir buyurtmaga faqat 1 ta taklif bera oladi
    __table_args__ = (
        UniqueConstraint("order_id", "driver_id", name="uq_offer_order_driver"),
    )

    # Relationships
    order = relationship("Order", back_populates="offers", foreign_keys=[order_id])
    driver = relationship("User", back_populates="offers", foreign_keys=[driver_id])
    transactions = relationship("Transaction", back_populates="offer")

    def __repr__(self):
        return f"<Offer id={self.id} order={self.order_id} driver={self.driver_id} price={self.proposed_price}>"
