import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

# Try to import Google Gemini
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    MODEL = "gemini-2.0-flash-lite"
    print("? Google Gemini loaded successfully")
except ImportError as e:
    GEMINI_AVAILABLE = False
    print(f"?? Google Gemini not available: {e}")
    print("AI parsing features will be disabled")
except Exception as e:
    GEMINI_AVAILABLE = False
    print(f"?? Error loading Gemini: {e}")

def parse_prescription_text(text: str) -> dict:
    """
    Use Gemini to extract medication details from prescription text.
    Falls back to simple parsing if Gemini not available.
    """
    if not GEMINI_AVAILABLE:
        # Simple fallback parsing
        return fallback_parse_text(text)
    
    prompt = f"""
    You are a medical prescription parser for MediCycle, a Nigerian medication refill platform.
    
    Extract the following information from this prescription text and return ONLY a JSON object.
    No explanation, no markdown, just raw JSON.
    
    Extract:
    - medication_name: the drug name
    - dosage: strength/dose (e.g. "5mg", "500mg", "10mg/5ml")
    - frequency: how many times per day as a number (e.g. 1, 2, 3)
    - total_quantity: total pills/units dispensed as a number
    - duration_days: how many days supply
    - instructions: any special instructions (e.g. "take with food")
    
    If a field cannot be found, use null.
    
    Prescription text:
    {text}
    
    Return only this JSON format:
    {{
        "medication_name": "...",
        "dosage": "...",
        "frequency": 1,
        "total_quantity": 30,
        "duration_days": 30,
        "instructions": "..."
    }}
    """

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )
        raw = response.text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)
        return {"success": True, "data": data}

    except json.JSONDecodeError:
        return {"success": False, "error": "Could not parse Gemini response as JSON"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def fallback_parse_text(text: str) -> dict:
    """
    Simple fallback parsing when Gemini is not available
    """
    data = {
        "medication_name": None,
        "dosage": None,
        "frequency": None,
        "total_quantity": None,
        "duration_days": None,
        "instructions": None
    }
    
    # Simple regex patterns for fallback
    patterns = {
        "medication_name": r'(?:medication|medicine|drug|rx)[:\s]+([A-Za-z]+)',
        "dosage": r'(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml)',
        "frequency": r'(\d+)\s*(?:times?|x)\s*(?:daily|per day|day)',
        "total_quantity": r'(?:quantity|qty|dispense)[:\s]+(\d+)',
        "duration_days": r'(\d+)\s*(?:days?|day)'
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if key == "frequency" or key == "total_quantity" or key == "duration_days":
                try:
                    data[key] = int(match.group(1))
                except:
                    pass
            else:
                data[key] = match.group(1)
    
    return {"success": True, "data": data}


def parse_prescription_image(image_path: str) -> dict:
    """
    Use Gemini Vision to extract medication details from images.
    """
    if not GEMINI_AVAILABLE:
        return {"success": False, "error": "Gemini AI not available for image parsing", "data": {}}
    
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        ext = image_path.split(".")[-1].lower()
        mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "pdf": "application/pdf"}
        mime_type = mime_map.get(ext, "image/jpeg")

        prompt = """
        You are a medical prescription parser for MediCycle, a Nigerian medication refill platform.
        
        Look at this prescription image and extract medication information.
        Return ONLY a JSON object with no explanation or markdown.
        
        Extract:
        - medication_name: the drug name
        - dosage: strength/dose (e.g. "5mg", "500mg")
        - frequency: how many times per day as a number
        - total_quantity: total pills/units as a number
        - duration_days: days supply as a number
        - instructions: special instructions
        - doctor_name: prescribing doctor if visible
        - prescription_date: date if visible (YYYY-MM-DD format)
        
        If a field cannot be found, use null.
        
        Return only this JSON format:
        {
            "medication_name": "...",
            "dosage": "...",
            "frequency": 1,
            "total_quantity": 30,
            "duration_days": 30,
            "instructions": "...",
            "doctor_name": "...",
            "prescription_date": "..."
        }
        """

        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt
            ]
        )

        raw = response.text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)
        return {"success": True, "data": data}

    except json.JSONDecodeError:
        return {"success": False, "error": "Could not parse Gemini response as JSON"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_medication_info(medication_name: str) -> dict:
    """
    Use Gemini to get general info about a medication.
    """
    if not GEMINI_AVAILABLE:
        return {
            "success": False,
            "data": {
                "generic_name": "Information unavailable",
                "common_use": "Please consult your healthcare provider",
                "important_notes": "AI service not available at this time",
                "common_side_effects": "Ask your pharmacist for details",
                "storage": "Store as directed on the prescription label"
            }
        }
    
    prompt = f"""
    You are a helpful medical assistant for MediCycle, a Nigerian medication refill platform.
    
    Provide a brief, patient-friendly summary of the medication: {medication_name}
    
    Return ONLY a JSON object with no explanation or markdown:
    {{
        "generic_name": "...",
        "common_use": "...",
        "important_notes": "...",
        "common_side_effects": "...",
        "storage": "..."
    }}
    
    Keep each field under 50 words. Use simple language a patient can understand.
    Do NOT provide dosage recommendations � that is the doctor's job.
    """

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )
        raw = response.text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)
        return {"success": True, "data": data}

    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_adherence_tip(
    medication_name: str,
    days_left: float,
    frequency: float
) -> str:
    """
    Generate a personalized adherence tip.
    """
    if not GEMINI_AVAILABLE:
        return f"Reminder: Take your {medication_name} as prescribed. Stay consistent! ??"
    
    prompt = f"""
    Write a single short, friendly SMS message (max 100 characters) 
    reminding a patient to take their {medication_name} ({frequency}x daily).
    They have {round(days_left)} days of supply left.
    Be warm, not scary. No hashtags. No emojis except one.
    Return only the message text, nothing else.
    """

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        return f"Reminder: Take your {medication_name} as prescribed. Stay consistent! ??"
