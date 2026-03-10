import requests
import os
import base64
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── INTERSWITCH CONFIG ──
CLIENT_ID = os.getenv("INTERSWITCH_CLIENT_ID", "YOUR_CLIENT_ID_HERE")
CLIENT_SECRET = os.getenv("INTERSWITCH_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")
BASE_URL = os.getenv("INTERSWITCH_BASE_URL", "https://qa.interswitchng.com")

# ── HELPER: Generate unique reference ──
def generate_ref(prefix="medicycle"):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique = str(uuid.uuid4())[:8].upper()
    return f"{prefix}_{timestamp}_{unique}"

# ── STEP 0: Get Access Token ──
def get_access_token():
    """Get Interswitch OAuth token. Valid for 1 hour."""
    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()

        response = requests.post(
            f"{BASE_URL}/passport/oauth/token",
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            data={"grant_type": "client_credentials"},
            timeout=30
        )

        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print(f"[Interswitch] Token error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"[Interswitch] Token exception: {str(e)}")
        return None


# ── STEP 1: Tokenize Card ──
def tokenize_card(auth_data: str, transaction_ref: str = None):
    """
    Tokenize a patient's card for recurring payments.
    auth_data: encrypted card data from frontend
    Returns: { token, tokenExpiryDate } or None
    """
    try:
        access_token = get_access_token()
        if not access_token:
            return {"success": False, "error": "Could not get access token"}

        ref = transaction_ref or generate_ref("tokenize")

        response = requests.post(
            f"{BASE_URL}/api/v2/purchases/validations/recurrents",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "transactionRef": ref,
                "AuthData": auth_data,
            },
            timeout=30
        )

        data = response.json()

        if response.status_code in [200, 201]:
            return {
                "success": True,
                "token": data.get("token"),
                "token_expiry": data.get("tokenExpiryDate"),
                "transaction_ref": ref
            }
        else:
            return {
                "success": False,
                "error": data.get("description", "Tokenization failed"),
                "code": response.status_code
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── STEP 2: Charge Patient (Recurring) ──
def charge_patient(
    token: str,
    token_expiry: str,
    amount_kobo: int,
    customer_id: str,
    prescription_id: int
):
    """
    Charge a patient using their saved card token.
    amount_kobo: amount in kobo (₦5000 = 500000)
    Returns: { success, reference, amount } or error
    """
    try:
        access_token = get_access_token()
        if not access_token:
            return {"success": False, "error": "Could not get access token"}

        ref = generate_ref(f"refill_{prescription_id}")

        response = requests.post(
            f"{BASE_URL}/api/v2/purchases/recurrents",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "customerId": str(customer_id),
                "amount": str(amount_kobo),
                "currency": "NGN",
                "token": token,
                "tokenExpiryDate": token_expiry,
                "transferRef": ref,
                "requestRef": ref,
            },
            timeout=30
        )

        data = response.json()

        if response.status_code in [200, 201]:
            return {
                "success": True,
                "reference": ref,
                "amount_kobo": amount_kobo,
                "amount_naira": amount_kobo / 100,
                "response_code": data.get("responseCode"),
                "response_description": data.get("responseDescription")
            }
        else:
            return {
                "success": False,
                "error": data.get("description", "Payment failed"),
                "code": response.status_code
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── STEP 3: Verify Transaction ──
def verify_transaction(transaction_ref: str):
    """
    Verify a payment was successful.
    Always verify before marking a payment as complete!
    """
    try:
        access_token = get_access_token()
        if not access_token:
            return {"success": False, "error": "Could not get access token"}

        response = requests.get(
            f"{BASE_URL}/collections/api/v1/gettransaction.json",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            params={"merchantcode": CLIENT_ID, "transactionreference": transaction_ref},
            timeout=30
        )

        data = response.json()

        # Response code "00" means success in Interswitch
        if data.get("ResponseCode") == "00":
            return {
                "success": True,
                "verified": True,
                "amount": data.get("Amount"),
                "reference": transaction_ref
            }
        else:
            return {
                "success": True,
                "verified": False,
                "response_code": data.get("ResponseCode"),
                "error": data.get("ResponseDescription", "Transaction not successful")
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── SANDBOX TEST: Mock response for demo ──
def mock_charge_success(amount_kobo: int, prescription_id: int):
    """
    Use this during hackathon demo when real Interswitch
    credentials aren't available yet.
    """
    ref = generate_ref(f"mock_{prescription_id}")
    return {
        "success": True,
        "reference": ref,
        "amount_kobo": amount_kobo,
        "amount_naira": amount_kobo / 100,
        "response_code": "00",
        "response_description": "Approved",
        "mode": "SANDBOX_MOCK"
    }
