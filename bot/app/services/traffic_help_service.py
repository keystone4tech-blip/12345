"""
Сервис автоматической помощи при отсутствии трафика.

Функционал:
- Ежедневная проверка пользователей, у которых активна подписка, но нет трафика.
- Отправка сообщения с инструкцией и кнопкой связи с поддержкой.
- Установка флага setup_help_sent, чтобы не отправлять сообщение повторно.
"""

import asyncio
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, UTC, time as dt_time

import structlog
from aiogram import Bot
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.config import settings
from app.database.models import User, Subscription, SubscriptionStatus

logger = structlog.get_logger(__name__)


class TrafficHelpService:
    """Управление рассылкой помощи пользователям без трафика."""

    def __init__(self):
        self.bot: Bot | None = None
        self._task: asyncio.Task | None = None
        self._running: bool = False

    def set_bot(self, bot: Bot) -> None:
        self.bot = bot

    def is_enabled(self) -> bool:
        return bool(settings.TRAFFIC_HELP_ENABLED)

    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def start(self) -> None:
        if not self.is_enabled():
            logger.info('⭐ Система помощи по трафику отключена (TRAFFIC_HELP_ENABLED=false)')
            return

        if self.is_running():
            logger.warning('⭐ Шедулер помощи по трафику уже запущен')
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info(
            '⭐ Шедулер помощи по трафику запущен',
            check_time=settings.TRAFFIC_HELP_CHECK_TIME,
            threshold_mb=settings.TRAFFIC_HELP_THRESHOLD_MB,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info('⭐ Шедулер помощи по трафику остановлен')

    async def run_manual(self) -> tuple[int, int]:
        """
        Ручной запуск рассылки.
        Возвращает (отправлено, ошибок).
        """
        if not self.bot:
            logger.error('⭐ Бот не установлен, рассылка невозможна')
            return 0, 0
        return await self._send_help_requests()

    async def _scheduler_loop(self) -> None:
        logger.info('⭐ Цикл шедулера помощи по трафику запущен')

        while self._running:
            try:
                tz = ZoneInfo(settings.TIMEZONE)
                now_local = datetime.now(tz)
                check_time = self._parse_check_time()

                next_run_local = now_local.replace(
                    hour=check_time.hour,
                    minute=check_time.minute,
                    second=0,
                    microsecond=0,
                )
                if next_run_local <= now_local:
                    next_run_local += timedelta(days=1)

                wait_seconds = (next_run_local - now_local).total_seconds()

                if wait_seconds > 60:
                    await asyncio.sleep(60)
                    continue

                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)

                if not self._running or not self.is_enabled():
                    continue

                await self._send_help_requests()
                
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                logger.info('⭐ Шедулер помощи по трафику отменён')
                break
            except Exception as e:
                logger.error('❌ Ошибка в цикле шедулера помощи по трафику', error=e)
                await asyncio.sleep(60)

    def _parse_check_time(self) -> dt_time:
        try:
            hour_str, minute_str = settings.TRAFFIC_HELP_CHECK_TIME.split(':')
            return dt_time(hour=int(hour_str), minute=int(minute_str))
        except Exception as e:
            logger.error('❌ Ошибка парсинга TRAFFIC_HELP_CHECK_TIME, используем 12:00', error=e)
            return dt_time(hour=12, minute=0)

    async def _send_help_requests(self) -> tuple[int, int]:
        """Рассылает помощь и возвращает (успешно, ошибки)."""
        logger.info('⭐ Начинаем рассылку помощи по трафику')

        try:
            from app.database.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                eligible_users = await self._get_eligible_users(db)

                sent_count = 0
                error_count = 0

                for user in eligible_users:
                    try:
                        if not user.telegram_id:
                            continue

                        await self._send_single_request(user)
                        
                        # Отмечаем флаг в БД
                        await db.execute(
                            update(User)
                            .where(User.id == user.id)
                            .values(setup_help_sent=True)
                        )
                        await db.commit()
                        
                        sent_count += 1
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        error_count += 1
                        logger.error(
                            '❌ Ошибка отправки помощи по трафику',
                            user_id=user.id,
                            error=e,
                        )

                logger.info(
                    '⭐ Рассылка помощи завершена',
                    sent=sent_count,
                    errors=error_count,
                )
                return sent_count, error_count

        except Exception as e:
            logger.error('❌ Ошибка в процессе рассылки помощи', error=e)
            return 0, 0

    async def _get_eligible_users(self, db: AsyncSession) -> list[User]:
        try:
            threshold_gb = settings.TRAFFIC_HELP_THRESHOLD_MB / 1024.0
            days_after = settings.TRAFFIC_HELP_DAYS_AFTER
            cutoff_date = datetime.now(UTC) - timedelta(days=days_after)

            result = await db.execute(
                select(User)
                .join(Subscription, Subscription.user_id == User.id)
                .where(
                    and_(
                        Subscription.status == SubscriptionStatus.ACTIVE.value,
                        Subscription.start_date <= cutoff_date,
                        Subscription.traffic_used_gb <= threshold_gb,
                        User.setup_help_sent == False,
                        User.telegram_id.isnot(None),
                    )
                )
            )
            eligible_users = result.scalars().all()

            logger.info(
                '⭐ Найдено пользователей для помощи по трафику',
                eligible=len(eligible_users),
            )
            return list(eligible_users)

        except Exception as e:
            logger.error('❌ Ошибка получения списка пользователей для помощи', error=e)
            return []

    async def _send_single_request(self, user: User) -> None:
        url = settings.TRAFFIC_HELP_SUPPORT_URL or settings.MINIAPP_SUPPORT_URL
        
        keyboard_buttons = []
        if url:
            keyboard_buttons.append([InlineKeyboardButton(text="🆘 Поддержка", url=url)])
        else:
             # Fallback to direct bot command or contact (depending on system settings)
             pass 

        # We will use the exact text format preferred for user notifications
        text = (
            "Привет! 👋\n\n"
            "Видим, что у тебя активна подписка, но ты пока не пользовался нашим VPN.\n"
            "Возникли сложности с настройкой? 🔧\n\n"
            "Нажми кнопку ниже, и мы поможем тебе всё настроить!"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None
        
        await self.bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
t r a f f i c _ h e l p _ s e r v i c e   =   T r a f f i c H e l p S e r v i c e ( )  
 