# # app/services/email.py

# from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
# from pydantic import EmailStr
# from typing import Optional
# import os
# from dotenv import load_dotenv

# load_dotenv()

# # Email configuration
# conf = ConnectionConfig(
#     MAIL_USERNAME=os.getenv("SMTP_USER"),
#     MAIL_PASSWORD=os.getenv("SMTP_PASSWORD"),
#     MAIL_FROM=os.getenv("FROM_EMAIL", "noreply@medicycle.com"),
#     MAIL_PORT=int(os.getenv("SMTP_PORT", 587)),
#     MAIL_SERVER=os.getenv("SMTP_HOST", "smtp.gmail.com"),
#     MAIL_STARTTLS=True,
#     MAIL_SSL_TLS=False,
#     USE_CREDENTIALS=True,
#     VALIDATE_CERTS=True,
#     MAIL_FROM_NAME=os.getenv("FROM_NAME", "MediCycle")
# )

# async def send_otp_email(email: str, otp_code: str, name: Optional[str] = None):
#     """Send OTP verification email"""
    
#     html_content = f"""
#     <!DOCTYPE html>
#     <html>
#     <head>
#         <meta charset="UTF-8">
#         <meta name="viewport" content="width=device-width, initial-scale=1.0">
#         <title>Verify Your MediCycle Account</title>
#         <style>
#             body {{
#                 font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
#                 line-height: 1.6;
#                 color: #111a14;
#                 background-color: #faf8f3;
#                 margin: 0;
#                 padding: 0;
#             }}
#             .container {{
#                 max-width: 560px;
#                 margin: 40px auto;
#                 background: white;
#                 border-radius: 24px;
#                 overflow: hidden;
#                 box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
#             }}
#             .header {{
#                 background: linear-gradient(135deg, #0a4a32, #0e6e4a);
#                 padding: 32px 24px;
#                 text-align: center;
#             }}
#             .logo {{
#                 font-size: 28px;
#                 font-weight: 700;
#                 color: white;
#             }}
#             .logo span {{
#                 color: #f4a935;
#             }}
#             .content {{
#                 padding: 32px 24px;
#             }}
#             .otp-code {{
#                 background: #e8f5ef;
#                 border-radius: 12px;
#                 padding: 20px;
#                 text-align: center;
#                 margin: 24px 0;
#             }}
#             .code {{
#                 font-family: monospace;
#                 font-size: 32px;
#                 font-weight: 700;
#                 letter-spacing: 8px;
#                 color: #0e6e4a;
#             }}
#             .button {{
#                 display: inline-block;
#                 background: #0e6e4a;
#                 color: white;
#                 padding: 12px 24px;
#                 border-radius: 8px;
#                 text-decoration: none;
#                 font-weight: 600;
#                 margin: 16px 0;
#             }}
#             .footer {{
#                 padding: 24px;
#                 text-align: center;
#                 background: #faf8f3;
#                 font-size: 12px;
#                 color: #4a6155;
#                 border-top: 1px solid #e0e8e4;
#             }}
#             .warning {{
#                 background: #fff9e6;
#                 border-left: 4px solid #f4a935;
#                 padding: 12px 16px;
#                 margin: 16px 0;
#                 font-size: 13px;
#                 color: #7a5c00;
#             }}
#         </style>
#     </head>
#     <body>
#         <div class="container">
#             <div class="header">
#                 <div class="logo">Medi<span>Cycle</span></div>
#                 <p style="color: rgba(255,255,255,0.9); margin-top: 8px;">Your Health, Automated</p>
#             </div>
#             <div class="content">
#                 <h2 style="margin-bottom: 8px;">Welcome to MediCycle! [WAVE]</h2>
#                 <p>Hi {name or 'there'},</p>
#                 <p>Thank you for signing up for MediCycle -- your automated medication refill platform.</p>
#                 <p>To complete your registration, please verify your email address using the code below:</p>
                
#                 <div class="otp-code">
#                     <div style="font-size: 14px; color: #4a6155; margin-bottom: 8px;">Your Verification Code</div>
#                     <div class="code">{otp_code}</div>
#                     <div style="font-size: 12px; color: #4a6155; margin-top: 8px;">Valid for 10 minutes</div>
#                 </div>
                
#                 <div class="warning">
#                     [!] <strong>Security Notice:</strong> Never share this code with anyone. MediCycle will never ask for this code outside of this verification process.
#                 </div>
                
#                 <p style="margin-top: 24px;">If you didn't create this account, please ignore this email.</p>
#                 <p>Need help? <a href="mailto:support@medicycle.com" style="color: #0e6e4a;">Contact Support</a></p>
#             </div>
#             <div class="footer">
#                 <p>MediCycle -- Making medication management effortless.</p>
#                 <p>&copy; 2024 MediCycle. All rights reserved.</p>
#             </div>
#         </div>
#     </body>
#     </html>
#     """
    
#     message = MessageSchema(
#         subject="[LOCK] Verify Your MediCycle Account",
#         recipients=[email],
#         body=html_content,
#         subtype="html"
#     )
    
#     fm = FastMail(conf)
#     await fm.send_message(message)
#     print(f"[OK] OTP email sent to {email}")

# async def send_test_email(email: str):
#     """Send a test email to verify configuration"""
#     html_content = """
#     <h2>Test Email from MediCycle</h2>
#     <p>If you're reading this, your email configuration is working correctly! [OK]</p>
#     """
    
#     message = MessageSchema(
#         subject="MediCycle - Test Email",
#         recipients=[email],
#         body=html_content,
#         subtype="html"
#     )
    
#     fm = FastMail(conf)
#     await fm.send_message(message)