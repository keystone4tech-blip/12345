import asyncio
import os
import sys

# Add bot directory to path to import app
sys.path.append(os.path.join(os.getcwd(), 'bot'))

from app.database.database import get_db
from app.database.crud.user import get_user_by_telegram_id

async def find_user():
    tg_id = 6521050178
    async for db in get_db():
        user = await get_user_by_telegram_id(db, tg_id)
        if user:
            print(f"User found: ID={user.id}, TG_ID={user.telegram_id}, Name={user.full_name}")
        else:
            print(f"User with TG_ID {tg_id} not found in database.")
        break

if __name__ == "__main__":
    asyncio.run(find_user())
