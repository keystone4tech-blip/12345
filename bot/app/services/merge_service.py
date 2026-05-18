"""Сервис слияния учетных записей (Account Merge Service)."""

import json
import uuid
import structlog
from datetime import datetime, UTC
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User, Subscription
import redis.asyncio as redis

# Инициализируем структурированное логирование проекта
logger = structlog.get_logger(__name__)

class MergeService:
    """Сервис для управления токенами слияния и транзакционного слияния аккаунтов."""

    def __init__(self):
        self._redis_client: redis.Redis | None = None

    def _get_redis_client(self) -> redis.Redis | None:
        """Ленивая инициализация Redis-клиента для graceful fallback при сбое Redis."""
        if self._redis_client is not None:
            return self._redis_client
        try:
            self._redis_client = redis.from_url(settings.REDIS_URL)
            logger.debug("🧠 MERGE: Redis-клиент успешно инициализирован")
        except Exception as e:
            logger.warning("⚠️ MERGE: Не удалось подключиться к Redis", error=e)
            self._redis_client = None
        return self._redis_client

    async def create_merge_token(self, primary_id: int, secondary_id: int) -> str:
        """
        Создает временный токен слияния аккаунтов в Redis.
        Срок действия: 15 минут (900 секунд).
        """
        token = f"merge_{uuid.uuid4().hex}"
        redis_key = f"merge_token:{token}"
        data = {
            "primary_id": primary_id,
            "secondary_id": secondary_id,
            "created_at": datetime.now(UTC).isoformat()
        }
        
        client = self._get_redis_client()
        if client:
            try:
                await client.setex(redis_key, 900, json.dumps(data))
                logger.info(
                    "📝 MERGE: Токен слияния успешно создан в Redis",
                    token=token,
                    primary_id=primary_id,
                    secondary_id=secondary_id,
                    ttl_seconds=900
                )
            except Exception as e:
                logger.error("❌ MERGE: Ошибка сохранения токена в Redis", error=e)
                raise RuntimeError("Ошибка сохранения данных авторизации") from e
        else:
            logger.error("❌ MERGE: Redis недоступен, невозможно создать токен слияния")
            raise RuntimeError("Сервер авторизации временно недоступен")
            
        return token

    async def get_merge_data(self, token: str) -> dict | None:
        """Получает данные слияния по токену из Redis."""
        redis_key = f"merge_token:{token}"
        client = self._get_redis_client()
        if not client:
            logger.error("❌ MERGE: Redis недоступен при получении токена")
            return None
            
        try:
            raw_data = await client.get(redis_key)
            if not raw_data:
                logger.warning("⚠️ MERGE: Запрошенный токен слияния истек или не существует", token=token)
                return None
            return json.loads(raw_data)
        except Exception as e:
            logger.error("❌ MERGE: Ошибка чтения токена из Redis", error=e)
            return None

    async def delete_merge_token(self, token: str) -> None:
        """Удаляет использованный токен слияния из Redis."""
        redis_key = f"merge_token:{token}"
        client = self._get_redis_client()
        if client:
            try:
                await client.delete(redis_key)
                logger.info("🗑️ MERGE: Использованный токен удален из Redis", token=token)
            except Exception as e:
                logger.warning("⚠️ MERGE: Не удалось удалить токен из Redis", error=e)

    async def execute_merge_accounts(
        self, db: AsyncSession, token: str, keep_subscription_from_user_id: int
    ) -> User:
        """
        Выполняет транзакционное слияние двух учетных записей пользователей.
        Все связанные данные переносятся на основной аккаунт, а вторичный аккаунт удаляется.
        """
        # Получаем данные токена
        merge_data = await self.get_merge_data(token)
        if not merge_data:
            raise ValueError("Токен слияния истек или недействителен")

        primary_id = merge_data["primary_id"]
        secondary_id = merge_data["secondary_id"]

        logger.info(
            "🔄 MERGE: Запуск процесса слияния аккаунтов",
            primary_id=primary_id,
            secondary_id=secondary_id,
            keep_sub_from=keep_subscription_from_user_id
        )

        # Запрашиваем обоих пользователей из БД
        primary_user = (await db.execute(select(User).where(User.id == primary_id))).scalar_one_or_none()
        secondary_user = (await db.execute(select(User).where(User.id == secondary_id))).scalar_one_or_none()

        if not primary_user or not secondary_user:
            raise ValueError("Один или оба аккаунта не найдены в системе")

        # 1. Объединяем балансы
        old_balance = primary_user.balance_kopeks
        primary_user.balance_kopeks += secondary_user.balance_kopeks
        logger.info(
            "💰 MERGE: Балансы пользователей объединены",
            primary_user_id=primary_id,
            old_balance_kopeks=old_balance,
            added_kopeks=secondary_user.balance_kopeks,
            new_balance_kopeks=primary_user.balance_kopeks
        )

        # 2. Переносим реферальный статус (referred_by_id)
        if not primary_user.referred_by_id and secondary_user.referred_by_id:
            if secondary_user.referred_by_id != primary_user.id:
                primary_user.referred_by_id = secondary_user.referred_by_id
                logger.info(
                    "👤 MERGE: Перенесен вышестоящий реферер",
                    primary_user_id=primary_id,
                    referred_by_id=primary_user.referred_by_id
                )

        # 3. Переносим флаг платной подписки
        if secondary_user.has_had_paid_subscription:
            primary_user.has_had_paid_subscription = True

        # 4. Копируем недостающие привязки соцсетей и авторизационные поля
        fields_to_copy = [
            "telegram_id", "username", "first_name", "last_name", 
            "email", "email_verified", "email_verified_at", "password_hash",
            "google_id", "yandex_id", "discord_id", "vk_id",
            "remnawave_uuid", "trojan_password", "vless_uuid", "ss_password"
        ]
        
        for field in fields_to_copy:
            primary_val = getattr(primary_user, field)
            secondary_val = getattr(secondary_user, field)
            if primary_val is None and secondary_val is not None:
                setattr(primary_user, field, secondary_val)
                logger.info(f"🔗 MERGE: Поле '{field}' перенесено", primary_user_id=primary_id, value=secondary_val)

        # 5. Обработка подписки (Subscription)
        sub_p = (await db.execute(select(Subscription).where(Subscription.user_id == primary_id))).scalar_one_or_none()
        sub_s = (await db.execute(select(Subscription).where(Subscription.user_id == secondary_id))).scalar_one_or_none()

        if keep_subscription_from_user_id == primary_id:
            # Сохраняем первичную подписку
            if sub_s:
                logger.info("🗑️ MERGE: Удаляем невыбранную подписку вторичного аккаунта", secondary_sub_id=sub_s.id)
                await db.delete(sub_s)
        elif keep_subscription_from_user_id == secondary_id:
            # Сохраняем вторичную подписку
            if sub_p:
                logger.info("🗑️ MERGE: Удаляем невыбранную подписку первичного аккаунта", primary_sub_id=sub_p.id)
                await db.delete(sub_p)
            if sub_s:
                sub_s.user_id = primary_id
                logger.info("⚡ MERGE: Подписка вторичного аккаунта привязана к основному", sub_id=sub_s.id, user_id=primary_id)
        else:
            raise ValueError("Некорректный ID для сохранения подписки")

        # 6. Разрешаем конфликты и переносим данные во всех дочерних таблицах через транзакционный SQL
        
        # Удаляем дублирующиеся уникальные записи для secondary_id перед апдейтом
        # А. user_promo_groups
        await db.execute(text(
            "DELETE FROM user_promo_groups WHERE user_id = :sec_id AND promo_group_id IN "
            "(SELECT promo_group_id FROM user_promo_groups WHERE user_id = :prim_id)"
        ), {"sec_id": secondary_id, "prim_id": primary_id})
        
        # Б. poll_responses
        await db.execute(text(
            "DELETE FROM poll_responses WHERE user_id = :sec_id AND poll_id IN "
            "(SELECT poll_id FROM poll_responses WHERE user_id = :prim_id)"
        ), {"sec_id": secondary_id, "prim_id": primary_id})
        
        # В. user_roles
        await db.execute(text(
            "DELETE FROM user_roles WHERE user_id = :sec_id AND role_id IN "
            "(SELECT role_id FROM user_roles WHERE user_id = :prim_id)"
        ), {"sec_id": secondary_id, "prim_id": primary_id})

        # Г. Удаляем сессионные refresh токены вторичного аккаунта, чтобы завершить все сессии
        await db.execute(text("DELETE FROM cabinet_refresh_tokens WHERE user_id = :sec_id"), {"sec_id": secondary_id})

        # Перенаправляем все внешние ключи с secondary_id на primary_id
        update_queries = [
            # Платежи
            ("UPDATE yookassa_payments SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE cryptobot_payments SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE heleket_payments SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE mulenpay_payments SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE pal24_payments SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE wata_payments SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE platega_payments SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE cloudpayments_payments SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE freekassa_payments SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE kassa_ai_payments SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            
            # Промо-группы и роли
            ("UPDATE user_promo_groups SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE user_roles SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE user_roles SET assigned_by = :prim_id WHERE assigned_by = :sec_id", {}),
            ("UPDATE admin_roles SET created_by = :prim_id WHERE created_by = :sec_id", {}),
            ("UPDATE access_policies SET created_by = :prim_id WHERE created_by = :sec_id", {}),
            
            # Рефералы и начисления
            ("UPDATE users SET referred_by_id = :prim_id WHERE referred_by_id = :sec_id", {}),
            ("UPDATE referral_earnings SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE referral_earnings SET referral_id = :prim_id WHERE referral_id = :sec_id", {}),
            ("UPDATE promocode_uses SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE promocodes SET created_by = :prim_id WHERE created_by = :sec_id", {}),
            
            # Выплаты и конкурсы
            ("UPDATE withdrawal_requests SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE withdrawal_requests SET processed_by = :prim_id WHERE processed_by = :sec_id", {}),
            ("UPDATE partner_applications SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE partner_applications SET processed_by = :prim_id WHERE processed_by = :sec_id", {}),
            ("UPDATE referral_contests SET created_by = :prim_id WHERE created_by = :sec_id", {}),
            ("UPDATE referral_contest_events SET referrer_id = :prim_id WHERE referrer_id = :sec_id", {}),
            ("UPDATE referral_contest_events SET referral_id = :prim_id WHERE referral_id = :sec_id", {}),
            ("UPDATE contest_attempts SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            
            # Финансовые транзакции
            ("UPDATE transactions SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            
            # Подписки и рекламные кампании
            ("UPDATE subscription_conversions SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE subscription_events SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE discount_offers SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE promo_offer_logs SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE promo_offer_templates SET created_by = :prim_id WHERE created_by = :sec_id", {}),
            ("UPDATE advertising_campaigns SET partner_user_id = :prim_id WHERE partner_user_id = :sec_id", {}),
            ("UPDATE advertising_campaigns SET created_by = :prim_id WHERE created_by = :sec_id", {}),
            ("UPDATE advertising_campaign_registrations SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            
            # Поддержка и сообщения
            ("UPDATE tickets SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE ticket_messages SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE ticket_notifications SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE user_messages SET created_by = :prim_id WHERE created_by = :sec_id", {}),
            ("UPDATE welcome_texts SET created_by = :prim_id WHERE created_by = :sec_id", {}),
            ("UPDATE pinned_messages SET created_by = :prim_id WHERE created_by = :sec_id", {}),
            ("UPDATE sent_notifications SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE support_audit_logs SET actor_user_id = :prim_id WHERE actor_user_id = :sec_id", {}),
            ("UPDATE support_audit_logs SET target_user_id = :prim_id WHERE target_user_id = :sec_id", {}),
            ("UPDATE forum_tickets SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            
            # Логирование, аудит и колесо фортуны
            ("UPDATE button_click_logs SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE wheel_spins SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE admin_audit_log SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            ("UPDATE broadcast_history SET admin_id = :prim_id WHERE admin_id = :sec_id", {}),
            ("UPDATE polls SET created_by = :prim_id WHERE created_by = :sec_id", {}),
            ("UPDATE poll_responses SET user_id = :prim_id WHERE user_id = :sec_id", {}),
            
            # Подарки VPN
            ("UPDATE gifts SET gifter_id = :prim_id WHERE gifter_id = :sec_id", {}),
            ("UPDATE gifts SET recipient_id = :prim_id WHERE recipient_id = :sec_id", {})
        ]

        # Запускаем все SQL-апдейты в рамках одной транзакции
        for query_str, params in update_queries:
            await db.execute(text(query_str), {"prim_id": primary_id, "sec_id": secondary_id})

        logger.info("📦 MERGE: Все внешние связи успешно перенаправлены на основной аккаунт")

        # 7. Наконец, удаляем вторичного пользователя из базы данных
        logger.info("🗑️ MERGE: Удаление дублирующего вторичного аккаунта", secondary_user_id=secondary_id)
        await db.delete(secondary_user = secondary_user)

        # Коммитим транзакцию
        await db.commit()

        # Удаляем использованный токен из Redis
        await self.delete_merge_token(token)

        logger.info("✅ MERGE: Слияние аккаунтов успешно выполнено!", primary_user_id=primary_id)
        
        # Обновляем состояние основного пользователя для возврата
        await db.refresh(primary_user)
        return primary_user
