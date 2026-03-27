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
    prescription_issue_date: Optional[str] = None    # when doctor issued script
    prescription_expiry_date: Optional[str] = None   # when doctor's script expires
    medication_expiry_date: Optional[str] = None     # when physical pills expire

class UpdatePrescriptionRequest(BaseModel):
    total_quantity: Optional[float] = None
    frequency: Optional[float] = None
    medication_cost: Optional[float] = None
    next_review_date: Optional[str] = None
    prescription_issue_date: Optional[str] = None
    prescription_expiry_date: Optional[str] = None
    medication_expiry_date: Optional[str] = None


# ── HELPER ──
def parse_date(date_str: str, field_name: str) -> datetime:
    """Parse a date string or raise a clean HTTP error."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} format. Use YYYY-MM-DD"
        )


# ── ROUTES ──

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

    allowed_types = ["image/jpeg", "image/png", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, PNG, or PDF files allowed"
        )

    file_extension = file.filename.split(".")[-1]
    file_name = f"patient_{user.id}_prescription_{prescription_id}.{file_extension}"
    file_path = os.path.join(UPLOAD_FOLDER, file_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

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
            "prescription_issue_date": p.prescription_issue_date,
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


# Keep this static route above `/{prescription_id}` so it doesn't get parsed as an int.
@router.get("/sample-medications")
def get_sample_medications(db: Session = Depends(get_db)):
    return build_sample_medications(db)


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
        "prescription_issue_date": prescription.prescription_issue_date,
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
        prescription.next_review_date = parse_date(request.next_review_date, "next_review_date")
    if request.prescription_issue_date is not None:
        prescription.prescription_issue_date = parse_date(request.prescription_issue_date, "prescription_issue_date")
    if request.prescription_expiry_date is not None:
        prescription.prescription_expiry_date = parse_date(request.prescription_expiry_date, "prescription_expiry_date")
    if request.medication_expiry_date is not None:
        prescription.medication_expiry_date = parse_date(request.medication_expiry_date, "medication_expiry_date")

    db.commit()

    return {
        "message": "Prescription updated successfully!",
        "days_left": round(prescription.days_left(), 1),
        "prescription_issue_date": prescription.prescription_issue_date,
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
# 7a. PARSE PRESCRIPTION FROM TEXT
@router.post("/ai-parse-text")
def ai_parse_prescription_text(
    text: str,
    token: str,
    db: Session = Depends(get_db)
):
    """Parse prescription from typed text"""
    user = get_current_user(token, db)
    
    from app.services.gemini import parse_prescription_text
    
    result = parse_prescription_text(text)
    
    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=f"AI parsing failed: {result['error']}"
        )
    
    return {
        "success": True,
        "message": "Prescription parsed successfully! ✅",
        "extracted_data": result["data"],
        "note": "Please review and confirm before saving."
    }


# 7b. PARSE PRESCRIPTION FROM FILE (Image/PDF)
@router.post("/ai-parse-file")
async def ai_parse_prescription_file(
    token: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Parse prescription from uploaded image or PDF"""
    user = get_current_user(token, db)
    
    from app.services.gemini import parse_prescription_image, parse_prescription_text
    import tempfile
    import os
    import PyPDF2
    from io import BytesIO
    
    try:
        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/jpg", "application/pdf"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: JPG, PNG, PDF. Got: {file.content_type}"
            )
        
        # Read file content
        content = await file.read()
        
        # Validate file size (max 10MB)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="File size must be less than 10MB"
            )
        
        # Process based on file type
        if file.content_type.startswith('image/'):
            # Save image temporarily
            suffix = f".{file.filename.split('.')[-1]}"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_file.write(content)
                tmp_path = tmp_file.name
            
            try:
                result = parse_prescription_image(tmp_path)
            finally:
                os.unlink(tmp_path)
                
        else:  # PDF
            pdf_reader = PyPDF2.PdfReader(BytesIO(content))
            text = ""
            for page in pdf_reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            
            if not text.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Could not extract text from PDF. Please ensure it's not a scanned image."
                )
            
            result = parse_prescription_text(text)
        
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=f"AI parsing failed: {result.get('error', 'Unknown error')}"
            )
        
        extracted_data = result.get("data", {})
        
        return {
            "success": True,
            "message": "Prescription parsed successfully! ✅",
            "extracted_data": {
                "medication_name": extracted_data.get("medication_name"),
                "dosage": extracted_data.get("dosage"),
                "frequency": extracted_data.get("frequency"),
                "total_quantity": extracted_data.get("total_quantity"),
                "duration_days": extracted_data.get("duration_days"),
                "instructions": extracted_data.get("instructions"),
                "doctor_name": extracted_data.get("doctor_name"),
                "prescription_date": extracted_data.get("prescription_date")
            },
            "note": "Please review the extracted information and confirm before saving."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"AI Parse Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse prescription: {str(e)}")

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
def build_sample_medications(db: Session):
    """
    Get random active prescriptions from real users (for demo)
    """
    # Get prescriptions from real users that have been added
    prescriptions = db.query(Prescription).filter(
        Prescription.is_active == True,
        Prescription.document_status == "verified"
    ).limit(10).all()
    
    if prescriptions:
        sample_medications = []
        for p in prescriptions:
            days_left = p.days_left()
            if days_left <= 3:
                status = "critical"
                tag = "🔴"
                message = "Auto-charging"
                tag_class = "tag-red"
            elif days_left <= 5:
                status = "warning"
                tag = "⚠️"
                message = f"{int(days_left)} days"
                tag_class = "tag-yellow"
            else:
                status = "good"
                tag = "✅"
                message = f"{int(days_left)} days"
                tag_class = "tag-green"
            
            sample_medications.append({
                "name": f"{p.medication_name} {p.dosage}",
                "dosage": p.dosage,
                "days_left": round(days_left, 1),
                "status": status,
                "tag": tag,
                "message": message,
                "tag_class": tag_class,
                "medication_name": p.medication_name
            })
        
        # Shuffle and return random 3
        import random
        random.shuffle(sample_medications)
        return {"medications": sample_medications[:3]}
    else:
        # Fallback to static samples
        return get_static_samples()
def get_static_samples():
    """
    Static sample medications for when no real prescriptions exist yet.
    """
    static_medications = [
        {
            "name": "Amlodipine 5mg",
            "dosage": "5mg",
            "days_left": 18,
            "status": "good",
            "tag": "[OK]",
            "message": "18 days",
            "tag_class": "tag-green",
            "medication_name": "Amlodipine",
            "frequency": 1,
            "total_quantity": 18
        },
        {
            "name": "Metformin 500mg",
            "dosage": "500mg",
            "days_left": 4,
            "status": "warning",
            "tag": "[WARN]",
            "message": "4 days",
            "tag_class": "tag-yellow",
            "medication_name": "Metformin",
            "frequency": 2,
            "total_quantity": 8
        },
        {
            "name": "Lisinopril 10mg",
            "dosage": "10mg",
            "days_left": 2,
            "status": "critical",
            "tag": "[!]",
            "message": "Auto-charging",
            "tag_class": "tag-red",
            "medication_name": "Lisinopril",
            "frequency": 1,
            "total_quantity": 2
        },
        {
            "name": "Losartan 50mg",
            "dosage": "50mg",
            "days_left": 25,
            "status": "good",
            "tag": "[OK]",
            "message": "25 days",
            "tag_class": "tag-green",
            "medication_name": "Losartan",
            "frequency": 1,
            "total_quantity": 25
        },
        {
            "name": "Atorvastatin 20mg",
            "dosage": "20mg",
            "days_left": 12,
            "status": "good",
            "tag": "[OK]",
            "message": "12 days",
            "tag_class": "tag-green",
            "medication_name": "Atorvastatin",
            "frequency": 1,
            "total_quantity": 12
        }
    ]
    
    # Return 3 random static medications
    import random
    random.shuffle(static_medications)
    return {
        "medications": static_medications[:3],
        "source": "static_samples",
        "total_available": len(static_medications)
    }
