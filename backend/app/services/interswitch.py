import requests
import os
import base64
import uuid
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── CONFIG ──
CLIENT_ID = os.getenv("INTERSWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("INTERSWITCH_SECRET_KEY")  # matches your .env
MERCHANT_CODE = os.getenv("INTERSWITCH_MERCHANT_CODE")
PAYMENT_ITEM_ID = os.getenv("INTERSWITCH_PAYMENT_ITEM_ID")
ISW_ENV = os.getenv("INTERSWITCH_ENV", "sandbox")  # "sandbox" or "production"

# ── URLs per environment ──
URLS = {
    "sandbox": {
        "base": "https://qa.interswitchng.com",
        "passport": "https://qa.interswitchng.com/passport/oauth/token",
        "tokenize": "https://qa.interswitchng.com/api/v2/purchases/validations/recurrents",
        "charge": "https://qa.interswitchng.com/api/v2/purchases/recurrents",
        "verify": "https://qa.interswitchng.com/api/v2/purchases",
    },
    "production": {
        "base": "https://webpay.interswitchng.com",
        "passport": "https://passport.interswitchng.com/passport/oauth/token",
        "tokenize": "https://webpay.interswitchng.com/api/v2/purchases/validations/recurrents",
        "charge": "https://webpay.interswitchng.com/api/v2/purchases/recurrents",
        "verify": "https://webpay.interswitchng.com/api/v2/purchases",
    }
}

ACTIVE = URLS.get(ISW_ENV, URLS["sandbox"])

# ── TOKEN CACHE (avoids fetching a new token on every request) ──
_token_cache = {"token": None, "expires_at": 0}


def generate_ref(prefix="medicycle"):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique = str(uuid.uuid4())[:8].upper()
    return f"{prefix}_{timestamp}_{unique}"


# ── GET ACCESS TOKEN (cached) ──
def get_access_token():
    """Fetch OAuth2 token from Interswitch. Cached for 55 minutes."""
    now = time.time()

    # Return cached token if still valid
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()

        response = requests.post(
            ACTIVE["passport"],
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            data={"grant_type": "client_credentials"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)

        # Cache it with a 5-minute safety buffer
        _token_cache["token"] = token
        _token_cache["expires_at"] = now + expires_in - 300

        return token

    except Exception as e:
        print(f"[Interswitch] Token error: {e}")
        return None


# ── TOKENIZE CARD ──
def tokenize_card(auth_data: str, transaction_ref: str = None):
    """
    Tokenize patient card for recurring charges.
    auth_data: encrypted card data from Interswitch JS SDK on frontend.
    """
    try:
        access_token = get_access_token()
        if not access_token:
            return {"success": False, "error": "Could not get access token"}

        ref = transaction_ref or generate_ref("tokenize")

        response = requests.post(
            ACTIVE["tokenize"],
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
            token = data.get("token")
            if not token:
                return {
                    "success": False,
                    "error": "Tokenization succeeded but no token returned",
                    "raw": data
                }
            return {
                "success": True,
                "token": token,
                "token_expiry": data.get("tokenExpiryDate"),
                "transaction_ref": ref
            }
        else:
            return {
                "success": False,
                "error": data.get("description", "Tokenization failed"),
                "code": response.status_code,
                "raw": data
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── CHARGE PATIENT (recurring) ──
def charge_patient(
    token: str,
    token_expiry: str,
    amount_kobo: int,
    customer_id: str,
    prescription_id: int
):
    """
    Charge saved card token. 
    [!]  HTTP 200 is NOT enough -- always check responseCode == "00".
    """
    try:
        access_token = get_access_token()
        if not access_token:
            return {"success": False, "error": "Could not get access token"}

        ref = generate_ref(f"refill_{prescription_id}")

        response = requests.post(
            ACTIVE["charge"],
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "customerId": str(customer_id),
                "amount": str(amount_kobo),
                "currency": "NGN",
                "token": token,
                "transactionRef": ref, 
                "tokenExpiryDate": token_expiry,
                "transferRef": ref,
                "requestRef": ref,
            },
            timeout=30
        )

        data = response.json()
        response_code = data.get("responseCode") or data.get("ResponseCode", "")

        # [OK] HTTP 200 + responseCode "00" = genuine success
        if response.status_code in [200, 201] and response_code == "00":
            return {
                "success": True,
                "reference": ref,
                "amount_kobo": amount_kobo,
                "amount_naira": amount_kobo / 100,
                "response_code": response_code,
                "response_description": data.get("responseDescription", "Approved"),
                "mode": ISW_ENV.upper()
            }

        # HTTP 200 but bad response code = declined (common with Interswitch)
        error_msg = (
            data.get("responseDescription")
            or data.get("description")
            or f"Payment declined (code: {response_code})"
        )
        return {
            "success": False,
            "error": error_msg,
            "response_code": response_code,
            "raw": data
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── VERIFY TRANSACTION ──
def verify_transaction(transaction_ref: str):
    """
    Verify a recurring charge by transaction reference.
    Always call this before marking any payment as complete.
    """
    try:
        access_token = get_access_token()
        if not access_token:
            return {"verified": False, "error": "Could not get access token"}

        response = requests.get(
            f"{ACTIVE['verify']}/{transaction_ref}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        data = response.json()
        response_code = data.get("responseCode") or data.get("ResponseCode", "")

        if response_code == "00":
            return {
                "verified": True,
                "amount": data.get("amount"),
                "reference": transaction_ref,
                "raw": data
            }

        return {
            "verified": False,
            "response_code": response_code,
            "error": data.get("responseDescription", "Transaction not verified"),
            "raw": data
        }

    except Exception as e:
        return {"verified": False, "error": str(e)}


# ── MOCK (sandbox demo only) ──
def mock_charge_success(amount_kobo: int, prescription_id: int):
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