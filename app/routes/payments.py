from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.models.transaction import Transaction
from app.models.prescription import Prescription
from app.models.user import User
from app.routes.auth import get_current_user
from app.services.interswitch import tokenize_card, charge_patient, verify_transaction, mock_charge_success
import os

router = APIRouter()

USE_MOCK = os.getenv("USE_MOCK_PAYMENTS", "true").lower() == "true"

# ── REQUEST MODELS ──
class TokenizeCardRequest(BaseModel):
    auth_data: str  # encrypted card data from frontend

class ChargeRequest(BaseModel):
    prescription_id: int

# ── ROUTES ──

# 1. TOKENIZE CARD (patient saves card once)
@router.post("/save-card")
def save_card(
    request: TokenizeCardRequest,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    if USE_MOCK:
        # Mock tokenization for demo
        user.interswitch_token = f"mock_tok_{user.id}_medicycle"
        user.token_expiry_date = "2612"
        db.commit()
        return {
            "message": "Card saved successfully! ✅",
            "mode": "SANDBOX",
            "card_masked": "**** **** **** 1234",
            "token_saved": True
        }

    # Real tokenization
    result = tokenize_card(request.auth_data)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    # Save token to user — NEVER save raw card number
    user.interswitch_token = result["token"]
    user.token_expiry_date = result["token_expiry"]
    db.commit()

    return {
        "message": "Card saved successfully! ✅",
        "token_saved": True
    }


# 2. CHARGE PATIENT FOR A PRESCRIPTION REFILL
@router.post("/charge-refill")
def charge_refill(
    request: ChargeRequest,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    # Check patient has a saved card
    if not user.interswitch_token:
        raise HTTPException(
            status_code=400,
            detail="No card saved. Please save a card first via /payments/save-card"
        )

    # Get prescription
    prescription = db.query(Prescription).filter(
        Prescription.id == request.prescription_id,
        Prescription.patient_id == user.id,
        Prescription.is_active == True
    ).first()

    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    if not prescription.medication_cost:
        raise HTTPException(
            status_code=400,
            detail="Medication cost not set for this prescription"
        )

    amount_kobo = int(prescription.medication_cost)

    # Create pending transaction record
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

    # Charge patient
    if USE_MOCK:
        result = mock_charge_success(amount_kobo, prescription.id)
    else:
        result = charge_patient(
            token=user.interswitch_token,
            token_expiry=user.token_expiry_date,
            amount_kobo=amount_kobo,
            customer_id=f"PAT-{user.id:04d}",
            prescription_id=prescription.id
        )

    if not result["success"]:
        # Update transaction as failed
        transaction.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail=result["error"])

    # Update transaction as successful
    transaction.status = "success"
    transaction.payment_reference = result["reference"]
    transaction.delivery_status = "preparing"

    # Update prescription last refill date
    prescription.last_refill_date = datetime.utcnow()
    prescription.total_quantity = prescription.total_quantity  # reset after refill

    db.commit()

    return {
        "message": f"Payment successful! ₦{result['amount_naira']:,.2f} charged. 💊",
        "transaction_id": transaction.id,
        "reference": result["reference"],
        "amount": f"₦{result['amount_naira']:,.2f}",
        "delivery_status": "preparing",
        "prescription": prescription.medication_name,
        "mode": result.get("mode", "LIVE")
    }


# 3. VERIFY A TRANSACTION
@router.get("/verify/{reference}")
def verify_payment(
    reference: str,
    token: str,
    db: Session = Depends(get_db)
):
    user = get_current_user(token, db)

    # Find transaction
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


# 4. GET PAYMENT HISTORY
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

    return {
        "total_transactions": len(result),
        "transactions": result
    }


# 5. UPDATE DELIVERY STATUS (called by pharmacy/admin)
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


