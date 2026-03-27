from sqlalchemy.orm import Session
from app.models.refill_history import RefillHistory
from app.models.prescription import Prescription
from datetime import datetime


def calculate_adherence_score(patient_id: int, db: Session) -> dict:
    """
    Calculate a patient's medication adherence score (0-100)
    based on their refill history.

    Score interpretation:
    - 80-100: Excellent -- alerts at Day 5
    - 60-79:  Good -- alerts at Day 6
    - 40-59:  Fair -- alerts at Day 7
    - 0-39:   Poor -- alerts at Day 8 (consistently late)
    """
    history = db.query(RefillHistory).filter(
        RefillHistory.patient_id == patient_id
    ).order_by(RefillHistory.created_at.desc()).limit(10).all()

    # Not enough history -- return default
    if len(history) < 2:
        return {
            "score": 75,
            "level": "Good",
            "alert_threshold_days": 5,
            "data_points": len(history),
            "message": "Insufficient history -- using default threshold"
        }

    # Calculate average days variance
    variances = [abs(h.days_variance) for h in history if h.days_variance is not None]

    if not variances:
        return {
            "score": 75,
            "level": "Good",
            "alert_threshold_days": 5,
            "data_points": 0,
            "message": "No variance data available"
        }

    avg_variance = sum(variances) / len(variances)
    on_time_refills = sum(1 for v in variances if v <= 1)
    on_time_rate = on_time_refills / len(variances)

    # Calculate score
    # Perfect score = 0 variance, 100% on time
    # Each day of avg variance reduces score by 10
    base_score = 100
    variance_penalty = min(avg_variance * 10, 60)
    score = max(0, int(base_score - variance_penalty + (on_time_rate * 20)))
    score = min(100, score)

    # Determine level and alert threshold
    if score >= 80:
        level = "Excellent"
        alert_days = 5
        message = "Great adherence! Standard 5-day alert."
    elif score >= 60:
        level = "Good"
        alert_days = 6
        message = "Good adherence. Slightly early alert."
    elif score >= 40:
        level = "Fair"
        alert_days = 7
        message = "Fair adherence. Earlier alert recommended."
    else:
        level = "Poor"
        alert_days = 8
        message = "Low adherence. Extended alert window for safety."

    return {
        "score": score,
        "level": level,
        "alert_threshold_days": alert_days,
        "avg_variance_days": round(avg_variance, 1),
        "on_time_rate": f"{int(on_time_rate * 100)}%",
        "data_points": len(variances),
        "message": message
    }


def get_smart_threshold(patient_id: int, db: Session) -> int:
    """
    Get the smart alert threshold for a patient.
    Used by the scheduler to decide when to send alerts.
    Default is 5 days -- adjusted based on adherence score.
    """
    result = calculate_adherence_score(patient_id, db)
    return result["alert_threshold_days"]


def get_all_adherence_report(db: Session) -> list:
    """
    Generate adherence report for all patients.
    Useful for admin dashboard.
    """
    from app.models.user import User
    patients = db.query(User).filter(User.is_active == True).all()

    report = []
    for patient in patients:
        score_data = calculate_adherence_score(patient.id, db)
        report.append({
            "patient_id": patient.id,
            "patient_name": patient.full_name,
            "phone": patient.phone_number[:3] + "****" + patient.phone_number[-3:],
            "adherence_score": score_data["score"],
            "level": score_data["level"],
            "alert_threshold_days": score_data["alert_threshold_days"],
            "message": score_data["message"]
        })

    return sorted(report, key=lambda x: x["adherence_score"])