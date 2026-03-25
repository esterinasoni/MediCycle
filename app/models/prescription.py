from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Enum
from sqlalchemy.sql import func
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
import enum


class PrescriptionStatus(enum.Enum):
    INCOMPLETE = "incomplete"
    VERIFIED = "verified"
    EXPIRED = "expired"


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Medication details
    medication_name = Column(String, nullable=False)
    dosage = Column(String, nullable=False)
    frequency = Column(Float, nullable=False)
    total_quantity = Column(Float, nullable=False)

    # Refill tracking
    last_refill_date = Column(DateTime, nullable=False)

    # Prescription document details
    document_path = Column(String, nullable=True)
    document_status = Column(String, default=PrescriptionStatus.INCOMPLETE.value)

    # Dates
    prescription_issue_date = Column(DateTime, nullable=True)    # when doctor issued script
    prescription_expiry_date = Column(DateTime, nullable=True)   # when doctor's script expires
    medication_expiry_date = Column(DateTime, nullable=True)     # when physical pills expire
    next_review_date = Column(DateTime, nullable=True)           # next clinician visit

    # Cost
    medication_cost = Column(Float, nullable=True)  # in kobo

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    patient = relationship("User", backref="prescriptions")

    def days_left(self) -> float:
        """Calculate how many days of medication remain."""
        if self.frequency <= 0:
            return 0
        return self.total_quantity / self.frequency

    def is_prescription_expired(self) -> bool:
        """Check if the doctor's prescription script has expired."""
        if not self.prescription_expiry_date:
            return False
        return datetime.utcnow() > self.prescription_expiry_date

    def is_medication_expired(self) -> bool:
        """Check if the physical medication has expired."""
        if not self.medication_expiry_date:
            return False
        return datetime.utcnow() > self.medication_expiry_date

    def days_until_prescription_expires(self) -> float:
        """Days until doctor's script expires."""
        if not self.prescription_expiry_date:
            return 999
        delta = self.prescription_expiry_date - datetime.utcnow()
        return max(0, delta.days)

    def days_until_medication_expires(self) -> float:
        """Days until physical medication expires."""
        if not self.medication_expiry_date:
            return 999
        delta = self.medication_expiry_date - datetime.utcnow()
        return max(0, delta.days)

    def __repr__(self):
        return f"<Prescription {self.medication_name} - Patient {self.patient_id}>"