"""
Сервис автоматического сбора отзывов пользователей.

Функционал:
- Ежедневная проверка пользователей по порогу трафика
- Отправка запросов на оставление отзыва
- Начисление бонусных дней за оценки и контент (текст/голос/видео)
- Синхронизация продлённых подписок с RemnaWave
"""

import asyncio
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, UTC, time as dt_time

import structlog
from aiogram import Bot
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.config import settings
from app.database.models import User, UserReview, Subscription, SubscriptionStatus

# Логгер модуля
logger = structlog.get_logger(__name__)


class ReviewsService:
    """Управление сбором отзывов и начислением наград."""

    def __init__(self):
        # Ссылка на бот (устанавливается при старте)
        self.bot: Bot | None = None
        # Фоновая задача шедулера
        self._task: asyncio.Task | None = None
        # Флаг работы
        self._running: bool = False

    # ──────────────────────────── Публичные методы ────────────────────────────

    def set_bot(self, bot: Bot) -> None:
        """Устанавливает экземпляр бота для отправки сообщений."""
        self.bot = bot

    def is_enabled(self) -> bool:
        """Проверяет, включена ли система отзывов в настройках."""
        return bool(settings.REVIEWS_ENABLED)

    def is_running(self) -> bool:
        """Возвращает True, если фоновая задача шедулера запущена."""
        return self._running and self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Запускает фоновый шедулер проверки отзывов."""
        if not self.is_enabled():
            logger.info('⭐ Система отзывов отключена настройками (REVIEWS_ENABLED=false)')
            return

        if self.is_running():
            logger.warning('⭐ Шедулер отзывов уже запущен, пропускаем повторный старт')
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info(
            '⭐ Шедулер отзывов запущен',
            check_time=settings.REVIEWS_CHECK_TIME,
            threshold_mb=settings.REVIEWS_TRAFFIC_THRESHOLD_MB,
        )

    async def stop(self) -> None:
        """Останавливает фоновый шедулер."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info('⭐ Шедулер отзывов остановлен')

    # ──────────────────────────── Награды ────────────────────────────

    def get_star_reward(self, rating: int) -> int:
        """Возвращает кол-во бонусных дней за оценку (1-5 звёзд)."""
        rewards = {
            1: settings.REVIEWS_REWARD_STAR_1,
            2: settings.REVIEWS_REWARD_STAR_2,
            3: settings.REVIEWS_REWARD_STAR_3,
            4: settings.REVIEWS_REWARD_STAR_4,
            5: settings.REVIEWS_REWARD_STAR_5,
        }
        return rewards.get(rating, 0)

    def get_content_reward(self, review_type: str) -> int:
        """Возвращает кол-во бонусных дней за тип контента."""
        rewards = {
            'text': settings.REVIEWS_REWARD_CONTENT_TEXT,
            'voice': settings.REVIEWS_REWARD_CONTENT_VOICE,
            'video_note': settings.REVIEWS_REWARD_CONTENT_VIDEO,
        }
        return rewards.get(review_type, 0)

    # ──────────────────────────── Работа с БД ────────────────────────────

    async def create_review(self, db: AsyncSession, user_id: int, rating: int) -> UserReview:
        """
        Создаёт запись отзыва после выбора оценки пользователем.

        Args:
            db: Сессия базы данных
            user_id: ID пользователя
            rating: Оценка от 1 до 5

        Returns:
            Созданный объект UserReview
        """
        # Вычисляем награду за звёзды
        star_days = self.get_star_reward(rating)

        review = UserReview(
            user_id=user_id,
            rating=rating,
            star_reward_days=star_days,
            content_reward_days=0,
            status='WAITING_FOR_CONTENT',
        )
        db.add(review)
        await db.commit()
        await db.refresh(review)

        logger.info(
            '⭐ Создан отзыв с оценкой',
            user_id=user_id,
            rating=rating,
            star_reward_days=star_days,
        )
        return review

    async def complete_review(
        self,
        db: AsyncSession,
        review: UserReview,
        review_type: str,
        content_id: str | None = None,
    ) -> int:
        """
        Завершает отзыв, добавляя контент и начисляя все бонусные дни.

        Args:
            db: Сессия базы данных
            review: Объект отзыва
            review_type: Тип контента ('text', 'voice', 'video_note', 'none')
            content_id: Telegram file_id медиа-файла (опционально)

        Returns:
            Общее количество начисленных бонусных дней
        """
        # Вычисляем награду за контент
        content_days = self.get_content_reward(review_type) if review_type != 'none' else 0

        # Обновляем запись
        review.review_type = review_type
        review.review_content_id = content_id
        review.content_reward_days = content_days
        review.status = 'COMPLETED'
        review.updated_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(review)

        # Общее количество бонусных дней
        total_days = review.star_reward_days + content_days

        logger.info(
            '⭐ Отзыв завершён',
            review_id=review.id,
            user_id=review.user_id,
            review_type=review_type,
            star_days=review.star_reward_days,
            content_days=content_days,
            total_days=total_days,
        )
        return total_days

    async def award_bonus_days(self, db: AsyncSession, user_id: int, days: int, bot: Bot) -> bool:
        """
        Начисляет бонусные дни к подписке пользователя и синхронизирует с RemnaWave.

        Args:
            db: Сессия базы данных
            user_id: ID пользователя
            days: Количество бонусных дней
            bot: Экземпляр Bot для уведомлений

        Returns:
            True если дни начислены успешно
        """
        if days <= 0:
            logger.debug('Пропуск начисления: 0 дней', user_id=user_id)
            return True

        try:
            # Импортируем CRUD-функции для работы с подписками
            from app.database.crud.subscription import (
                get_subscription_by_user_id,
                extend_subscription,
                create_trial_subscription,
            )
            from app.database.crud.user import get_user_by_id

            # Получаем пользователя
            user = await get_user_by_id(db, user_id)
            if not user:
                logger.error('⭐ Пользователь не найден для начисления бонуса', user_id=user_id)
                return False

            # Получаем текущую подписку
            sub = await get_subscription_by_user_id(db, user_id)
            if sub:
                # Продлеваем существующую подписку
                await extend_subscription(db, sub, days)
                logger.info('⭐ Подписка продлена за отзыв', user_id=user_id, days=days)
            else:
                # Создаём триальную подписку с бонусными днями
                await create_trial_subscription(db, user_id, duration_days=days)
                logger.info('⭐ Создана триал-подписка за отзыв', user_id=user_id, days=days)

            # Синхронизируем с RemnaWave
            try:
                from app.services.subscription_service import SubscriptionService

                subscription_service = SubscriptionService()
                await subscription_service.update_remnawave_user(db, user)
                logger.info('⭐ Синхронизация с RemnaWave после отзыва выполнена', user_id=user_id)
            except Exception as sync_err:
                logger.error(
                    '❌ Ошибка синхронизации с RemnaWave после отзыва',
                    user_id=user_id,
                    error=sync_err,
                )

            return True

        except Exception as e:
            logger.error('❌ Ошибка начисления бонусных дней за отзыв', user_id=user_id, error=e)
            return False

    async def get_pending_review(self, db: AsyncSession, user_id: int) -> UserReview | None:
        """Получает незавершённый отзыв пользователя (WAITING_FOR_CONTENT)."""
        result = await db.execute(
            select(UserReview)
            .where(
                and_(
                    UserReview.user_id == user_id,
                    UserReview.status == 'WAITING_FOR_CONTENT',
                )
            )
            .order_by(UserReview.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def has_recent_review(self, db: AsyncSession, user_id: int, days: int = 30) -> bool:
        """Проверяет, оставлял ли пользователь отзыв за последние N дней."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await db.execute(
            select(UserReview.id)
            .where(
                and_(
                    UserReview.user_id == user_id,
                    UserReview.created_at >= cutoff,
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_review_stats(self, db: AsyncSession) -> dict:
        """Возвращает общую статистику по отзывам для админ-панели."""
        from sqlalchemy import func

        # Общее количество отзывов
        total_q = await db.execute(select(func.count(UserReview.id)))
        total = total_q.scalar() or 0

        # Завершённые
        completed_q = await db.execute(
            select(func.count(UserReview.id)).where(UserReview.status == 'COMPLETED')
        )
        completed = completed_q.scalar() or 0

        # Средняя оценка
        avg_q = await db.execute(
            select(func.avg(UserReview.rating)).where(UserReview.rating.isnot(None))
        )
        avg_rating = round(avg_q.scalar() or 0, 1)

        # Общее количество начисленных дней
        days_q = await db.execute(
            select(
                func.sum(UserReview.star_reward_days + UserReview.content_reward_days)
            ).where(UserReview.status == 'COMPLETED')
        )
        total_days = days_q.scalar() or 0

        return {
            'total': total,
            'completed': completed,
            'pending': total - completed,
            'avg_rating': avg_rating,
            'total_reward_days': total_days,
        }

    # ──────────────────────────── Шедулер ────────────────────────────

    async def _scheduler_loop(self) -> None:
        """Основной цикл шедулера: ждёт время REVIEWS_CHECK_TIME, затем рассылает запросы."""
        logger.info('⭐ Цикл шедулера отзывов запущен')

        while self._running:
            try:
                # Получаем текущую локальную таймзону (например, из настроек)
                tz = ZoneInfo(settings.TIMEZONE)
                now_local = datetime.now(tz)
                check_time = self._parse_check_time()

                # Следующий запуск сегодня или завтра по локальному времени
                next_run_local = now_local.replace(
                    hour=check_time.hour,
                    minute=check_time.minute,
                    second=0,
                    microsecond=0,
                )
                if next_run_local <= now_local:
                    next_run_local += timedelta(days=1)

                wait_seconds = (next_run_local - now_local).total_seconds()

                # Спим максимум 60 секунд за итерацию, чтобы быстро подхватывать изменения настроек времени рассылки
                if wait_seconds > 60:
                    await asyncio.sleep(60)
                    continue

                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)

                # Проверяем, всё ещё включено ли
                if not self._running or not self.is_enabled():
                    continue

                # Выполняем рассылку
                await self._send_review_requests()
                
                # Спим 60 секунд после рассылки, чтобы не запустить её повторно в ту же минуту
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                logger.info('⭐ Шедулер отзывов отменён')
                break
            except Exception as e:
                logger.error('❌ Ошибка в цикле шедулера отзывов', error=e)
                # Ждём 60 секунд перед повторной попыткой
                await asyncio.sleep(60)

    def _parse_check_time(self) -> dt_time:
        """Парсит настройку REVIEWS_CHECK_TIME ('HH:MM') в объект time."""
        try:
            parts = settings.REVIEWS_CHECK_TIME.split(':')
            return dt_time(hour=int(parts[0]), minute=int(parts[1]))
        except Exception:
            logger.warning('⚠️ Некорректный формат REVIEWS_CHECK_TIME, используем 09:00')
            return dt_time(hour=9, minute=0)

    async def _send_review_requests(self) -> None:
        """
        Рассылает запросы на отзывы всем подходящим пользователям.

        Критерии отбора:
        - Активная подписка
        - Трафик >= REVIEWS_TRAFFIC_THRESHOLD_MB
        - Не оставляли отзыв за последние 30 дней
        """
        if not self.bot:
            logger.error('⭐ Бот не установлен, рассылка невозможна')
            return

        logger.info('⭐ Начинаем рассылку запросов на отзывы')

        try:
            from app.database.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                # Получаем пользователей с активными подписками
                eligible_users = await self._get_eligible_users(db)

                sent_count = 0
                error_count = 0

                for user in eligible_users:
                    try:
                        # Проверяем, есть ли telegram_id
                        if not user.telegram_id:
                            continue

                        # Проверяем, не оставлял ли уже отзыв
                        if await self.has_recent_review(db, user.id, days=30):
                            continue

                        # Отправляем запрос на отзыв
                        await self._send_single_request(user)
                        sent_count += 1

                        # Задержка между отправками (антифлуд)
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        error_count += 1
                        logger.error(
                            '❌ Ошибка отправки запроса на отзыв',
                            user_id=user.id,
                            error=e,
                        )

                logger.info(
                    '⭐ Рассылка запросов завершена',
                    sent=sent_count,
                    errors=error_count,
                    total_eligible=len(eligible_users),
                )

        except Exception as e:
            logger.error('❌ Критическая ошибка рассылки отзывов', error=e)

    async def _get_eligible_users(self, db: AsyncSession) -> list[User]:
        """Получает список пользователей, подходящих для запроса отзыва."""
        try:
            # Получаем пользователей с активной подпиской
            result = await db.execute(
                select(User)
                .join(Subscription, Subscription.user_id == User.id)
                .where(
                    and_(
                        Subscription.status == SubscriptionStatus.ACTIVE.value,
                        Subscription.end_date > datetime.now(UTC),
                        User.telegram_id.isnot(None),
                    )
                )
            )
            active_users = result.scalars().all()

            # Фильтруем по порогу трафика через RemnaWave API
            eligible = []
            threshold_bytes = settings.REVIEWS_TRAFFIC_THRESHOLD_MB * 1024 * 1024

            try:
                from app.external.remnawave_api import RemnaWaveAPI

                async with RemnaWaveAPI(
                    base_url=settings.REMNAWAVE_API_URL,
                    api_key=settings.REMNAWAVE_API_KEY,
                    secret_key=getattr(settings, 'REMNAWAVE_SECRET_KEY', None),
                    username=getattr(settings, 'REMNAWAVE_USERNAME', None),
                    password=getattr(settings, 'REMNAWAVE_PASSWORD', None),
                    caddy_token=getattr(settings, 'REMNAWAVE_CADDY_AUTH_TOKEN', None),
                    auth_type=getattr(settings, 'REMNAWAVE_AUTH_TYPE', 'api_key'),
                ) as api:
                    for user in active_users:
                        try:
                            if not user.telegram_id:
                                continue

                            # Получаем данные трафика из RemnaWave
                            panel_users = await api.get_user_by_telegram_id(user.telegram_id)
                            if not panel_users:
                                continue

                            # Берём первого пользователя
                            panel_user = panel_users[0]
                            used_bytes = panel_user.used_traffic_bytes

                            # Проверяем порог
                            if used_bytes >= threshold_bytes:
                                eligible.append(user)

                        except Exception as user_err:
                            logger.debug(
                                'Не удалось получить трафик пользователя',
                                user_id=user.id,
                                error=user_err,
                            )
            except Exception as api_err:
                logger.error('❌ Ошибка подключения к RemnaWave API для отзывов', error=api_err)
                # При ошибке API — берём всех активных пользователей
                eligible = list(active_users)

            logger.info(
                '⭐ Найдено подходящих пользователей для отзывов',
                total_active=len(active_users),
                eligible=len(eligible),
                threshold_mb=settings.REVIEWS_TRAFFIC_THRESHOLD_MB,
            )
            return eligible

        except Exception as e:
            logger.error('❌ Ошибка получения списка пользователей для отзывов', error=e)
            return []

    async def _send_single_request(self, user: User) -> None:
        """Отправляет одному пользователю запрос на отзыв."""
        # Клавиатура с кнопками рейтинга (1-5 звёзд)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text='⭐', callback_data='review_rate:1'),
                    InlineKeyboardButton(text='⭐⭐', callback_data='review_rate:2'),
                    InlineKeyboardButton(text='⭐⭐⭐', callback_data='review_rate:3'),
                ],
                [
                    InlineKeyboardButton(text='⭐⭐⭐⭐', callback_data='review_rate:4'),
                    InlineKeyboardButton(text='⭐⭐⭐⭐⭐', callback_data='review_rate:5'),
                ],
                [
                    InlineKeyboardButton(text='❌ Не сейчас', callback_data='review_dismiss'),
                ],
            ]
        )

        # Формируем описание наград
        max_star_reward = settings.REVIEWS_REWARD_STAR_5
        max_content_reward = settings.REVIEWS_REWARD_CONTENT_VIDEO
        max_total = max_star_reward + max_content_reward

        name = user.first_name or user.full_name or "пользователь"
        text_lines = [
            f'👋 <b>Здравствуйте, {name}!</b>\n\n',
            'Мы видим, что вы активно пользуетесь нашим сервисом, и хотели бы узнать ваше мнение о качестве нашего VPN!\n'
        ]
        
        if max_total > 0:
            text_lines.append('')
            if max_star_reward > 0:
                text_lines.append(f'🎁 За оценку вы можете получить <b>до +{max_star_reward} дн.</b> подписки')
            if max_content_reward > 0:
                text_lines.append(f'📝 За развёрнутый отзыв — ещё <b>до +{max_content_reward} дн.</b>')
            text_lines.extend([
                '',
                f'💎 Итого до <b>+{max_total} дней</b> бесплатно!\n'
            ])
            
        text_lines.append('Выберите вашу оценку:')
        text = '\n'.join(text_lines)

        try:
            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                reply_markup=keyboard,
                parse_mode='HTML',
            )
            logger.debug('⭐ Запрос на отзыв отправлен', user_id=user.id)
        except Exception as e:
            logger.warning(
                '⚠️ Не удалось отправить запрос на отзыв',
                user_id=user.id,
                error=e,
            )


# Глобальный экземпляр сервиса (синглтон)
reviews_service = ReviewsService()
