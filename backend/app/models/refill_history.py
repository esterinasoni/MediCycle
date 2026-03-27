from sqlalchemy import Column, Integer, Float, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class RefillHistory(Base):
    __tablename__ = "refill_history"

    id = Column(Integer, primary_key=True, index=True)
    
    # Links
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=False)
    
    # Adherence tracking
    expected_refill_date = Column(Date, nullable=False)  # when they SHOULD refill
    actual_refill_date = Column(Date, nullable=False)    # when they ACTUALLY refilled
    days_variance = Column(Integer, nullable=False)      # positive = late, negative = early

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    patient = relationship("User", backref="refill_history")
    prescription = relationship("Prescription", backref="refill_history")

    def __repr__(self):
        return f"<RefillHistory Patient {self.patient_id} - Variance: {self.days_variance} days>"