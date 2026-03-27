from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone_number = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # OTP verification
    otp_code = Column(String, nullable=True)
    otp_expiry = Column(DateTime, nullable=True)
    is_verified = Column(Boolean, default=False)

    # Caregiver (optional)
    caregiver_name = Column(String, nullable=True)
    caregiver_phone = Column(String, nullable=True)

    # Delivery location
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    landmark = Column(String, nullable=True)

    # Interswitch token -- NEVER store raw card number
    interswitch_token = Column(String, nullable=True)
    token_expiry_date = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<User {self.email}>"