# MediCycle

### Enyata × Interswitch Buildathon 2026 - Health Track

**MediCycle** is a data-driven medication management platform designed to eliminate **“Refill Gaps”** for patients living with chronic conditions. By combining clinical logic, automated notifications, and seamless payments, we ensure patients never run out of life-saving medication.


##  The Problem

Patients with chronic illnesses (e.g. hypertension, diabetes, asthma) often:

* Forget to refill prescriptions on time
* Lack visibility into remaining medication
* Face logistical barriers accessing pharmacies
* Depend on manual tracking or caregivers

This results in dangerous **refill gaps**, leading to:

* Missed doses
* Health deterioration
* Preventable hospital visits


##  Our Solution

MediCycle acts as a **Clinical Refill Intelligence System** that proactively manages medication cycles:

* **Smart Tracking Engine**
  Calculates medication depletion based on dosage and frequency.

* **Predictive Notifications**
  Alerts patients before medication runs out.

* **Emergency Safety Net (Caregiver Escalation)** 
  Notifies caregivers when medication reaches zero — enabling immediate intervention.

* **Seamless Payments**
  Integrated with **Interswitch APIs** for one-click refill payments.

* **Pharmacy Routing & Delivery**
  Automatically routes orders to available pharmacies and triggers delivery.


##  How It Works (System Flow)

1. Patient uploads prescription
2. System validates and stores medication data
3. Daily engine calculates **Days Left**
4. Notifications triggered based on thresholds:

   * 5 days → Reminder
   * 2 days → Urgent alert
   * 0 days → **Emergency caregiver escalation**
5. User (or caregiver) completes payment
6. System routes order to nearest pharmacy
7. Delivery is triggered and tracked


##  Communication System (Core Feature)

MediCycle uses a **trigger-based notification engine**:

| Scenario                | Trigger                | Action                   |
| ----------------------- | ---------------------- | ------------------------ |
| Verification Failed     | `is_verified == False` | Prompt user to re-upload |
| Refill Reminder         | `days_left ≤ 5`        | Notify patient           |
| Urgent Alert            | `days_left ≤ 2`        | Send critical message    |
| Stock Failover          | `primary_OOS == True`  | Reroute pharmacy         |
| Expired Prescription    | `today > expiry_date`  | Block refill             |
|  Emergency Escalation | `pills_remaining == 0` | Alert caregiver          |

 Full scripts available in `/communications/notifications.md`

##  MVP Scope (Buildathon Focus)

For the MVP, we are prioritizing:

* Refill tracking engine
* Notification system (multi-stage alerts)
* Emergency caregiver escalation (**core differentiator**)
* Payment integration (Interswitch)
* Basic pharmacy routing (mock data)


##  Tech Stack (Planning Phase)

* **Frontend:** Streamlit (Python-based UI)
* **Backend:** FastAPI
* **Database:** PostgreSQL
* **Payments:** Interswitch Webpay / Recurring API
* **Automation (optional):** n8n workflows

##  User Personas

### 1. Mary Wanjiku (Elderly Patient)

* Age: 68
* Condition: Hypertension
* Challenge: Forgets to refill medication
* Needs: Simple reminders + caregiver support

### 2. James Otieno (Busy Professional)

* Age: 35
* Condition: Diabetes
* Challenge: Busy schedule
* Needs: Automated reminders + quick payment

### 3. Amina Hassan (Remote Area Resident)

* Age: 42
* Condition: Asthma
* Challenge: Limited pharmacy access
* Needs: Delivery + routing

### 4. Brian Mwangi (Caregiver)

* Age: 30
* Role: Caregiver for elderly parent
* Challenge: No visibility into medication status
* Needs: Emergency alerts + refill control

### 5. Sarah Chebet (Young Adult Patient)

* Age: 27
* Condition: Chronic condition
* Challenge: Inconsistent adherence
* Needs: Smart reminders + tracking


## Product Differentiator

Unlike traditional pharmacy apps, MediCycle introduces a **Caregiver Safety Net**:

> When a patient runs out of medication, the system escalates the situation to a caregiver — ensuring no patient is left without support.

This feature directly addresses high-risk scenarios for:

* Elderly patients
* Chronically ill individuals
* Patients in remote areas


##  Team: MediCycle

* **Esterina** – Team Lead & Data Scientist
* **Winfred** – Data Scientist
* **Maureen Cheptoo** – Product Manager & UX Strategy
* **Phylis** – Software Developer / Cybersecurity


## Current Status

We are currently in the **MVP Build Phase**, focusing on:

* Implementing notification logic
* Building refill tracking engine
* Integrating payment workflows
* Designing caregiver escalation system

## Local Run

The project is now split so the backend and frontend can run independently.

Backend:
```powershell
cd backend
pip install -r requirements.txt
.\run_backend.ps1
```

Frontend:
```powershell
cd frontend
.\run_frontend.ps1
```

Then open `http://127.0.0.1:3000` in your browser. The frontend calls `http://127.0.0.1:8000` by default.

## Future Scope (Post-MVP)

To keep the MVP focused, several features are planned for future development:

- **Prescription Digitization (OCR):** Reduce manual input and improve data accuracy  
- **Real-Time Pharmacy Stock Integration:** Ensure medication availability before refill  
- **Adherence Analytics:** Improve long-term medication adherence  
- **Insurance Integration:** Reduce financial barriers to access  
- **Caregiver Dashboard:** Enable remote patient support  
- **Offline Access (USSD/SMS):** Support users without smartphones  
- **Predictive Risk Modeling:** Identify patients at risk of missing refills early

