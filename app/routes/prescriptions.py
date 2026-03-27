from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.database import get_db
from app.models.prescription import Prescription, PrescriptionStatus
from app.models.user import User
from app.routes.auth import get_current_user
from app.services.gemini import parse_prescription_text, get_medication_info
import os
import shutil

router = APIRouter()

UPLOAD_FOLDER = "uploads/prescriptions"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# -- REQUEST MODELS --
class AddPrescriptionRequest(BaseModel):
    medication_name: str
    dosage: str
    frequency: float
    total_quantity: float
    last_refill_date: str
    medication_cost: Optional[float] = None
    next_review_date: Optional[str] = None
    prescription_issue_date: Optional[str] = None
    prescription_expiry_date: Optional[str] = None
    medication_expiry_date: Optional[str] = None

class UpdatePrescriptionRequest(BaseModel):
    total_quantity: Optional[float] = None
    frequency: Optional[float] = None
    medication_cost: Optional[float] = None
    next_review_date: Optional[str] = None
    prescription_issue_date: Optional[str] = None
    prescription_expiry_date: Optional[str] = None
    medication_expiry_date: Optional[str] = None


# -- HELPER --
def parse_date(date_str: str, field_name: str) -> datetime:
    """Parse a date string or raise a clean HTTP error."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} format. Use YYYY-MM-DD"
        )


# -- ROUTES --

# 1. ADD PRESCRIPTION
@router.post("/add")
def add_prescription(
    request: AddPrescriptionRequest,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    last_refill = parse_date(request.last_refill_date, "last_refill_date")
    next_review = parse_date(request.next_review_date, "next_review_date") if request.next_review_date else None
    prescription_issue = parse_date(request.prescription_issue_date, "prescription_issue_date") if request.prescription_issue_date else None
    prescription_expiry = parse_date(request.prescription_expiry_date, "prescription_expiry_date") if request.prescription_expiry_date else None
    medication_expiry = parse_date(request.medication_expiry_date, "medication_expiry_date") if request.medication_expiry_date else None

    new_prescription = Prescription(
        patient_id=user.id,
        medication_name=request.medication_name,
        dosage=request.dosage,
        frequency=request.frequency,
        total_quantity=request.total_quantity,
        last_refill_date=last_refill,
        medication_cost=request.medication_cost,
        next_review_date=next_review,
        prescription_issue_date=prescription_issue,
        prescription_expiry_date=prescription_expiry,
        medication_expiry_date=medication_expiry,
        document_status=PrescriptionStatus.INCOMPLETE.value
    )

    db.add(new_prescription)
    db.commit()
    db.refresh(new_prescription)

    days_left = new_prescription.days_left()

    return {
        "message": "Prescription added successfully!",
        "prescription": {
            "id": new_prescription.id,
            "medication_name": new_prescription.medication_name,
            "dosage": new_prescription.dosage,
            "frequency": new_prescription.frequency,
            "total_quantity": new_prescription.total_quantity,
            "days_left": round(days_left, 1),
            "last_refill_date": new_prescription.last_refill_date,
            "prescription_issue_date": new_prescription.prescription_issue_date,
            "prescription_expiry_date": new_prescription.prescription_expiry_date,
            "medication_expiry_date": new_prescription.medication_expiry_date,
            "days_until_prescription_expires": new_prescription.days_until_prescription_expires(),
            "days_until_medication_expires": new_prescription.days_until_medication_expires(),
            "document_status": new_prescription.document_status,
            "status": "Upload prescription document to activate tracking"
        }
    }

# Add the rest of your routes here...