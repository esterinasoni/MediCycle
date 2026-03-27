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
# from app.services.email import send_otp_email
from app.services.email_simple import send_otp_email
import asyncio

load_dotenv()

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

class UpdateCaregiverRequest(BaseModel):
    caregiver_name: str
    caregiver_phone: str

class UpdateProfileRequest(BaseModel):
    full_name: str = None
    phone_number: str = None
    caregiver_name: str = None
    caregiver_phone: str = None
    address: str = None
    city: str = None
    state: str = None
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
async def register(
    request: RegisterRequest, 
    db: Session = Depends(get_db)
):
    # Check existing user
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    existing_phone = db.query(User).filter(
        User.phone_number == request.phone_number
    ).first()
    if existing_phone:
        raise HTTPException(status_code=400, detail="Phone number already registered")

    # Generate OTP
    otp = str(random.randint(100000, 999999))
    otp_expiry = datetime.utcnow() + timedelta(minutes=10)

    # Create user
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

    # Send OTP via email
    try:
        first_name = request.full_name.split()[0] if request.full_name else None
        await send_otp_email(
            email=request.email,
            otp_code=otp,
            name=first_name
        )
        print(f"[OK] OTP email sent to {request.email}")
    except Exception as e:
        print(f"[X] Failed to send OTP email: {e}")
        # In production, you might want to retry or log this
        # For now, we'll still return success but user won't get email
        raise HTTPException(
            status_code=500,
            detail="Failed to send verification email. Please try again."
        )

    # Return success WITHOUT OTP in response (security)
    return {
        "message": "Registration successful! Please check your email for the verification code.",
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
        raise HTTPException(
            status_code=400,
            detail="OTP has expired. Please register again."
        )

    user.is_verified = True
    user.otp_code = None
    user.otp_expiry = None
    db.commit()

    return {"message": "Account verified successfully! You can now log in."}
@router.post("/resend-otp")
async def resend_otp(
    email: str,
    db: Session = Depends(get_db)
):
    """Resend OTP verification code"""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Account already verified")
    
    # Rate limiting (optional)
    # Check last OTP request time
    if user.last_otp_request:
        time_since_last = datetime.utcnow() - user.last_otp_request
        if time_since_last.total_seconds() < 60:  # 1 minute cooldown
            raise HTTPException(
                status_code=429,
                detail="Please wait 1 minute before requesting another code"
            )
    
    # Generate new OTP
    new_otp = str(random.randint(100000, 999999))
    user.otp_code = new_otp
    user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
    user.last_otp_request = datetime.utcnow()
    db.commit()
    
    # Send email
    try:
        first_name = user.full_name.split()[0] if user.full_name else None
        await send_otp_email(email, new_otp, first_name)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to send verification email. Please try again."
        )
    
    return {"message": "New verification code sent to your email"}

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
            "caregiver_name": user.caregiver_name,
            "caregiver_phone": user.caregiver_phone,
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
        "message": "Location updated successfully! [OK]",
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
        "created_at": user.created_at,
        "has_caregiver": bool(user.caregiver_phone),
        "has_card": bool(user.interswitch_token),
        "has_delivery_address": bool(user.address and user.city)
    }

# 6. UPDATE CAREGIVER
@router.put("/update-caregiver")
def update_caregiver(
    request: UpdateCaregiverRequest,
    token: str,
    db: Session = Depends(get_db)
):
    """Add or update caregiver details (Req 1.1, 4.3, 7.1)"""
    user = get_current_user(token, db)

    user.caregiver_name = request.caregiver_name
    user.caregiver_phone = request.caregiver_phone
    db.commit()

    return {
        "message": f"Caregiver {request.caregiver_name} added successfully! [OK]",
        "caregiver": {
            "name": user.caregiver_name,
            "phone": mask_phone(user.caregiver_phone)
        }
    }

# 7. UPDATE FULL PROFILE
@router.put("/update-profile")
def update_profile(
    request: UpdateProfileRequest,
    token: str,
    db: Session = Depends(get_db)
):
    """Update any profile field"""
    user = get_current_user(token, db)

    if request.full_name is not None:
        user.full_name = request.full_name
    if request.phone_number is not None:
        # Check phone not taken by another user
        existing = db.query(User).filter(
            User.phone_number == request.phone_number,
            User.id != user.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Phone number already in use")
        user.phone_number = request.phone_number
    if request.caregiver_name is not None:
        user.caregiver_name = request.caregiver_name
    if request.caregiver_phone is not None:
        user.caregiver_phone = request.caregiver_phone
    if request.address is not None:
        user.address = request.address
    if request.city is not None:
        user.city = request.city
    if request.state is not None:
        user.state = request.state
    if request.landmark is not None:
        user.landmark = request.landmark

    db.commit()

    return {
        "message": "Profile updated successfully! [OK]",
        "profile": {
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "caregiver_name": user.caregiver_name,
            "caregiver_phone": mask_phone(user.caregiver_phone) if user.caregiver_phone else None,
            "address": user.address,
            "city": user.city,
            "state": user.state,
            "landmark": user.landmark
        }
    }

# ── HELPER ──
def mask_phone(phone: str) -> str:
    if not phone or len(phone) < 7:
        return phone
    return phone[:3] + "****" + phone[-3:]