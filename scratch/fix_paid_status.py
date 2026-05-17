import asyncio
import os
import sys

# Add the project root to sys.path so we can import app modules
sys.path.insert(0, r'c:\Users\Keystone-Tech\Desktop\сервис рекламы с впн\bot')

from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.database.models import User, Subscription

async def main():
    async with AsyncSessionLocal() as db:
        query = select(User).join(Subscription).where(
            User.has_had_paid_subscription == False,
            Subscription.is_trial == False
        )
        result = await db.execute(query)
        users = result.scalars().all()
        
        print(f"Found {len(users)} users to fix.")
        
        for user in users:
            user.has_had_paid_subscription = True
            
        await db.commit()
        print("Done fixing.")

if __name__ == "__main__":
    asyncio.run(main())
