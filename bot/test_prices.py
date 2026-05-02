import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

sys.path.append('c:\\Users\\Keystone-Tech\\Desktop\\сервис рекламы с впн\\bot')
from app.config import settings, _DB_PERIOD_PRICES

async def main():
    print(f"SALES_MODE: {settings.SALES_MODE}")
    print(f"_DB_PERIOD_PRICES: {_DB_PERIOD_PRICES}")

asyncio.run(main())
