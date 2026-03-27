from sqlalchemy.orm import Session
from app.models.pharmacy import Pharmacy
from app.models.pharmacy_inventory import PharmacyInventory


# ── SEED MOCK PHARMACIES ──
def seed_pharmacies(db: Session):
    """Seed 3 mock partner pharmacies if none exist."""
    existing = db.query(Pharmacy).count()
    if existing > 0:
        return  # already seeded

    pharmacies = [
        Pharmacy(
            name="MedPlus Pharmacy",
            city="Lagos",
            zone="Victoria Island",
            address="23 Adeola Odeku Street, Victoria Island, Lagos",
            phone="08001234001",
            email="medplus@demo.com"
        ),
        Pharmacy(
            name="HealthPlus Pharmacy",
            city="Lagos",
            zone="Ikeja",
            address="45 Allen Avenue, Ikeja, Lagos",
            phone="08001234002",
            email="healthplus@demo.com"
        ),
        Pharmacy(
            name="Kersey Pharmacy",
            city="Lagos",
            zone="Lekki",
            address="12 Admiralty Way, Lekki Phase 1, Lagos",
            phone="08001234003",
            email="kersey@demo.com"
        ),
        Pharmacy(
            name="Alpha Pharmacy",
            city="Nairobi",
            zone="CBD",
            address="10 Kenyatta Avenue, Nairobi CBD",
            phone="07001234001",
            email="alpha@demo.com"
        ),
        Pharmacy(
            name="Goodlife Pharmacy",
            city="Nairobi",
            zone="Westlands",
            address="Westgate Mall, Westlands, Nairobi",
            phone="07001234002",
            email="goodlife@demo.com"
        ),
        Pharmacy(
            name="Portal Pharmacy",
            city="Nairobi",
            zone="Karen",
            address="Karen Shopping Centre, Karen, Nairobi",
            phone="07001234003",
            email="portal@demo.com"
        ),
    ]

    for p in pharmacies:
        db.add(p)
    db.commit()
    print("[MediCycle] [OK] Mock pharmacies seeded successfully!")


# ── SMART ROUTING LOGIC ──
def find_nearest_pharmacy(
    user_city: str,
    user_state: str,
    medication_name: str,
    db: Session,
    exclude_pharmacy_id: int = None
):
    """
    Find the nearest available pharmacy based on user city/zone.
    Priority: Same city → same state → any available
    Checks inventory for stock availability.
    Returns pharmacy object or None.
    """

    # Get all active pharmacies except excluded one
    query = db.query(Pharmacy).filter(Pharmacy.is_active == True)
    if exclude_pharmacy_id:
        query = query.filter(Pharmacy.id != exclude_pharmacy_id)

    all_pharmacies = query.all()

    if not all_pharmacies:
        return None

    # Priority 1: Same city + in stock
    for pharmacy in all_pharmacies:
        if pharmacy.city.lower() == (user_city or "").lower():
            if _is_in_stock(pharmacy.id, medication_name, db):
                return pharmacy

    # Priority 2: Same state + in stock
    for pharmacy in all_pharmacies:
        if pharmacy.city.lower() in (user_state or "").lower():
            if _is_in_stock(pharmacy.id, medication_name, db):
                return pharmacy

    # Priority 3: Any pharmacy with stock
    for pharmacy in all_pharmacies:
        if _is_in_stock(pharmacy.id, medication_name, db):
            return pharmacy

    # Priority 4: Any pharmacy (ignore stock -- last resort)
    return all_pharmacies[0] if all_pharmacies else None


def _is_in_stock(pharmacy_id: int, medication_name: str, db: Session) -> bool:
    """Check if a pharmacy has a medication in stock."""
    inventory = db.query(PharmacyInventory).filter(
        PharmacyInventory.pharmacy_id == pharmacy_id,
        PharmacyInventory.medication_name.ilike(f"%{medication_name}%")
    ).first()

    # If no inventory record exists, assume in stock
    if not inventory:
        return True

    return inventory.is_in_stock


def handle_out_of_stock(
    original_pharmacy: Pharmacy,
    user_city: str,
    user_state: str,
    medication_name: str,
    db: Session
):
    """
    Requirement 6.6: Handle out-of-stock scenario.
    Finds next available pharmacy and returns notification message.
    """
    backup = find_nearest_pharmacy(
        user_city=user_city,
        user_state=user_state,
        medication_name=medication_name,
        db=db,
        exclude_pharmacy_id=original_pharmacy.id
    )

    if backup:
        return {
            "rerouted": True,
            "pharmacy": backup,
            "sms_message": (
                f"Medication secured at {backup.name} due to stock availability "
                f"at your primary location. Delivery is still on track. [TRUCK]"
            )
        }

    return {
        "rerouted": False,
        "pharmacy": None,
        "sms_message": "We are currently checking stock at partner pharmacies. Our team will contact you shortly."
    }