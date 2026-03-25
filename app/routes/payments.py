from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.models.transaction import Transaction
from app.models.prescription import Prescription
from app.models.user import User
from app.routes.auth import get_current_user
from app.services.interswitch import (
    tokenize_card, charge_patient, verify_transaction, mock_charge_success
)
from app.services.scheduler import route_to_pharmacy, send_sms
import os

router = APIRouter()

# Single source of truth for mock flag
USE_MOCK = os.getenv("USE_MOCK_PAYMENTS", "true").lower() == "true"


# ── REQUEST MODELS ──
class TokenizeCardRequest(BaseModel):
    auth_data: str

class ChargeRequest(BaseModel):
    prescription_id: int


# ── HELPER ──
def _do_charge(
    user_token: str,
    token_expiry: str,
    amount_kobo: int,
    customer_id: str,
    prescription_id: int
) -> dict:
    """Single charge helper — respects USE_MOCK flag."""
    if USE_MOCK:
        return mock_charge_success(amount_kobo, prescription_id)
    return charge_patient(
        token=user_token,
        token_expiry=token_expiry,
        amount_kobo=amount_kobo,
        customer_id=customer_id,
        prescription_id=prescription_id
    )


# ── 1. TOKENIZE CARD ──
@router.post("/save-card")
def save_card(
    request: TokenizeCardRequest,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    if USE_MOCK:
        user.interswitch_token = f"mock_tok_{user.id}_medicycle"
        user.token_expiry_date = "2612"
        db.commit()
        return {
            "message": "Card saved successfully! ✅",
            "mode": "SANDBOX",
            "card_masked": "**** **** **** 1234",
            "token_saved": True
        }

    result = tokenize_card(request.auth_data)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    user.interswitch_token = result["token"]
    user.token_expiry_date = result["token_expiry"]
    db.commit()

    return {"message": "Card saved successfully! ✅", "token_saved": True}


# ── 2. CHARGE PATIENT (self) ──
@router.post("/charge-refill")
def charge_refill(
    request: ChargeRequest,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    if not user.interswitch_token:
        raise HTTPException(
            status_code=400,
            detail="No card saved. Please save a card first via /payments/save-card"
        )

    prescription = db.query(Prescription).filter(
        Prescription.id == request.prescription_id,
        Prescription.patient_id == user.id,
        Prescription.is_active == True
    ).first()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if not prescription.medication_cost:
        raise HTTPException(status_code=400, detail="Medication cost not set")

    amount_kobo = int(prescription.medication_cost)

    transaction = Transaction(
        patient_id=user.id,
        prescription_id=prescription.id,
        amount=amount_kobo,
        status="pending",
        delivery_status="pending"
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    result = _do_charge(
        user_token=user.interswitch_token,
        token_expiry=user.token_expiry_date,
        amount_kobo=amount_kobo,
        customer_id=f"PAT-{user.id:04d}",
        prescription_id=prescription.id
    )

    if not result["success"]:
        transaction.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail=result["error"])

    transaction.status = "success"
    transaction.payment_reference = result["reference"]
    transaction.delivery_status = "preparing"
    prescription.last_refill_date = datetime.utcnow()
    db.commit()

    return {
        "message": f"Payment successful! ₦{result['amount_naira']:,.2f} charged. 💊",
        "transaction_id": transaction.id,
        "reference": result["reference"],
        "amount": f"₦{result['amount_naira']:,.2f}",
        "delivery_status": "preparing",
        "prescription": prescription.medication_name,
        "mode": "SANDBOX" if USE_MOCK else "LIVE"
    }


# ── 3. VERIFY TRANSACTION ──
@router.get("/verify/{reference}")
def verify_payment(
    reference: str,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    transaction = db.query(Transaction).filter(
        Transaction.payment_reference == reference,
        Transaction.patient_id == user.id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if USE_MOCK:
        return {
            "verified": True,
            "status": transaction.status,
            "amount": transaction.amount / 100,
            "reference": reference,
            "mode": "SANDBOX"
        }

    result = verify_transaction(reference)
    if result["verified"]:
        transaction.status = "success"
        db.commit()

    return {
        "verified": result["verified"],
        "status": transaction.status,
        "reference": reference
    }


# ── 4. PAYMENT HISTORY ──
@router.get("/history")
def payment_history(token: str, db: Session = Depends(get_db)):
    user = get_current_user(token, db)

    transactions = db.query(Transaction).filter(
        Transaction.patient_id == user.id
    ).order_by(Transaction.created_at.desc()).all()

    if not transactions:
        return {"message": "No transactions yet", "transactions": []}

    result = []
    for t in transactions:
        prescription = db.query(Prescription).filter(
            Prescription.id == t.prescription_id
        ).first()
        result.append({
            "id": t.id,
            "medication": prescription.medication_name if prescription else "Unknown",
            "amount": f"₦{t.amount / 100:,.2f}",
            "status": t.status,
            "delivery_status": t.delivery_status,
            "reference": t.payment_reference,
            "date": t.created_at
        })

    return {"total_transactions": len(result), "transactions": result}


# ── 5. UPDATE DELIVERY STATUS ──
@router.put("/delivery/{transaction_id}/status")
def update_delivery(
    transaction_id: int,
    status: str,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    valid_statuses = ["pending", "preparing", "out_for_delivery", "delivered"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Choose from: {valid_statuses}"
        )

    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.patient_id == user.id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction.delivery_status = status
    db.commit()

    return {
        "message": f"Delivery status updated to: {status} ✅",
        "transaction_id": transaction_id,
        "delivery_status": status
    }


# ── 6. CAREGIVER INFO (public) ──
@router.get("/caregiver-info")
def get_caregiver_info(
    prescription_id: int,
    patient_id: int,
    db: Session = Depends(get_db)
):
    prescription = db.query(Prescription).filter(
        Prescription.id == prescription_id,
        Prescription.patient_id == patient_id,
        Prescription.is_active == True
    ).first()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    patient = db.query(User).filter(User.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    return {
        "patient": {
            "full_name": patient.full_name,
            "city": patient.city,
            "state": patient.state
        },
        "prescription": {
            "medication_name": prescription.medication_name,
            "dosage": prescription.dosage,
            "medication_cost": prescription.medication_cost,
            "days_left": round(prescription.days_left(), 1)
        }
    }


# ── 7. CAREGIVER CHARGE ──
@router.post("/caregiver-charge")
def caregiver_charge(
    prescription_id: int,
    patient_id: int,
    caregiver_name: str,
    card_data: str,
    db: Session = Depends(get_db)
):
    prescription = db.query(Prescription).filter(
        Prescription.id == prescription_id,
        Prescription.patient_id == patient_id
    ).first()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    patient = db.query(User).filter(User.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if not prescription.medication_cost:
        raise HTTPException(status_code=400, detail="No cost set for this medication")

    amount_kobo = int(prescription.medication_cost)

    transaction = Transaction(
        patient_id=patient_id,
        prescription_id=prescription_id,
        amount=amount_kobo,
        status="pending",
        delivery_status="pending"
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    # ✅ Now respects USE_MOCK — was always calling mock before
    result = _do_charge(
        user_token=card_data,       # caregiver provides card data directly
        token_expiry="",            # handled inside charge_patient for live
        amount_kobo=amount_kobo,
        customer_id=f"CAREGIVER-{patient_id}",
        prescription_id=prescription_id
    )

    if not result["success"]:
        transaction.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail="Payment failed")

    transaction.status = "success"
    transaction.payment_reference = result["reference"]
    transaction.delivery_status = "preparing"
    prescription.last_refill_date = datetime.utcnow()
    if prescription.frequency and prescription.frequency > 0:
        prescription.total_quantity = prescription.frequency * 30
    db.commit()

    send_sms(
        patient.phone_number,
        f"✅ Great news! {caregiver_name} has paid for your {prescription.medication_name} refill. "
        f"Your 30-day supply is on the way! 💊"
    )
    route_to_pharmacy(prescription, patient, transaction, db)

    return {
        "message": "Payment successful! Refill authorized.",
        "reference": result["reference"],
        "amount_naira": result["amount_naira"],
        "caregiver": caregiver_name,
        "mode": "SANDBOX" if USE_MOCK else "LIVE"
    }


# ── 8. MANUAL REFILL REQUEST ──
@router.post("/request-refill/{prescription_id}")
def request_refill(
    prescription_id: int,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    prescription = db.query(Prescription).filter(
        Prescription.id == prescription_id,
        Prescription.patient_id == user.id,
        Prescription.is_active == True
    ).first()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    if not user.interswitch_token:
        raise HTTPException(status_code=400, detail="No card saved.")
    if not prescription.medication_cost:
        raise HTTPException(status_code=400, detail="No cost set for this medication.")
    if prescription.is_prescription_expired():
        raise HTTPException(status_code=400, detail="Prescription expired. Please visit your doctor.")

    amount_kobo = int(prescription.medication_cost)

    transaction = Transaction(
        patient_id=user.id,
        prescription_id=prescription_id,
        amount=amount_kobo,
        status="pending",
        delivery_status="pending"
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    result = _do_charge(
        user_token=user.interswitch_token,
        token_expiry=user.token_expiry_date,
        amount_kobo=amount_kobo,
        customer_id=f"PAT-{user.id:04d}",
        prescription_id=prescription_id
    )

    if not result["success"]:
        transaction.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail=f"Payment failed: {result.get('error')}")

    transaction.status = "success"
    transaction.payment_reference = result["reference"]
    transaction.delivery_status = "preparing"
    prescription.last_refill_date = datetime.utcnow()
    if prescription.frequency and prescription.frequency > 0:
        prescription.total_quantity = prescription.frequency * 30
    db.commit()

    send_sms(
        user.phone_number,
        f"✅ Refill confirmed for {prescription.medication_name}! "
        f"₦{result['amount_naira']:,.0f} charged. Your order is being prepared. 💊"
    )
    route_to_pharmacy(prescription, user, transaction, db)

    return {
        "message": "Refill requested successfully! ✅",
        "prescription": prescription.medication_name,
        "amount_charged": f"₦{result['amount_naira']:,.0f}",
        "reference": result["reference"],
        "transaction_id": transaction.id,
        "delivery_status": "preparing",
        "track_url": f"medicycle.app/track/{transaction.id}"
    }