from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum

class PrescriptionStatus(enum.Enum):
    INCOMPLETE = "incomplete"   # no document uploaded yet
    VERIFIED = "verified"       # document uploaded, tracking active
    EXPIRED = "expired"         # prescription has expired

class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    
    # Link to patient
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Medication details
    medication_name = Column(String, nullable=False)
    dosage = Column(String, nullable=False)          # e.g. "5mg"
    frequency = Column(Float, nullable=False)        # e.g. 2.0 (twice daily)
    total_quantity = Column(Float, nullable=False)   # e.g. 60 tablets
    last_refill_date = Column(DateTime, nullable=False)
    
    # Prescription document
    document_path = Column(String, nullable=True)    # file path after upload
    document_status = Column(
        String, 
        default=PrescriptionStatus.INCOMPLETE.value
    )
    
    # Optional
    next_review_date = Column(DateTime, nullable=True)  # clinician review date
    medication_cost = Column(Float, nullable=True)       # cost per refill in kobo
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to user
    patient = relationship("User", backref="prescriptions")

    def days_left(self):
        """Calculate how many days of medication remain"""
        if self.frequency == 0:
            return 0
        return self.total_quantity / self.frequency

    def __repr__(self):
        return f"<Prescription {self.medication_name} - Patient {self.patient_id}>"