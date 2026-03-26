import asyncio
import sys
sys.path.append('.')  # Add current directory to path

from app.services.email import send_test_email

async def test():
    try:
        await send_test_email("phylliskemuma6@gmail.com")
        print("✅ Test email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send test email: {e}")

if __name__ == "__main__":
    asyncio.run(test())