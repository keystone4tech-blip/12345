import asyncio
from app.config import settings

async def main():
    print(f"ADMIN_IDS: {settings.ADMIN_IDS}")
    print(f"get_admin_ids(): {settings.get_admin_ids()}")

if __name__ == "__main__":
    asyncio.run(main())
