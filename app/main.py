from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import engine, Base
from app.routes import auth, prescriptions, payments
import os

# Import all models so tables are created
from app.models import user, prescription, transaction, refill_history
from app.models.pharmacy import Pharmacy
from app.models.pharmacy_inventory import PharmacyInventory

# Create all tables
Base.metadata.create_all(bind=engine)
print("Database tables created/verified")

app = FastAPI(
    title="MediCycle API",
    description="Automated medication refill platform",
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

# ---------------------------
# API ROUTES (NEVER AFFECT FRONTEND)
# ---------------------------
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(prescriptions.router, prefix="/prescriptions", tags=["Prescriptions"])
app.include_router(payments.router, prefix="/payments", tags=["Payments"])

# ---------------------------
# FRONTEND SETUP (FIXED FOR RENDER)
# ---------------------------

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
frontend_path = os.path.join(BASE_DIR, "frontend")

# Serve static assets (CSS, JS, images, html files)
if os.path.exists(frontend_path):
    print(f"✅ Frontend found at {frontend_path}")

    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

else:
    print(f"⚠️ Frontend folder not found at {frontend_path}")


# ---------------------------
# FRONTEND ROUTES (PREVENT 404 ON RENDER)
# ---------------------------

@app.get("/")
def root():
    index_file = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "MediCycle API running"}


@app.get("/payment.html")
def payment():
    return FileResponse(os.path.join(frontend_path, "payment.html"))


@app.get("/dashboard.html")
def dashboard():
    return FileResponse(os.path.join(frontend_path, "dashboard.html"))


@app.get("/add-prescription.html")
def add_prescription():
    return FileResponse(os.path.join(frontend_path, "add-prescription.html"))


# ---------------------------
# STARTUP / SHUTDOWN
# ---------------------------

@app.on_event("startup")
async def startup_event():
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
    from app.services.scheduler import stop_scheduler
    stop_scheduler()


# ---------------------------
# HEALTH CHECKS
# ---------------------------

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/test")
def test():
    return {"status": "ok", "message": "API is working"}