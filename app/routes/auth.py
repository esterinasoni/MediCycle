from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from app.database import get_db
from app.models.user import User
from dotenv import load_dotenv
import os
import random

load_dotenv()

router = APIRouter()

# Password encryption
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# ── REQUEST MODELS ──
class RegisterRequest(BaseModel):
    full_name: str
    email: str
    phone_number: str
    password: str
    caregiver_name: str = None
    caregiver_phone: str = None
    address: str = None
    city: str = None
    state: str = None
    landmark: str = None

class VerifyOTPRequest(BaseModel):
    email: str
    otp_code: str

class LoginRequest(BaseModel):
    email: str
    password: str

class UpdateLocationRequest(BaseModel):
    address: str
    city: str
    state: str
    landmark: str = None

# ── HELPER FUNCTIONS ──
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str):
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def generate_otp():
    return str(random.randint(100000, 999999))

# ── GET CURRENT USER (reusable) ──
def get_current_user(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# ── ROUTES ──

# 1. REGISTER
@router.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):

    # Check if email already exists
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check if phone already exists
    existing_phone = db.query(User).filter(
        User.phone_number == request.phone_number
    ).first()
    if existing_phone:
        raise HTTPException(status_code=400, detail="Phone number already registered")

    # Generate OTP
    otp = generate_otp()
    otp_expiry = datetime.utcnow() + timedelta(minutes=10)

    # Create new user
    new_user = User(
        full_name=request.full_name,
        email=request.email,
        phone_number=request.phone_number,
        hashed_password=hash_password(request.password),
        caregiver_name=request.caregiver_name,
        caregiver_phone=request.caregiver_phone,
        address=request.address,
        city=request.city,
        state=request.state,
        landmark=request.landmark,
        otp_code=otp,
        otp_expiry=otp_expiry,
        is_verified=False
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # In production: send OTP via SMS
    # For hackathon demo: return OTP in response
    return {
        "message": "Registration successful! Please verify your OTP.",
        "otp": otp,  # ← remove in production, send via SMS
        "email": new_user.email
    }

# 2. VERIFY OTP
@router.post("/verify-otp")
def verify_otp(request: VerifyOTPRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_verified:
        raise HTTPException(status_code=400, detail="Account already verified")

    if user.otp_code != request.otp_code:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if datetime.utcnow() > user.otp_expiry:
        raise HTTPException(status_code=400, detail="OTP has expired. Please register again.")

    user.is_verified = True
    user.otp_code = None
    user.otp_expiry = None
    db.commit()

    return {"message": "Account verified successfully! You can now log in."}

# 3. LOGIN
@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_verified:
        raise HTTPException(status_code=401, detail="Please verify your OTP first")

    token = create_access_token({"sub": str(user.id), "email": user.email})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "address": user.address,
            "city": user.city,
            "state": user.state,
            "landmark": user.landmark
        }
    }

# 4. UPDATE LOCATION
@router.put("/update-location")
def update_location(
    request: UpdateLocationRequest,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    user.address = request.address
    user.city = request.city
    user.state = request.state
    user.landmark = request.landmark
    db.commit()

    return {
        "message": "Location updated successfully!",
        "delivery_address": {
            "address": user.address,
            "city": user.city,
            "state": user.state,
            "landmark": user.landmark
        }
    }

# 5. GET PROFILE
@router.get("/profile")
def get_profile(token: str, db: Session = Depends(get_db)):
    user = get_current_user(token, db)

    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "caregiver_name": user.caregiver_name,
        "caregiver_phone": user.caregiver_phone,
        "address": user.address,
        "city": user.city,
        "state": user.state,
        "landmark": user.landmark,
        "is_verified": user.is_verified,
        "created_at": user.created_at
    }