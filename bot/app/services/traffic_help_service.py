"""
Сервис автоматической помощи при отсутствии трафика.

Функционал:
- Ежедневная проверка пользователей, у которых активна подписка, но нет трафика.
- Отправка сообщения с инструкцией и кнопкой связи с поддержкой.
- Установка флага setup_help_sent, чтобы не отправлять сообщение повторно.
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.database.models import User, Subscription
from app.localization.texts import get_texts
from app.external.remnawave_api import UserStatus
from app.keyboards.inline import get_traffic_help_keyboard


logger = structlog.get_logger(__name__)


class TrafficHelpService:
    def __init__(self):
        self.bot: Optional[Bot] = None
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    def set_bot(self, bot: Bot):
        self.bot = bot

    def is_enabled(self) -> bool:
        return settings.TRAFFIC_HELP_ENABLED

    def is_running(self) -> bool:
        return self._is_running

    async def start(self):
        if not settings.TRAFFIC_HELP_ENABLED:
            logger.info("Сервис Traffic Help выключен в настройках.")
            return

        if self._is_running:
            logger.warning("Traffic Help сервис уже запущен.")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Traffic Help сервис запущен.")

    async def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Traffic Help сервис остановлен.")

    async def _run_scheduler(self):
        """Фоновый цикл проверки."""
        while self._is_running:
            try:
                now = datetime.now()
                # Определяем время следующего запуска (сегодня или завтра в TRAFFIC_HELP_CHECK_TIME)
                target_time = datetime.strptime(settings.TRAFFIC_HELP_CHECK_TIME, "%H:%M").time()
                next_run = datetime.combine(now.date(), target_time)

                if now >= next_run:
                    next_run += timedelta(days=1)

                sleep_seconds = (next_run - now).total_seconds()
                logger.info(f"Traffic Help сервис ждет {sleep_seconds} секунд до следующей проверки ({next_run}).")
                
                await asyncio.sleep(sleep_seconds)
                
                if self._is_running:
                    await self.run_check()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Ошибка в цикле Traffic Help сервиса: {e}")
                await asyncio.sleep(60)

    async def run_check(self, admin_id: Optional[int] = None) -> tuple[int, int]:
        """
        Запускает проверку пользователей и рассылку.
        Возвращает кортеж: (количество_найденных, количество_отправленных)
        """
        if not self.bot:
            logger.error("Bot instance не установлен в TrafficHelpService")
            return 0, 0

        logger.info("Запуск проверки пользователей для Traffic Help", triggered_by=admin_id or "scheduler")
        
        found_count = 0
        sent_count = 0

        async with AsyncSessionLocal() as db:
            try:
                users_to_notify = await self._get_eligible_users(db)
                found_count = len(users_to_notify)
                
                logger.info(f"Найдено пользователей для рассылки Traffic Help: {found_count}")

                for user in users_to_notify:
                    success = await self._notify_user(db, user)
                    if success:
                        sent_count += 1
                        
                    # Небольшая пауза, чтобы не упереться в лимиты Telegram API (30 сообщений в секунду)
                    await asyncio.sleep(0.05)
                    
            except Exception as e:
                logger.exception(f"Ошибка при получении или обработке пользователей Traffic Help: {e}")

        logger.info("Проверка Traffic Help завершена", found_count=found_count, sent_count=sent_count)
        return found_count, sent_count

    async def _get_eligible_users(self, db: AsyncSession) -> list[User]:
        """
        Получает список пользователей, которым нужно отправить помощь.
        Критерии:
        1. setup_help_sent == False (или NULL)
        2. Есть активная подписка (UserStatus.ACTIVE)
        3. Подписка активна больше чем TRAFFIC_HELP_DAYS_AFTER дней
        4. Использовано трафика меньше чем TRAFFIC_HELP_THRESHOLD_MB
        """
        threshold_gb = settings.TRAFFIC_HELP_THRESHOLD_MB / 1024.0
        days_after = settings.TRAFFIC_HELP_DAYS_AFTER
        
        now = datetime.now()
        activation_threshold_date = now - timedelta(days=days_after)
        
        query = (
            select(User)
            .join(Subscription, User.id == Subscription.user_id)
            .where(
                # Сообщение еще не отправлялось
                or_(User.setup_help_sent == False, User.setup_help_sent.is_(None)),
                
                # Подписка активна
                Subscription.status == UserStatus.ACTIVE,
                
                # Подписка активирована давно (создана или обновлена, в идеале created_at, но тут берем updated_at или created_at)
                Subscription.created_at <= activation_threshold_date,
                
                # Трафика потрачено меньше порога
                Subscription.traffic_used_gb < threshold_gb
            )
        )
        
        result = await db.execute(query)
        return list(result.scalars().all())

    async def _notify_user(self, db: AsyncSession, user: User) -> bool:
        """Отправляет сообщение пользователю и обновляет статус."""
        texts = get_texts(user.language)
        
        # Текст сообщения
        message_text = texts.t(
            'TRAFFIC_HELP_MESSAGE',
            '👋 Здравствуйте! Мы заметили, что у вас активна подписка, но вы почти не используете VPN.\n\n'
            'Возможно, у вас возникли сложности с настройкой?\n'
            'Если вам нужна помощь, посмотрите нашу инструкцию или напишите в поддержку — мы с радостью поможем!'
        )
        
        # Клавиатура
        keyboard = get_traffic_help_keyboard(user.language, settings.TRAFFIC_HELP_SUPPORT_URL)
        
        try:
            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=message_text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            
            # Отмечаем, что отправили
            user.setup_help_sent = True
            await db.commit()
            
            logger.info("Traffic Help сообщение отправлено", user_id=user.id, telegram_id=user.telegram_id)
            return True
            
        except TelegramAPIError as e:
            logger.error(f"Не удалось отправить Traffic Help сообщение пользователю {user.telegram_id}: {e}")
            # Отмечаем как отправленное даже при ошибке (например, если заблокировал бота), 
            # чтобы не долбиться к нему каждый день
            if "bot was blocked by the user" in str(e).lower() or "user is deactivated" in str(e).lower():
                 user.setup_help_sent = True
                 await db.commit()
            return False
        except Exception as e:
            logger.exception(f"Непредвиденная ошибка при отправке Traffic Help {user.telegram_id}: {e}")
            return False

    async def send_test_message(self, admin_user: User) -> bool:
        """Отправляет тестовое сообщение администратору без изменения статуса в БД."""
        if not self.bot:
            logger.error("Bot instance не установлен в TrafficHelpService")
            return False
            
        texts = get_texts(admin_user.language)
        
        # Текст сообщения
        message_text = texts.t(
            'TRAFFIC_HELP_MESSAGE',
            '👋 Здравствуйте! Мы заметили, что у вас активна подписка, но вы почти не используете VPN.\n\n'
            'Возможно, у вас возникли сложности с настройкой?\n'
            'Если вам нужна помощь, посмотрите нашу инструкцию или напишите в поддержку — мы с радостью поможем!'
        )
        
        # Клавиатура
        keyboard = get_traffic_help_keyboard(admin_user.language, settings.TRAFFIC_HELP_SUPPORT_URL)
        
        try:
            await self.bot.send_message(
                chat_id=admin_user.telegram_id,
                text=message_text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            logger.info("Тестовое Traffic Help сообщение отправлено", telegram_id=admin_user.telegram_id)
            return True
        except Exception as e:
            logger.exception(f"Непредвиденная ошибка при отправке тестового Traffic Help {admin_user.telegram_id}: {e}")
            return False

traffic_help_service = TrafficHelpService()
