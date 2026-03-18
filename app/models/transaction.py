from sqlalchemy import (
    Column, Integer, String, ForeignKey,
    DateTime, Text, Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    amount = Column(Numeric(12, 2), nullable=False)
    # Musbat (+) = to'ldirildi, Manfiy (-) = sarflandi

    type = Column(String(30), nullable=False)
    # top_up | offer_commission | refund

    description = Column(Text)
    related_offer_id = Column(Integer, ForeignKey("offers.id"), nullable=True)
    payment_provider = Column(String(50))     # payme | click | uzcard | manual
    payment_id = Column(String(255))          # To'lov tizimidan qaytgan tashqi ID

    status = Column(String(20), default="success")
    # success | pending | failed

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="transactions")
    offer = relationship("Offer", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction id={self.id} user={self.user_id} amount={self.amount} type={self.type}>"
