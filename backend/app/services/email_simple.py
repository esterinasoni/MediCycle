import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)
FROM_NAME = os.getenv("FROM_NAME", "MediCycle")

async def send_otp_email(email: str, otp_code: str, name: str = None):
    """Send OTP verification email"""
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Verify Your MediCycle Account</title></head>
    <body style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #0e6e4a;">Welcome to MediCycle!</h2>
        <p>Hi {name or 'there'},</p>
        <p>Your verification code is:</p>
        <div style="background: #e8f5ef; padding: 20px; text-align: center; font-size: 32px; font-weight: bold; letter-spacing: 5px;">
            {otp_code}
        </div>
        <p>This code expires in 10 minutes.</p>
        <p>If you didn't create this account, please ignore this email.</p>
        <hr>
        <p style="color: #4a6155; font-size: 12px;">MediCycle - Making medication management effortless.</p>
    </body>
    </html>
    """
    
    message = MIMEMultipart("alternative")
    message["Subject"] = "Verify Your MediCycle Account"
    message["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    message["To"] = email
    message.attach(MIMEText(html_content, "html"))
    
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)
        server.quit()
        print(f"OTP email sent to {email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise e
