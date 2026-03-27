# app/services/email_simple.py

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
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verify Your MediCycle Account</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #111a14;
                background-color: #faf8f3;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 560px;
                margin: 40px auto;
                background: white;
                border-radius: 24px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            }}
            .header {{
                background: linear-gradient(135deg, #0a4a32, #0e6e4a);
                padding: 32px 24px;
                text-align: center;
            }}
            .logo {{
                font-size: 28px;
                font-weight: 700;
                color: white;
            }}
            .logo span {{
                color: #f4a935;
            }}
            .content {{
                padding: 32px 24px;
            }}
            .otp-code {{
                background: #e8f5ef;
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                margin: 24px 0;
            }}
            .code {{
                font-family: monospace;
                font-size: 32px;
                font-weight: 700;
                letter-spacing: 8px;
                color: #0e6e4a;
            }}
            .footer {{
                padding: 24px;
                text-align: center;
                background: #faf8f3;
                font-size: 12px;
                color: #4a6155;
                border-top: 1px solid #e0e8e4;
            }}
            .warning {{
                background: #fff9e6;
                border-left: 4px solid #f4a935;
                padding: 12px 16px;
                margin: 16px 0;
                font-size: 13px;
                color: #7a5c00;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">Medi<span>Cycle</span></div>
                <p style="color: rgba(255,255,255,0.9); margin-top: 8px;">Your Health, Automated</p>
            </div>
            <div class="content">
                <h2 style="margin-bottom: 8px;">Welcome to MediCycle! 👋</h2>
                <p>Hi {name or 'there'},</p>
                <p>Thank you for signing up for MediCycle — your automated medication refill platform.</p>
                <p>To complete your registration, please verify your email address using the code below:</p>
                
                <div class="otp-code">
                    <div style="font-size: 14px; color: #4a6155; margin-bottom: 8px;">Your Verification Code</div>
                    <div class="code">{otp_code}</div>
                    <div style="font-size: 12px; color: #4a6155; margin-top: 8px;">Valid for 10 minutes</div>
                </div>
                
                <div class="warning">
                    ⚠️ <strong>Security Notice:</strong> Never share this code with anyone. MediCycle will never ask for this code outside of this verification process.
                </div>
                
                <p style="margin-top: 24px;">If you didn't create this account, please ignore this email.</p>
                <p>Need help? <a href="mailto:support@medicycle.com" style="color: #0e6e4a;">Contact Support</a></p>
            </div>
            <div class="footer">
                <p>MediCycle — Making medication management effortless.</p>
                <p>&copy; 2024 MediCycle. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""
    Welcome to MediCycle!
    
    Hi {name or 'there'},
    
    Your verification code is: {otp_code}
    
    This code expires in 10 minutes.
    
    If you didn't create this account, please ignore this email.
    
    MediCycle — Your Health, Automated
    """
    
    # Create message
    message = MIMEMultipart("alternative")
    message["Subject"] = "🔐 Verify Your MediCycle Account"
    message["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    message["To"] = email
    
    # Add both plain text and HTML versions
    message.attach(MIMEText(text_content, "plain"))
    message.attach(MIMEText(html_content, "html"))
    
    try:
        # Connect to SMTP server
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)
        server.quit()
        print(f"✅ OTP email sent to {email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        raise e

async def send_test_email(email: str):
    """Send a test email to verify configuration"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>MediCycle Test Email</title>
    </head>
    <body style="font-family: Arial, sans-serif;">
        <div style="max-width: 500px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #0e6e4a;">MediCycle Test Email</h2>
            <p>If you're reading this, your email configuration is working correctly! ✅</p>
            <p>Your SMTP settings are properly configured.</p>
            <hr>
            <p style="color: #4a6155; font-size: 12px;">MediCycle - Making medication management effortless.</p>
        </div>
    </body>
    </html>
    """
    
    text_content = """
    MediCycle Test Email
    
    If you're reading this, your email configuration is working correctly! ✅
    
    Your SMTP settings are properly configured.
    
    MediCycle - Making medication management effortless.
    """
    
    message = MIMEMultipart("alternative")
    message["Subject"] = "MediCycle - Test Email"
    message["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    message["To"] = email
    message.attach(MIMEText(text_content, "plain"))
    message.attach(MIMEText(html_content, "html"))
    
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)
        server.quit()
        print(f"✅ Test email sent to {email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send test email: {e}")
        raise e