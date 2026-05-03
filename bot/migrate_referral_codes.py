import asyncio
import structlog
from sqlalchemy import select, update
from app.database.session import AsyncSessionLocal
from app.database.models import User

logger = structlog.get_logger(__name__)

async def migrate_referral_codes():
    async with AsyncSessionLocal() as db:
        # 1. Получаем всех активных пользователей, у которых код начинается на 'ref'
        result = await db.execute(
            select(User).where(User.referral_code.like('ref%'), User.telegram_id.isnot(None))
        )
        users = result.scalars().all()
        
        print(f"Найдено {len(users)} пользователей для миграции кодов.")
        
        updated_count = 0
        for user in users:
            new_code = str(user.telegram_id)
            
            # Проверяем, не занят ли уже такой код кем-то другим
            check_res = await db.execute(select(User).where(User.referral_code == new_code))
            if check_res.scalar_one_or_none():
                print(f"Пропуск пользователя {user.id}: код {new_code} уже занят.")
                continue
                
            # Обновляем
            user.referral_code = new_code
            updated_count += 1
            
        await db.commit()
        print(f"Успешно обновлено {updated_count} кодов.")

if __name__ == "__main__":
    asyncio.run(migrate_referral_codes())
