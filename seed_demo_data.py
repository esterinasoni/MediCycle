"""
MediCycle Demo Data Seeder
Run this before demo day to populate the database with perfect test scenarios.
Usage: python seed_demo_data.py
"""

from app.database import SessionLocal
from app.models.user import User
from app.models.prescription import Prescription, PrescriptionStatus
from app.models.pharmacy import Pharmacy
from app.models.pharmacy_inventory import PharmacyInventory
from app.models.transaction import Transaction
from app.models.refill_history import RefillHistory
from datetime import datetime, timedelta
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def seed():
    db = SessionLocal()
    print("\n🌱 MediCycle Demo Seeder Starting...\n")

    try:
        # ── CLEAR EXISTING DEMO DATA ──
        print("🧹 Clearing existing data...")
        db.query(RefillHistory).delete()
        db.query(Transaction).delete()
        db.query(PharmacyInventory).delete()
        db.query(Prescription).delete()
        db.query(Pharmacy).delete()
        db.query(User).delete()
        db.commit()
        print("   ✅ Cleared\n")

        today = datetime.now()

        # ══════════════════════════════════════════
        # PHARMACIES
        # ══════════════════════════════════════════
        print("🏥 Seeding pharmacies...")

        ph1 = Pharmacy(
            name="Halisi Pharma",
            city="Westlands",
            zone="Nairobi",
            address="Westlands Estate, Nairobi",
            phone="0700000001",
            is_active=True
        )
        ph2 = Pharmacy(
            name="Boma Chemist",
            city="Kikuyu",
            zone="Kiambu",
            address="Kikuyu Estate, Kiambu",
            phone="0700000002",
            is_active=True
        )
        ph3 = Pharmacy(
            name="Afya Bora Pharmacy",
            city="Thika Road",
            zone="Nairobi",
            address="Thika Road Estate, Nairobi",
            phone="0700000003",
            is_active=True
        )

        db.add_all([ph1, ph2, ph3])
        db.commit()
        db.refresh(ph1); db.refresh(ph2); db.refresh(ph3)
        print(f"   ✅ {ph1.name} (ID {ph1.id})")
        print(f"   ✅ {ph2.name} (ID {ph2.id})")
        print(f"   ✅ {ph3.name} (ID {ph3.id}) — OUT OF STOCK pharmacy\n")

        # ══════════════════════════════════════════
        # PHARMACY INVENTORY
        # ══════════════════════════════════════════
        print("📦 Seeding pharmacy inventory...")

        medications = [
            "Amlodipine", "Metformin", "Atorvastatin",
            "Ventolin", "Insulin", "Losartan"
        ]

        for med in medications:
            # PH01 — in stock for everything
            db.add(PharmacyInventory(
                pharmacy_id=ph1.id,
                medication_name=med,
                is_in_stock=True
            ))
            # PH02 — in stock for everything
            db.add(PharmacyInventory(
                pharmacy_id=ph2.id,
                medication_name=med,
                is_in_stock=True
            ))
            # PH03 — OUT OF STOCK for Metformin (triggers failover demo)
            db.add(PharmacyInventory(
                pharmacy_id=ph3.id,
                medication_name=med,
                is_in_stock=(med != "Metformin")
            ))

        db.commit()
        print("   ✅ Inventory seeded (PH03 Metformin = OUT OF STOCK)\n")

        # ══════════════════════════════════════════
        # PATIENTS
        # ══════════════════════════════════════════
        print("👥 Seeding patients...")

        hashed_pw = pwd_context.hash("demo1234")

        # P101 — Kwame (Happy Path + Stock Failover)
        kwame = User(
            full_name="Kwame Owino",
            email="kwame@medicycle.demo",
            phone_number="+254710000001",
            hashed_password=hashed_pw,
            is_verified=True,
            address="Westlands Estate",
            city="Westlands",
            state="Nairobi",
            caregiver_name="Jane Wambui",
            caregiver_phone="+254790000001",
            interswitch_token="DEMO_TOKEN_KWAME",
            token_expiry_date="2027-12-31"
        )

        # P102 — Wanjiku (5-day alert)
        wanjiku = User(
            full_name="Wanjiku Kamau",
            email="wanjiku@medicycle.demo",
            phone_number="+254710000002",
            hashed_password=hashed_pw,
            is_verified=True,
            address="Kikuyu Estate",
            city="Kikuyu",
            state="Kiambu",
            caregiver_name="Peter Omondi",
            caregiver_phone="+254790000002",
            interswitch_token="DEMO_TOKEN_WANJIKU",
            token_expiry_date="2027-12-31"
        )

        # P103 — Musa (expired prescription)
        musa = User(
            full_name="Musa Otieno",
            email="musa@medicycle.demo",
            phone_number="+254710000003",
            hashed_password=hashed_pw,
            is_verified=True,
            address="Thika Road Estate",
            city="Thika Road",
            state="Nairobi",
            caregiver_name="Sarah Cherono",
            caregiver_phone="+254790000003",
            interswitch_token="DEMO_TOKEN_MUSA",
            token_expiry_date="2027-12-31"
        )

        # P104 — Achieng (unverified prescription)
        achieng = User(
            full_name="Achieng Anyango",
            email="achieng@medicycle.demo",
            phone_number="+254710000004",
            hashed_password=hashed_pw,
            is_verified=True,
            address="South C Estate",
            city="South C",
            state="Nairobi",
            caregiver_name="Hassan Ali",
            caregiver_phone="+254790000004",
            interswitch_token="DEMO_TOKEN_ACHIENG",
            token_expiry_date="2027-12-31"
        )

        # P105 — Fatuma (emergency / caregiver alert)
        fatuma = User(
            full_name="Fatuma Juma",
            email="fatuma@medicycle.demo",
            phone_number="+254710000005",
            hashed_password=hashed_pw,
            is_verified=True,
            address="Kilimani Estate",
            city="Kilimani",
            state="Nairobi",
            caregiver_name="Grace Nyambura",
            caregiver_phone="+254790000005",
            interswitch_token="DEMO_TOKEN_FATUMA",
            token_expiry_date="2027-12-31"
        )

        db.add_all([kwame, wanjiku, musa, achieng, fatuma])
        db.commit()
        for u in [kwame, wanjiku, musa, achieng, fatuma]:
            db.refresh(u)
            print(f"   ✅ {u.full_name} (ID {u.id}) — {u.email}")
        print()

        # ══════════════════════════════════════════
        # PRESCRIPTIONS
        # ══════════════════════════════════════════
        print("💊 Seeding prescriptions...")

        # RX001 — Kwame / Amlodipine — STABLE (20 days left)
        rx1 = Prescription(
            patient_id=kwame.id,
            medication_name="Amlodipine",
            dosage="5mg",
            frequency=1,
            total_quantity=20,
            last_refill_date=today - timedelta(days=10),
            prescription_issue_date=today - timedelta(days=10),
            prescription_expiry_date=today + timedelta(days=170),
            medication_expiry_date=today + timedelta(days=365),
            medication_cost=50000,
            document_status=PrescriptionStatus.VERIFIED.value,
            document_path="uploads/prescriptions/kwame_amlodipine.png",
            is_active=True
        )

        # RX002 — Kwame / Metformin — STOCK FAILOVER (4 days, PH03 out of stock)
        rx2 = Prescription(
            patient_id=kwame.id,
            medication_name="Metformin",
            dosage="500mg",
            frequency=2,
            total_quantity=8,
            last_refill_date=today - timedelta(days=15),
            prescription_issue_date=today - timedelta(days=15),
            prescription_expiry_date=today + timedelta(days=165),
            medication_expiry_date=today + timedelta(days=365),
            medication_cost=80000,
            document_status=PrescriptionStatus.VERIFIED.value,
            document_path="uploads/prescriptions/kwame_metformin.png",
            is_active=True
        )

        # RX003 — Wanjiku / Atorvastatin — 5-DAY ALERT
        rx3 = Prescription(
            patient_id=wanjiku.id,
            medication_name="Atorvastatin",
            dosage="20mg",
            frequency=1,
            total_quantity=5,
            last_refill_date=today - timedelta(days=25),
            prescription_issue_date=today - timedelta(days=25),
            prescription_expiry_date=today + timedelta(days=65),
            medication_expiry_date=today + timedelta(days=365),
            medication_cost=120000,
            document_status=PrescriptionStatus.VERIFIED.value,
            document_path="uploads/prescriptions/wanjiku_atorvastatin.png",
            is_active=True
        )

        # RX004 — Musa / Ventolin — EXPIRED
        rx4 = Prescription(
            patient_id=musa.id,
            medication_name="Ventolin",
            dosage="100mcg",
            frequency=1,
            total_quantity=10,
            last_refill_date=today - timedelta(days=210),
            prescription_issue_date=today - timedelta(days=210),
            prescription_expiry_date=today - timedelta(days=30),   # already expired!
            medication_expiry_date=today + timedelta(days=365),
            medication_cost=60000,
            document_status=PrescriptionStatus.VERIFIED.value,
            document_path="uploads/prescriptions/musa_ventolin.png",
            is_active=True
        )

        # RX005 — Achieng / Insulin — PENDING UPLOAD
        rx5 = Prescription(
            patient_id=achieng.id,
            medication_name="Insulin",
            dosage="10 units",
            frequency=2,
            total_quantity=40,
            last_refill_date=today - timedelta(days=10),
            prescription_issue_date=today - timedelta(days=10),
            prescription_expiry_date=today + timedelta(days=170),
            medication_expiry_date=today + timedelta(days=365),
            medication_cost=200000,
            document_status=PrescriptionStatus.INCOMPLETE.value,   # not verified!
            document_path=None,
            is_active=True
        )

        # RX006 — Fatuma / Losartan — EMERGENCY (0 pills left)
        rx6 = Prescription(
            patient_id=fatuma.id,
            medication_name="Losartan",
            dosage="50mg",
            frequency=1,
            total_quantity=0,
            last_refill_date=today - timedelta(days=30),
            prescription_issue_date=today - timedelta(days=30),
            prescription_expiry_date=today + timedelta(days=90),
            medication_expiry_date=today + timedelta(days=365),
            medication_cost=90000,
            document_status=PrescriptionStatus.VERIFIED.value,
            document_path="uploads/prescriptions/fatuma_losartan.png",
            is_active=True
        )

        db.add_all([rx1, rx2, rx3, rx4, rx5, rx6])
        db.commit()
        for rx in [rx1, rx2, rx3, rx4, rx5, rx6]:
            db.refresh(rx)

        print(f"   ✅ RX001 — Kwame / Amlodipine    — {round(rx1.days_left(), 1)} days left 🟢 STABLE")
        print(f"   ✅ RX002 — Kwame / Metformin     — {round(rx2.days_left(), 1)} days left 🔄 STOCK FAILOVER")
        print(f"   ✅ RX003 — Wanjiku / Atorvastatin — {round(rx3.days_left(), 1)} days left 📱 ALERT")
        print(f"   ✅ RX004 — Musa / Ventolin        — EXPIRED 🔴")
        print(f"   ✅ RX005 — Achieng / Insulin      — PENDING UPLOAD ⏳")
        print(f"   ✅ RX006 — Fatuma / Losartan      — {round(rx6.days_left(), 1)} days left 🚨 EMERGENCY")

        # ══════════════════════════════════════════
        # SUMMARY
        # ══════════════════════════════════════════
        print("\n" + "═" * 50)
        print("✅ DEMO DATA SEEDED SUCCESSFULLY!")
        print("═" * 50)
        print("\n📋 Login credentials (all use password: demo1234):")
        print("   kwame@medicycle.demo     — Stable + Stock Failover")
        print("   wanjiku@medicycle.demo   — 5-Day Alert")
        print("   musa@medicycle.demo      — Expired Prescription")
        print("   achieng@medicycle.demo   — Pending Upload")
        print("   fatuma@medicycle.demo    — Emergency / Caregiver Alert")
        print("\n🚀 Start server: uvicorn app.main:app --reload")
        print("🌐 Frontend: open frontend/index.html in browser\n")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Seeding failed: {str(e)}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    seed()