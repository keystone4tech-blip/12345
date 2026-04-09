import uuid
import structlog
from datetime import datetime, UTC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database.models import Gift, User, Tariff
from app.database.crud.subscription import create_paid_subscription, extend_subscription, get_subscription_by_user_id
from app.services.subscription_service import SubscriptionService

logger = structlog.get_logger(__name__)

class GiftService:
    @staticmethod
    async def get_gift_by_token(db: AsyncSession, token: str) -> dict | None:
        """Получить информацию о подарке по токену."""
        query = (
            select(Gift)
            .options(joinedload(Gift.gifter), joinedload(Gift.tariff))
            .where(Gift.token == token, Gift.is_used == False)
        )
        result = await db.execute(query)
        gift = result.scalar_one_or_none()
        
        if not gift:
            return None
            
        return {
            "token": gift.token,
            "tariff_name": gift.tariff.name if gift.tariff else "VPN",
            "period_days": gift.period_days,
            "gifter_name": gift.gifter.full_name if gift.gifter else "Друг",
            "gifter_id": gift.gifter_id
        }

    @staticmethod
    async def create_gift(
        db: AsyncSession,
        tariff_id: int,
        period_days: int,
        gifter_id: int | None = None
    ) -> str:
        """Создать новый подарок в БД и вернуть токен."""
        token = uuid.uuid4().hex[:12]
        new_gift = Gift(
            token=token,
            tariff_id=tariff_id,
            period_days=period_days,
            gifter_id=gifter_id
        )
        db.add(new_gift)
        await db.commit()
        logger.info("🎁 Подарок создан в БД", token=token, tariff_id=tariff_id)
        return token

    @staticmethod
    async def activate_gift(
        db: AsyncSession,
        user: User,
        token: str,
        bot=None
    ) -> dict:
        """Активировать подарок по токену для указанного пользователя."""
        # Ищем подарок в БД с подгрузкой дарителя
        query = (
            select(Gift)
            .options(joinedload(Gift.gifter))
            .where(Gift.token == token, Gift.is_used == False)
        )
        result = await db.execute(query)
        gift = result.scalar_one_or_none()

        if not gift:
            logger.warning("⚠️ Подарок не найден или уже использован", token=token, user_id=user.id)
            return {"success": False, "error": "invalid_token"}

        # Ищем тариф
        query_tariff = select(Tariff).where(Tariff.id == gift.tariff_id)
        res_tariff = await db.execute(query_tariff)
        tariff = res_tariff.scalar_one_or_none()
        
        if not tariff:
            logger.error("❌ Тариф подарка не найден", tariff_id=gift.tariff_id)
            return {"success": False, "error": "tariff_not_found"}

        try:
            # Логика активации подписки
            current_sub = await get_subscription_by_user_id(db, user.id)
            
            # Определяем список серверов (сквадов) из тарифа для назначения
            # В текущем проекте это поле может называться allowed_squads или squads
            connected_squads = getattr(tariff, 'allowed_squads', [])

            if current_sub:
                subscription = await extend_subscription(
                    db=db,
                    subscription=current_sub,
                    days=gift.period_days,
                    tariff_id=tariff.id,
                    traffic_limit_gb=tariff.traffic_limit_gb,
                    device_limit=tariff.device_limit,
                    connected_squads=connected_squads
                )
            else:
                subscription = await create_paid_subscription(
                    db=db,
                    user_id=user.id,
                    duration_days=gift.period_days,
                    traffic_limit_gb=tariff.traffic_limit_gb,
                    device_limit=tariff.device_limit,
                    tariff_id=tariff.id,
                    connected_squads=connected_squads,
                    update_server_counters=True
                )

            # Синхронизация с сервером
            sub_service = SubscriptionService()
            if user.remnawave_uuid:
                await sub_service.update_remnawave_user(db, subscription)
            else:
                await sub_service.create_remnawave_user(db, subscription)

            # Извлекаем необходимые данные ДО коммита
            gifter_tg_id = gift.gifter.telegram_id if gift.gifter else None
            recipient_name = user.full_name or f"ID {user.id}"
            tariff_name = tariff.name

            # Отмечаем подарок как использованный
            gift.is_used = True
            gift.recipient_id = user.id
            gift.activated_at = datetime.now(UTC)
            
            # Пользователь теперь имеет платную подписку
            user.has_had_paid_subscription = True
            
            await db.commit()

            # Уведомляем дарителя
            if gifter_tg_id and bot:
                try:
                    await bot.send_message(
                        chat_id=gifter_tg_id,
                        text=f"✅ <b>Ваш подарок успешно получен!</b>\n\nПользователь {recipient_name} активировал подаренный вами тариф {tariff_name}.",
                        parse_mode='HTML',
                        message_effect_id='5107584321108051014' # Эффект "Лайк" 👍
                    )
                except Exception as e:
                    logger.error("Ошибка уведомления дарителя", gifter_tg_id=gifter_tg_id, error=e)

            logger.info("🎁 Подарок успешно активирован", token=token, user_id=user.id)
            return {
                "success": True, 
                "tariff_name": tariff.name, 
                "period": gift.period_days
            }

        except Exception as e:
            await db.rollback()
            logger.error("❌ Ошибка при активации подарка", token=token, error=e)
            return {"success": False, "error": str(e)}

    @staticmethod
    async def get_user_gift_history(db: AsyncSession, user_id: int, limit: int = 5) -> list[dict]:
        """Получить историю подарков пользователя."""
        query = (
            select(Gift)
            .options(joinedload(Gift.recipient), joinedload(Gift.tariff))
            .where(Gift.gifter_id == user_id)
            .order_by(Gift.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        gifts = result.scalars().all()
        
        history = []
        for g in gifts:
            history.append({
                "token": g.token,
                "tariff_name": g.tariff.name if g.tariff else "VPN",
                "period_days": g.period_days,
                "is_used": g.is_used,
                "recipient_name": g.recipient.full_name if g.recipient else None,
                "created_at": g.created_at
            })
        return history
