from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from app.database import get_db
from app.models.user import User
from dotenv import load_dotenv
import os
import logging

load_dotenv()

router = APIRouter()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# -- REQUEST MODELS --
class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str
    password: str
    caregiver_name: str = None
    caregiver_phone: str = None
    address: str = None
    city: str = None
    state: str = None
    landmark: str = None

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

# -- HELPER FUNCTIONS --
def hash_password(password: str) -> str:
    """Hash password with bcrypt, truncating to 72 bytes if needed"""
    try:
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            password = password_bytes[:72].decode('utf-8', errors='ignore')
        return pwd_context.hash(password)
    except Exception as e:
        logger.error(f"Error hashing password: {e}")
        raise HTTPException(status_code=500, detail="Error processing password")

def verify_password(plain: str, hashed: str) -> bool:
    """Verify password with bcrypt, truncating if needed"""
    try:
        plain_bytes = plain.encode('utf-8')
        if len(plain_bytes) > 72:
            plain = plain_bytes[:72].decode('utf-8', errors='ignore')
        return pwd_context.verify(plain, hashed)
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# -- GET CURRENT USER --
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

# -- ROUTES --

@router.post("/register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    try:
        logger.info(f"Registration attempt for {request.email}")
        
        # Check existing email
        existing = db.query(User).filter(User.email == request.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Check existing phone
        existing_phone = db.query(User).filter(
            User.phone_number == request.phone_number
        ).first()
        if existing_phone:
            raise HTTPException(status_code=400, detail="Phone number already registered")

        # Hash password
        hashed_password = hash_password(request.password)

        # Create user - auto-verified (no OTP)
        new_user = User(
            full_name=request.full_name,
            email=request.email,
            phone_number=request.phone_number,
            hashed_password=hashed_password,
            caregiver_name=request.caregiver_name,
            caregiver_phone=request.caregiver_phone,
            address=request.address,
            city=request.city,
            state=request.state,
            landmark=request.landmark,
            is_verified=True  # Auto-verified
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"User created and auto-verified: {request.email}")

        return {
            "message": "Registration successful! You can now log in.",
            "email": new_user.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

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
        "has_caregiver": bool(user.caregiver_phone),
        "has_card": bool(user.interswitch_token) if hasattr(user, 'interswitch_token') else False,
        "has_delivery_address": bool(user.address and user.city)
    }

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

@router.put("/update-caregiver")
def update_caregiver(
    request: UpdateCaregiverRequest,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    user.caregiver_name = request.caregiver_name
    user.caregiver_phone = request.caregiver_phone
    db.commit()

    return {
        "message": f"Caregiver {request.caregiver_name} added successfully!",
        "caregiver": {
            "name": user.caregiver_name,
            "phone": mask_phone(user.caregiver_phone)
        }
    }

@router.put("/update-profile")
def update_profile(
    request: UpdateProfileRequest,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    if request.full_name is not None:
        user.full_name = request.full_name
    if request.phone_number is not None:
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
        "message": "Profile updated successfully!",
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

def mask_phone(phone: str) -> str:
    if not phone or len(phone) < 7:
        return phone
    return phone[:3] + "****" + phone[-3:]

@router.get("/health")
def auth_health():
    return {"status": "ok", "service": "auth"}
