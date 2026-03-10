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

# ── REQUEST MODELS ──
class AddPrescriptionRequest(BaseModel):
    medication_name: str
    dosage: str
    frequency: float
    total_quantity: float
    last_refill_date: str
    medication_cost: Optional[float] = None
    next_review_date: Optional[str] = None
    prescription_expiry_date: Optional[str] = None  # when doctor's script expires
    medication_expiry_date: Optional[str] = None    # when physical pills expire

class UpdatePrescriptionRequest(BaseModel):
    total_quantity: Optional[float] = None
    frequency: Optional[float] = None
    medication_cost: Optional[float] = None
    next_review_date: Optional[str] = None
    prescription_expiry_date: Optional[str] = None
    medication_expiry_date: Optional[str] = None

# ── ROUTES ──

# 1. ADD PRESCRIPTION
@router.post("/add")
def add_prescription(
    request: AddPrescriptionRequest,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    # Parse last refill date
    try:
        last_refill = datetime.strptime(request.last_refill_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )

    # Parse next review date
    next_review = None
    if request.next_review_date:
        try:
            next_review = datetime.strptime(request.next_review_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid review date format. Use YYYY-MM-DD"
            )

    # Parse prescription expiry date
    prescription_expiry = None
    if request.prescription_expiry_date:
        try:
            prescription_expiry = datetime.strptime(
                request.prescription_expiry_date, "%Y-%m-%d"
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid prescription expiry date format. Use YYYY-MM-DD"
            )

    # Parse medication expiry date
    medication_expiry = None
    if request.medication_expiry_date:
        try:
            medication_expiry = datetime.strptime(
                request.medication_expiry_date, "%Y-%m-%d"
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid medication expiry date format. Use YYYY-MM-DD"
            )

    # Create prescription
    new_prescription = Prescription(
        patient_id=user.id,
        medication_name=request.medication_name,
        dosage=request.dosage,
        frequency=request.frequency,
        total_quantity=request.total_quantity,
        last_refill_date=last_refill,
        medication_cost=request.medication_cost,
        next_review_date=next_review,
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
            "prescription_expiry_date": new_prescription.prescription_expiry_date,
            "medication_expiry_date": new_prescription.medication_expiry_date,
            "days_until_prescription_expires": new_prescription.days_until_prescription_expires(),
            "days_until_medication_expires": new_prescription.days_until_medication_expires(),
            "document_status": new_prescription.document_status,
            "status": "⚠️ Upload prescription document to activate tracking"
        }
    }


# 2. UPLOAD PRESCRIPTION DOCUMENT
@router.post("/{prescription_id}/upload-document")
def upload_document(
    prescription_id: int,
    token: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    prescription = db.query(Prescription).filter(
        Prescription.id == prescription_id,
        Prescription.patient_id == user.id
    ).first()

    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, PNG, or PDF files allowed"
        )

    # Save file
    file_extension = file.filename.split(".")[-1]
    file_name = f"patient_{user.id}_prescription_{prescription_id}.{file_extension}"
    file_path = os.path.join(UPLOAD_FOLDER, file_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Update prescription status
    prescription.document_path = file_path
    prescription.document_status = PrescriptionStatus.VERIFIED.value
    db.commit()

    return {
        "message": "Prescription document uploaded! Refill tracking is now active. ✅",
        "document_status": prescription.document_status,
        "file_name": file_name
    }


# 3. GET ALL MY PRESCRIPTIONS
@router.get("/my-prescriptions")
def get_my_prescriptions(token: str, db: Session = Depends(get_db)):
    user = get_current_user(token, db)

    prescriptions = db.query(Prescription).filter(
        Prescription.patient_id == user.id,
        Prescription.is_active == True
    ).all()

    if not prescriptions:
        return {"message": "No prescriptions found", "prescriptions": []}

    result = []
    for p in prescriptions:
        days_left = p.days_left()

        # Refill urgency
        if days_left <= 3:
            urgency = "🔴 CRITICAL — Refill immediately!"
        elif days_left <= 5:
            urgency = "🟠 WARNING — Refill soon"
        elif days_left <= 10:
            urgency = "🟡 LOW — Monitor closely"
        else:
            urgency = "🟢 OK — Sufficient supply"

        # Prescription expiry status
        rx_expires_in = p.days_until_prescription_expires()
        if p.is_prescription_expired():
            rx_status = "🔴 EXPIRED — Visit doctor for new prescription"
        elif rx_expires_in <= 7:
            rx_status = f"⚠️ Expires in {rx_expires_in} days — renew soon"
        elif rx_expires_in == 999:
            rx_status = "No expiry set"
        else:
            rx_status = f"✅ Valid — {rx_expires_in} days remaining"

        # Medication expiry status
        med_expires_in = p.days_until_medication_expires()
        if p.is_medication_expired():
            med_status = "🔴 EXPIRED — Do not use this medication"
        elif med_expires_in <= 30:
            med_status = f"⚠️ Expires in {med_expires_in} days"
        elif med_expires_in == 999:
            med_status = "No expiry set"
        else:
            med_status = f"✅ Valid — expires in {med_expires_in} days"

        result.append({
            "id": p.id,
            "medication_name": p.medication_name,
            "dosage": p.dosage,
            "frequency": p.frequency,
            "total_quantity": p.total_quantity,
            "days_left": round(days_left, 1),
            "urgency": urgency,
            "last_refill_date": p.last_refill_date,
            "prescription_expiry_date": p.prescription_expiry_date,
            "prescription_status": rx_status,
            "medication_expiry_date": p.medication_expiry_date,
            "medication_expiry_status": med_status,
            "document_status": p.document_status,
            "medication_cost": p.medication_cost,
            "next_review_date": p.next_review_date
        })

    return {
        "patient": user.full_name,
        "total_prescriptions": len(result),
        "prescriptions": result
    }


# 4. GET SINGLE PRESCRIPTION
@router.get("/{prescription_id}")
def get_prescription(
    prescription_id: int,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    prescription = db.query(Prescription).filter(
        Prescription.id == prescription_id,
        Prescription.patient_id == user.id
    ).first()

    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    days_left = prescription.days_left()

    return {
        "id": prescription.id,
        "medication_name": prescription.medication_name,
        "dosage": prescription.dosage,
        "frequency": prescription.frequency,
        "total_quantity": prescription.total_quantity,
        "days_left": round(days_left, 1),
        "last_refill_date": prescription.last_refill_date,
        "prescription_expiry_date": prescription.prescription_expiry_date,
        "days_until_prescription_expires": prescription.days_until_prescription_expires(),
        "medication_expiry_date": prescription.medication_expiry_date,
        "days_until_medication_expires": prescription.days_until_medication_expires(),
        "is_prescription_expired": prescription.is_prescription_expired(),
        "is_medication_expired": prescription.is_medication_expired(),
        "document_status": prescription.document_status,
        "medication_cost": prescription.medication_cost,
        "next_review_date": prescription.next_review_date,
        "is_active": prescription.is_active
    }


# 5. UPDATE PRESCRIPTION
@router.put("/{prescription_id}/update")
def update_prescription(
    prescription_id: int,
    request: UpdatePrescriptionRequest,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    prescription = db.query(Prescription).filter(
        Prescription.id == prescription_id,
        Prescription.patient_id == user.id
    ).first()

    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    if request.total_quantity is not None:
        prescription.total_quantity = request.total_quantity
    if request.frequency is not None:
        prescription.frequency = request.frequency
    if request.medication_cost is not None:
        prescription.medication_cost = request.medication_cost
    if request.next_review_date is not None:
        prescription.next_review_date = datetime.strptime(
            request.next_review_date, "%Y-%m-%d"
        )
    if request.prescription_expiry_date is not None:
        prescription.prescription_expiry_date = datetime.strptime(
            request.prescription_expiry_date, "%Y-%m-%d"
        )
    if request.medication_expiry_date is not None:
        prescription.medication_expiry_date = datetime.strptime(
            request.medication_expiry_date, "%Y-%m-%d"
        )

    db.commit()

    return {
        "message": "Prescription updated successfully!",
        "days_left": round(prescription.days_left(), 1),
        "prescription_expiry_date": prescription.prescription_expiry_date,
        "medication_expiry_date": prescription.medication_expiry_date
    }


# 6. DELETE PRESCRIPTION
@router.delete("/{prescription_id}/delete")
def delete_prescription(
    prescription_id: int,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    prescription = db.query(Prescription).filter(
        Prescription.id == prescription_id,
        Prescription.patient_id == user.id
    ).first()

    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    prescription.is_active = False
    db.commit()

    return {"message": f"{prescription.medication_name} removed successfully!"}


# 7. PARSE PRESCRIPTION TEXT WITH AI
@router.post("/ai-parse")
def ai_parse_prescription(
    text: str,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    result = parse_prescription_text(text)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=f"AI parsing failed: {result['error']}"
        )

    return {
        "message": "Prescription parsed successfully! ✅",
        "parsed_data": result["data"],
        "note": "Please review and confirm before saving."
    }


# 8. GET MEDICATION INFO
@router.get("/medication-info/{medication_name}")
def medication_info(
    medication_name: str,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    result = get_medication_info(medication_name)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=f"Could not get medication info: {result['error']}"
        )

    return {
        "medication": medication_name,
        "info": result["data"]
    }


# 9. GET ADHERENCE SCORE
@router.get("/adherence/score")
def get_adherence_score(token: str, db: Session = Depends(get_db)):
    from app.services.adherence import calculate_adherence_score
    user = get_current_user(token, db)
    result = calculate_adherence_score(user.id, db)
    return {
        "patient": user.full_name,
        "adherence": result
    }


# 10. TEST ONLY — Manual scheduler trigger
@router.post("/test/run-scheduler")
def run_scheduler_now(token: str, db: Session = Depends(get_db)):
    from app.services.scheduler import run_check_now
    get_current_user(token, db)
    import threading
    thread = threading.Thread(target=run_check_now)
    thread.start()
    return {"message": "Scheduler triggered! Check your terminal for results. 🔍"}