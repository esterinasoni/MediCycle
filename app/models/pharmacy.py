from sqlalchemy import Column, Integer, String, Boolean, Float
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from app.database import Base

class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    zone = Column(String, nullable=False)       # e.g. "Victoria Island", "Westlands"
    address = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Pharmacy {self.name} - {self.city}>"