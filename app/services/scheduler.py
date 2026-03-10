from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.prescription import Prescription
from app.models.user import User
from app.models.transaction import Transaction
from app.models.refill_history import RefillHistory
from app.services.interswitch import charge_patient, mock_charge_success
from app.services.pharmacy_router import find_nearest_pharmacy
import os
import requests
from app.services.adherence import get_smart_threshold

USE_MOCK = os.getenv("USE_MOCK_PAYMENTS", "true").lower() == "true"
USE_MOCK_SMS = os.getenv("USE_MOCK_SMS", "true").lower() == "true"
TERMII_API_KEY = os.getenv("TERMII_API_KEY")
TERMII_SENDER_ID = os.getenv("TERMII_SENDER_ID", "MediCycle")

scheduler = BackgroundScheduler()


# ══════════════════════════════════════════
# MAIN DAILY JOB
# ══════════════════════════════════════════

def check_all_prescriptions():
    """
    Main daily job — runs at 8AM every day.
    Checks every active verified prescription and triggers
    alerts or payments based on days left.
    Implements Requirement 4.2: Three-Stage Alert Cycle.
    """
    print(f"\n[Scheduler] 🕐 Running daily check — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    db: Session = SessionLocal()

    try:
        # Get all active, verified prescriptions
        prescriptions = db.query(Prescription).filter(
            Prescription.is_active == True,
            Prescription.document_status == "verified"
        ).all()

        print(f"[Scheduler] Checking {len(prescriptions)} active prescriptions...")

        for prescription in prescriptions:
            try:
                process_prescription(prescription, db)
            except Exception as e:
                print(f"[Scheduler] ❌ Error processing prescription {prescription.id}: {str(e)}")
                continue

    except Exception as e:
        print(f"[Scheduler] ❌ Fatal error: {str(e)}")
    finally:
        db.close()
        print(f"[Scheduler] ✅ Daily check complete.\n")


# ══════════════════════════════════════════
# PROCESS SINGLE PRESCRIPTION
# ══════════════════════════════════════════

def process_prescription(prescription: Prescription, db: Session):
    """
    Process a single prescription based on days left.
    Implements the 3-stage alert cycle (Req 4.2).

    Stage 1 — Day 5: Standard refill alert
    Stage 2 — Day 2: Urgent critical alert
    Stage 3 — Day 0: Auto-charge + caregiver alert if payment fails
    """
    days_left = prescription.days_left()
    patient = db.query(User).filter(User.id == prescription.patient_id).first()

    if not patient:
        print(f"  → Prescription {prescription.id}: Patient not found, skipping.")
        return

    name = patient.full_name
    med = prescription.medication_name

    print(f"  → {name} | {med} | {round(days_left, 1)} days left")

    # ── STAGE 1: ~5 days left — Standard Alert ──
    # Get smart threshold based on patient adherence
   
    threshold = get_smart_threshold(patient.id, db)
    threshold_low = threshold - 0.5
    threshold_high = threshold + 0.5

    # ── STAGE 1: ~threshold days left — Standard Alert ──
    if threshold_low <= days_left <= threshold_high:
        message = (
            f"Hi {name}, your {med} supply is running low — "
            f"only {round(days_left)} days left. "
            f"Your refill has been scheduled. "
            f"Reply CONFIRM to authorize payment or visit: medicycle.app/refill"
        )
        send_sms(patient.phone_number, message)
        print(f"    📱 Stage 1 — Standard alert sent to {mask_phone(patient.phone_number)}")

    # ── STAGE 2: ~2 days left — Urgent Alert ──
    elif 1.5 <= days_left <= 2.5:
        message = (
            f"CRITICAL: {name}, you have 48 hours of {med} left. "
            f"Pay now to avoid a treatment gap. "
            f"Your card will be charged automatically in 24 hours if no action is taken. "
            f"Visit: medicycle.app/pay"
        )
        send_sms(patient.phone_number, message)
        print(f"    🚨 Stage 2 — URGENT alert sent to {mask_phone(patient.phone_number)}")

    # ── STAGE 3: Day 0 — Auto charge + Caregiver alert ──
    elif days_left <= 0:
        print(f"    ⚠️  {name} has run out of {med}! Triggering auto-charge...")

        # Attempt auto payment
        payment_success = attempt_auto_payment(prescription, patient, db)

        if not payment_success:
            print(f"    💔 Auto-payment failed — alerting caregiver...")

            # Alert caregiver (Req 4.3)
            if patient.caregiver_phone:
                caregiver_message = (
                    f"URGENT: {name}'s {med} supply has run out. "
                    f"Please authorize their refill immediately. "
                    f"One-click payment: medicycle.app/caregiver-pay/{prescription.id}/{patient.id}"
                )
                send_sms(patient.caregiver_phone, caregiver_message)
                print(f"    👨‍👩‍👧 Caregiver alert sent to {mask_phone(patient.caregiver_phone)}")
            else:
                print(f"    ⚠️  No caregiver phone registered for {name}")

        # Log refill attempt in history
        log_refill_history(prescription, days_left, db)


# ══════════════════════════════════════════
# AUTO PAYMENT
# ══════════════════════════════════════════

def attempt_auto_payment(
    prescription: Prescription,
    patient: User,
    db: Session
) -> bool:
    """
    Attempt to auto-charge patient for refill.
    Routes order to nearest pharmacy on success.
    Returns True if payment successful.
    """
    # Validate prerequisites
    if not patient.interswitch_token:
        print(f"    ❌ No card saved for {patient.full_name}")
        return False

    if not prescription.medication_cost:
        print(f"    ❌ No medication cost set for {prescription.medication_name}")
        return False

    amount_kobo = int(prescription.medication_cost)

    # Create pending transaction
    transaction = Transaction(
        patient_id=patient.id,
        prescription_id=prescription.id,
        amount=amount_kobo,
        status="pending",
        delivery_status="pending"
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    # Attempt charge
    if USE_MOCK:
        result = mock_charge_success(amount_kobo, prescription.id)
    else:
        result = charge_patient(
            token=patient.interswitch_token,
            token_expiry=patient.token_expiry_date,
            amount_kobo=amount_kobo,
            customer_id=f"PAT-{patient.id:04d}",
            prescription_id=prescription.id
        )

    if not result["success"]:
        # Mark transaction failed
        transaction.status = "failed"
        db.commit()
        print(f"    ❌ Payment failed: {result.get('error')}")
        return False

    # Payment successful — update transaction
    transaction.status = "success"
    transaction.payment_reference = result["reference"]
    transaction.delivery_status = "preparing"

    # Reset prescription after refill
    prescription.last_refill_date = datetime.utcnow()
    db.commit()

    print(f"    💳 Payment SUCCESS — ₦{result['amount_naira']:,.0f} charged")

    # Route order to nearest pharmacy (Req 6.5)
    route_to_pharmacy(prescription, patient, transaction, db)

    return True


# ══════════════════════════════════════════
# PHARMACY ROUTING
# ══════════════════════════════════════════

def route_to_pharmacy(
    prescription: Prescription,
    patient: User,
    transaction: Transaction,
    db: Session,
    exclude_pharmacy_id: int = None
):
    """
    Route order to nearest available pharmacy.
    Implements Req 6.5 (Smart Routing) and 6.6 (Out of Stock Failover).
    """
    pharmacy = find_nearest_pharmacy(
        user_city=patient.city,
        user_state=patient.state,
        medication_name=prescription.medication_name,
        db=db,
        exclude_pharmacy_id=exclude_pharmacy_id
    )

    if not pharmacy:
        print(f"    ❌ No pharmacy found for {prescription.medication_name}")
        send_sms(
            patient.phone_number,
            f"We are currently checking stock at partner pharmacies for your {prescription.medication_name}. "
            f"Our team will contact you shortly."
        )
        return

    # Check if out of stock — try failover (Req 6.6)
    from app.models.pharmacy_inventory import PharmacyInventory
    inventory = db.query(PharmacyInventory).filter(
        PharmacyInventory.pharmacy_id == pharmacy.id,
        PharmacyInventory.medication_name.ilike(f"%{prescription.medication_name}%")
    ).first()

    if inventory and not inventory.is_in_stock:
        print(f"    ⚠️  {pharmacy.name} is out of stock — rerouting...")

        # Notify patient about rerouting
        send_sms(
            patient.phone_number,
            f"Medication secured at an alternative pharmacy due to stock availability "
            f"at your primary location. Delivery is still on track. 🚚"
        )

        # Try next pharmacy
        route_to_pharmacy(
            prescription, patient, transaction, db,
            exclude_pharmacy_id=pharmacy.id
        )
        return

    # Update transaction with assigned pharmacy
    transaction.delivery_status = "preparing"
    db.commit()

    print(f"    🏥 Order routed to: {pharmacy.name} ({pharmacy.city} — {pharmacy.zone})")

    # Notify patient
    amount_naira = transaction.amount / 100
    send_sms(
        patient.phone_number,
        f"✅ Payment of ₦{amount_naira:,.0f} confirmed for {prescription.medication_name}. "
        f"Your order has been sent to {pharmacy.name}, {pharmacy.zone}. "
        f"Estimated delivery: 2-4 hours. Track: medicycle.app/track/{transaction.id}"
    )


# ══════════════════════════════════════════
# REFILL HISTORY LOGGING
# ══════════════════════════════════════════

def log_refill_history(
    prescription: Prescription,
    days_variance: float,
    db: Session
):
    """Log refill event for adherence score calculation."""
    history = RefillHistory(
        patient_id=prescription.patient_id,
        prescription_id=prescription.id,
        expected_refill_date=datetime.utcnow(),
        actual_refill_date=datetime.utcnow(),
        days_variance=round(days_variance, 1)
    )
    db.add(history)
    db.commit()


# ══════════════════════════════════════════
# SMS SERVICE
# ══════════════════════════════════════════

def send_sms(phone: str, message: str):
    """
    Send SMS via Termii (Nigeria).
    Currently in MOCK mode — logs to console.
    To activate real SMS: set USE_MOCK_SMS=false and add TERMII_API_KEY in .env
    """
    if USE_MOCK_SMS:
        print(f"    📱 [MOCK SMS] → {mask_phone(phone)}")
        print(f"       Message: {message[:80]}...")
        return True

    # Real Termii integration
    try:
        response = requests.post(
            "https://api.ng.termii.com/api/sms/send",
            json={
                "to": phone,
                "from": TERMII_SENDER_ID,
                "sms": message,
                "type": "plain",
                "api_key": TERMII_API_KEY,
                "channel": "generic"
            },
            timeout=10
        )

        if response.status_code == 200:
            print(f"    ✅ SMS sent to {mask_phone(phone)}")
            return True
        else:
            print(f"    ❌ SMS failed: {response.text}")
            return False

    except Exception as e:
        print(f"    ❌ SMS error: {str(e)}")
        return False


# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════

def mask_phone(phone: str) -> str:
    """Mask phone number for privacy: 0712345678 → 071****678"""
    if not phone or len(phone) < 7:
        return phone
    return phone[:3] + "****" + phone[-3:]


# ══════════════════════════════════════════
# SCHEDULER CONTROL
# ══════════════════════════════════════════

def start_scheduler():
    """Start the background scheduler."""
    if not scheduler.running:
        # Daily check at 8:00 AM
        scheduler.add_job(
            check_all_prescriptions,
            CronTrigger(hour=8, minute=0),
            id="daily_prescription_check",
            replace_existing=True
        )
        scheduler.start()
        print("[Scheduler] ✅ Daily prescription check scheduled for 8:00 AM")


def stop_scheduler():
    """Stop the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown()
        print("[Scheduler] Stopped.")


def run_check_now():
    """
    Manually trigger the daily check immediately.
    Useful for testing and demos.
    """
    print("[Scheduler] 🔧 Manual trigger initiated...")
    check_all_prescriptions()
    