from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class PharmacyInventory(Base):
    __tablename__ = "pharmacy_inventory"

    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    medication_name = Column(String, nullable=False)
    is_in_stock = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    pharmacy = relationship("Pharmacy")