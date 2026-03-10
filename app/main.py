from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routes import auth, prescriptions, payments

# Import all models so tables are created
from app.models import user, prescription, transaction, refill_history
from app.models.pharmacy import Pharmacy
from app.models.pharmacy_inventory import PharmacyInventory

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MediCycle API",
    description="Automated medication refill platform — Enyata x Interswitch Buildathon 2026",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(prescriptions.router, prefix="/prescriptions", tags=["Prescriptions"])
app.include_router(payments.router, prefix="/payments", tags=["Payments"])


@app.on_event("startup")
async def startup_event():
    """Seed mock data and start scheduler on startup."""
    from app.database import SessionLocal
    from app.services.pharmacy_router import seed_pharmacies
    from app.services.scheduler import start_scheduler

    db = SessionLocal()
    try:
        seed_pharmacies(db)
    finally:
        db.close()

    start_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    """Stop scheduler gracefully on shutdown."""
    from app.services.scheduler import stop_scheduler
    stop_scheduler()


@app.get("/")
def root():
    return {
        "message": "💊 MediCycle API is running!",
        "version": "1.0.0",
        "status": "healthy"
    }


@app.get("/health")
def health():
    return {"status": "ok"}