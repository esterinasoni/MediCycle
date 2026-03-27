from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    
    # Links
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=False)
    
    # Payment details
    payment_reference = Column(String, nullable=True)
    amount = Column(Float, nullable=False)           # in kobo
    status = Column(String, default="pending")       # pending, success, failed
    
    # Delivery status
    delivery_status = Column(String, default="pending")  # pending, preparing, out_for_delivery, delivered

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    patient = relationship("User", backref="transactions")
    prescription = relationship("Prescription", backref="transactions")

    def __repr__(self):
        return f"<Transaction {self.payment_reference} - {self.status}>"