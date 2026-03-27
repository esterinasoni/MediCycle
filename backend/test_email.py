# test_email.py

import asyncio
import sys
import os

# Add the current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Change this line:
# from app.services.email import send_test_email

# To this:
from app.services.email_simple import send_test_email

async def test():
    try:
        # Replace with your email address
        await send_test_email("phylliskemuma6@gmail.com")
        print("✅ Test email sent successfully!")
        print("Check your inbox (and spam folder)")
    except Exception as e:
        print(f"❌ Failed to send test email: {e}")
        print("\nMake sure your .env file has:")
        print("SMTP_USER=your-email@gmail.com")
        print("SMTP_PASSWORD=your-app-password")

if __name__ == "__main__":
    asyncio.run(test())