from datetime import datetime
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.prescription import Prescription
from app.models.transaction import Transaction
from app.models.user import User
from app.routes.auth import get_current_user
from app.services.interswitch import (
    charge_patient,
    mock_charge_success,
    tokenize_card,
    verify_transaction,
)
from app.services.scheduler import route_to_pharmacy, send_sms

router = APIRouter()

USE_MOCK = os.getenv("USE_MOCK_PAYMENTS", "true").lower() == "true"


class TokenizeCardRequest(BaseModel):
    auth_data: Optional[str] = None
    transaction_ref: Optional[str] = None
    amount: Optional[float] = None
    email: Optional[str] = None


class ChargeRequest(BaseModel):
    prescription_id: int


class CaregiverChargeRequest(BaseModel):
    prescription_id: int
    patient_id: int
    caregiver_name: str
    card_data: str


def _do_charge(
    user_token: str,
    token_expiry: str,
    amount_kobo: int,
    customer_id: str,
    prescription_id: int,
) -> dict:
    if USE_MOCK:
        return mock_charge_success(amount_kobo, prescription_id)
    return charge_patient(
        token=user_token,
        token_expiry=token_expiry,
        amount_kobo=amount_kobo,
        customer_id=customer_id,
        prescription_id=prescription_id,
    )


@router.post("/save-card")
def save_card(
    request: TokenizeCardRequest,
    token: str,
    db: Session = Depends(get_db),
):
    user = get_current_user(token, db)

    # Frontend completes checkout first and then posts a transaction reference.
    # Accept that flow directly so frontend and backend stay in sync.
    if USE_MOCK or request.transaction_ref:
        ref_suffix = request.transaction_ref or f"user_{user.id}"
        user.interswitch_token = f"mock_tok_{user.id}_{ref_suffix}"
        user.token_expiry_date = "2612"
        db.commit()
        return {
            "message": "Card saved successfully! [OK]",
            "mode": "SANDBOX" if USE_MOCK else "PENDING_VERIFICATION",
            "card_masked": "**** **** **** 1234",
            "token_saved": True,
            "reference": request.transaction_ref,
        }

    if not request.auth_data:
        raise HTTPException(status_code=400, detail="auth_data is required in live mode")

    result = tokenize_card(request.auth_data)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    user.interswitch_token = result["token"]
    user.token_expiry_date = result["token_expiry"]
    db.commit()

    return {"message": "Card saved successfully! [OK]", "token_saved": True}


@router.post("/charge-refill")
def charge_refill(
    request: ChargeRequest,
    token: str,
    db: Session = Depends(get_db),
):
    user = get_current_user(token, db)

    if not user.interswitch_token:
        raise HTTPException(
            status_code=400,
            detail="No card saved. Please save a card first via /payments/save-card",
        )

    prescription = db.query(Prescription).filter(
        Prescription.id == request.prescription_id,
        Prescription.patient_id == user.id,
        Prescription.is_active == True,
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
        delivery_status="pending",
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    result = _do_charge(
        user_token=user.interswitch_token,
        token_expiry=user.token_expiry_date,
        amount_kobo=amount_kobo,
        customer_id=f"PAT-{user.id:04d}",
        prescription_id=prescription.id,
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
        "message": f"Payment successful! NGN {result['amount_naira']:,.2f} charged.",
        "transaction_id": transaction.id,
        "reference": result["reference"],
        "amount": f"NGN {result['amount_naira']:,.2f}",
        "delivery_status": "preparing",
        "prescription": prescription.medication_name,
        "mode": "SANDBOX" if USE_MOCK else "LIVE",
    }


@router.get("/verify/{reference}")
def verify_payment(
    reference: str,
    token: str,
    db: Session = Depends(get_db),
):
    user = get_current_user(token, db)

    transaction = db.query(Transaction).filter(
        Transaction.payment_reference == reference,
        Transaction.patient_id == user.id,
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if USE_MOCK:
        return {
            "verified": True,
            "status": transaction.status,
            "amount": transaction.amount / 100,
            "reference": reference,
            "mode": "SANDBOX",
        }

    result = verify_transaction(reference)
    if result["verified"]:
        transaction.status = "success"
        db.commit()

    return {
        "verified": result["verified"],
        "status": transaction.status,
        "reference": reference,
    }


@router.get("/history")
def payment_history(token: str, db: Session = Depends(get_db)):
    user = get_current_user(token, db)

    transactions = db.query(Transaction).filter(
        Transaction.patient_id == user.id
    ).order_by(Transaction.created_at.desc()).all()

    if not transactions:
        return {
            "message": "No transactions yet",
            "has_saved_card": bool(user.interswitch_token),
            "transactions": [],
        }

    result = []
    for transaction in transactions:
        prescription = db.query(Prescription).filter(
            Prescription.id == transaction.prescription_id
        ).first()
        result.append(
            {
                "id": transaction.id,
                "medication": prescription.medication_name if prescription else "Unknown",
                "amount": transaction.amount,
                "amount_display": f"NGN {transaction.amount / 100:,.2f}",
                "status": transaction.status,
                "delivery_status": transaction.delivery_status,
                "reference": transaction.payment_reference,
                "date": transaction.created_at,
                "created_at": transaction.created_at,
                "prescription_id": transaction.prescription_id,
            }
        )

    return {
        "total_transactions": len(result),
        "has_saved_card": bool(user.interswitch_token),
        "transactions": result,
    }


@router.put("/delivery/{transaction_id}/status")
def update_delivery(
    transaction_id: int,
    status: str,
    token: str,
    db: Session = Depends(get_db),
):
    user = get_current_user(token, db)

    valid_statuses = ["pending", "preparing", "out_for_delivery", "delivered"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Choose from: {valid_statuses}",
        )

    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.patient_id == user.id,
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction.delivery_status = status
    db.commit()

    return {
        "message": f"Delivery status updated to: {status} [OK]",
        "transaction_id": transaction_id,
        "delivery_status": status,
    }


@router.get("/delivery/track/{transaction_id}")
def track_delivery(
    transaction_id: int,
    token: str,
    db: Session = Depends(get_db),
):
    user = get_current_user(token, db)

    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.patient_id == user.id,
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    prescription = db.query(Prescription).filter(
        Prescription.id == transaction.prescription_id
    ).first()

    return {
        "transaction_id": transaction.id,
        "prescription_id": transaction.prescription_id,
        "medication_name": prescription.medication_name if prescription else None,
        "dosage": prescription.dosage if prescription else None,
        "quantity": 30,
        "amount": transaction.amount,
        "status": transaction.status,
        "current_stage": transaction.delivery_status,
        "created_at": transaction.created_at,
        "preparing_time": transaction.created_at if transaction.delivery_status in ["preparing", "out_for_delivery", "delivered"] else None,
        "out_for_delivery_time": transaction.updated_at if transaction.delivery_status in ["out_for_delivery", "delivered"] else None,
        "delivered_time": transaction.updated_at if transaction.delivery_status == "delivered" else None,
        "pharmacy_name": "MediCycle Pharmacy Partner",
        "pharmacy_address": f"{user.city}, {user.state}" if user.city and user.state else "Nearest available partner pharmacy",
        "estimated_delivery": "2-4 hours",
    }


@router.get("/caregiver-info")
def get_caregiver_info(
    prescription_id: int,
    patient_id: int,
    db: Session = Depends(get_db),
):
    prescription = db.query(Prescription).filter(
        Prescription.id == prescription_id,
        Prescription.patient_id == patient_id,
        Prescription.is_active == True,
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
            "state": patient.state,
        },
        "prescription": {
            "medication_name": prescription.medication_name,
            "dosage": prescription.dosage,
            "medication_cost": prescription.medication_cost,
            "days_left": round(prescription.days_left(), 1),
        },
    }


@router.post("/caregiver-charge")
def caregiver_charge(
    request: CaregiverChargeRequest,
    db: Session = Depends(get_db),
):
    prescription = db.query(Prescription).filter(
        Prescription.id == request.prescription_id,
        Prescription.patient_id == request.patient_id,
    ).first()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    patient = db.query(User).filter(User.id == request.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if not prescription.medication_cost:
        raise HTTPException(status_code=400, detail="No cost set for this medication")

    amount_kobo = int(prescription.medication_cost)

    transaction = Transaction(
        patient_id=request.patient_id,
        prescription_id=request.prescription_id,
        amount=amount_kobo,
        status="pending",
        delivery_status="pending",
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    result = _do_charge(
        user_token=request.card_data,
        token_expiry="",
        amount_kobo=amount_kobo,
        customer_id=f"CAREGIVER-{request.patient_id}",
        prescription_id=request.prescription_id,
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
        f"[OK] Great news! {request.caregiver_name} has paid for your {prescription.medication_name} refill. "
        f"Your 30-day supply is on the way! [PILL]",
    )
    route_to_pharmacy(prescription, patient, transaction, db)

    return {
        "message": "Payment successful! Refill authorized.",
        "reference": result["reference"],
        "amount_naira": result["amount_naira"],
        "caregiver": request.caregiver_name,
        "mode": "SANDBOX" if USE_MOCK else "LIVE",
    }


@router.post("/request-refill/{prescription_id}")
def request_refill(
    prescription_id: int,
    token: str,
    db: Session = Depends(get_db),
):
    user = get_current_user(token, db)

    prescription = db.query(Prescription).filter(
        Prescription.id == prescription_id,
        Prescription.patient_id == user.id,
        Prescription.is_active == True,
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
        delivery_status="pending",
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    result = _do_charge(
        user_token=user.interswitch_token,
        token_expiry=user.token_expiry_date,
        amount_kobo=amount_kobo,
        customer_id=f"PAT-{user.id:04d}",
        prescription_id=prescription_id,
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
        f"[OK] Refill confirmed for {prescription.medication_name}! "
        f"NGN {result['amount_naira']:,.0f} charged. Your order is being prepared. [PILL]",
    )
    route_to_pharmacy(prescription, user, transaction, db)

    return {
        "message": "Refill requested successfully! [OK]",
        "prescription": prescription.medication_name,
        "amount_charged": f"NGN {result['amount_naira']:,.0f}",
        "reference": result["reference"],
        "transaction_id": transaction.id,
        "delivery_status": "preparing",
        "track_url": f"medicycle.app/track/{transaction.id}",
    }
