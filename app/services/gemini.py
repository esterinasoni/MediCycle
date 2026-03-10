from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
import json
import re

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.0-flash-lite"

def parse_prescription_text(text: str) -> dict:
    """
    Use Gemini to extract medication details from
    raw prescription text (typed or OCR'd from image).
    """
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


def parse_prescription_image(image_path: str) -> dict:
    """
    Use Gemini Vision to extract medication details
    directly from a prescription image/photo.
    """
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
    Helps patients understand their prescription.
    """
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
    Do NOT provide dosage recommendations — that is the doctor's job.
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
    Generate a personalized adherence tip for the patient.
    Used in SMS notifications.
    """
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
        return f"Reminder: Take your {medication_name} as prescribed. Stay consistent! 💊"