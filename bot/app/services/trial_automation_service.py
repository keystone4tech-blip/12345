import asyncio
import structlog
from datetime import datetime, timedelta, UTC
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.database.models import User, Subscription
from app.localization.texts import get_texts
from app.database.crud.tariff import get_trial_tariff, get_tariff_by_id
from app.keyboards.inline import get_main_menu_keyboard

logger = structlog.get_logger(__name__)

def is_trial_available_for_user(user: User) -> bool:
    if settings.TRIAL_DURATION_DAYS <= 0:
        return False

    if settings.is_trial_disabled_for_user(getattr(user, 'auth_type', 'telegram')):
        return False

    if getattr(user, 'has_had_paid_subscription', False):
        return False

    subscription = getattr(user, 'subscription', None)
    if subscription is not None:
        return False

    return True

class TrialAutomationService:
    def __init__(self):
        self.bot: Optional[Bot] = None
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    def set_bot(self, bot: Bot):
        self.bot = bot

    def is_enabled(self) -> bool:
        return settings.TRIAL_AUTO_ACTIVATE_ENABLED or settings.TRIAL_REMINDER_ENABLED

    def is_running(self) -> bool:
        return self._is_running

    async def start(self):
        if not self.is_enabled():
            logger.info("Trial Automation выключена в настройках.")
            return

        if self._is_running:
            logger.warning("Trial Automation сервис уже запущен.")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Trial Automation сервис запущен.")

    async def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Trial Automation сервис остановлен.")

    async def _run_scheduler(self):
        """Фоновый цикл проверки раз в час."""
        while self._is_running:
            try:
                await self.run_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Ошибка в цикле Trial Automation сервиса: {e}")
            
            # Ждем 1 час до следующей проверки
            await asyncio.sleep(3600)

    async def run_check(self):
        """Запускает проверку пользователей для напоминания и автоактивации."""
        if not self.bot:
            logger.error("Bot instance не установлен в TrialAutomationService")
            return

        logger.info("Запуск проверки пользователей для Trial Automation")
        
        async with AsyncSessionLocal() as db:
            try:
                users = await self._get_eligible_users(db)
                logger.info(f"Найдено пользователей для проверки: {len(users)}")

                now = datetime.now(UTC)
                for user in users:
                    hours_since_registration = (now - user.created_at.replace(tzinfo=UTC)).total_seconds() / 3600

                    # 1. Отправка напоминания
                    if settings.TRIAL_REMINDER_ENABLED and hours_since_registration >= settings.TRIAL_REMINDER_DELAY_HOURS:
                        notification_settings = user.notification_settings or {}
                        if not notification_settings.get('trial_reminder_sent'):
                            await self._send_reminder(db, user)

                    # 2. Авто-активация
                    if settings.TRIAL_AUTO_ACTIVATE_ENABLED and hours_since_registration >= settings.TRIAL_AUTO_ACTIVATE_DELAY_HOURS:
                        notification_settings = user.notification_settings or {}
                        if not notification_settings.get('trial_auto_activated'):
                            await self._auto_activate_trial(db, user)

                    await asyncio.sleep(0.05)  # Пауза
            except Exception as e:
                logger.exception(f"Ошибка при обработке Trial Automation: {e}")

    async def _get_eligible_users(self, db: AsyncSession) -> list[User]:
        from sqlalchemy.orm import selectinload
        # Выбираем пользователей без подписки и без оплаты
        query = (
            select(User)
            .options(selectinload(User.subscription))
            .outerjoin(Subscription, User.id == Subscription.user_id)
            .where(
                Subscription.id.is_(None),
                User.has_had_paid_subscription == False,
                User.telegram_id.isnot(None),
                User.status == 'active'
            )
        )
        result = await db.execute(query)
        users = result.scalars().all()
        
        # Оставляем только тех, кому доступен триал
        return [u for u in users if is_trial_available_for_user(u)]

    async def force_send_reminders(self, admin_id: int) -> int:
        """Принудительная отправка напоминаний всем пользователям, не активировавшим триал."""
        if not self.bot:
            logger.error("Bot instance не установлен в TrialAutomationService")
            return 0
            
        async with AsyncSessionLocal() as db:
            users = await self._get_eligible_users(db)
            sent_count = 0
            blocked_count = 0
            for user in users:
                success = await self._send_reminder(db, user)
                if success:
                    sent_count += 1
                else:
                    blocked_count += 1
                await asyncio.sleep(0.05)
                
            # Отправка отчета админу
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            report = (
                f"📊 <b>Аналитика рассылки триалов:</b>\n\n"
                f"Найдено пользователей без триалов: {len(users)}\n"
                f"Успешно доставлено: {sent_count}\n"
                f"Заблокировали бота: {blocked_count}"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Выход на главное меню", callback_data="admin_panel")]
            ])
            try:
                await self.bot.send_message(chat_id=admin_id, text=report, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка при отправке отчета админу {admin_id}: {e}")
                
            return sent_count

    async def _send_reminder(self, db: AsyncSession, user: User) -> bool:
        texts = get_texts(user.language)
        
        from app.utils.pricing_utils import _pluralize_days_ru
        duration = settings.TRIAL_DURATION_DAYS
        days_str = f"{duration} {_pluralize_days_ru(duration)}"
        
        message_text = texts.t(
            'TRIAL_REMINDER_MESSAGE',
            f'🎁 <b>Вы еще не попробовали наш VPN!</b>\n\n'
            f'Активируйте тестовый период на {days_str} абсолютно бесплатно '
            f'и оцените высокую скорость без ограничений.\n\n'
            f'Нажмите на кнопку ниже, чтобы перейти в меню.'
        )
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=texts.t('MENU_TRIAL', '🎁 Активировать триал'), callback_data='trial_activate')]
        ])
        
        try:
            sent_msg = await self.bot.send_message(
                chat_id=user.telegram_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            import contextlib
            with contextlib.suppress(Exception):
                await self.bot.pin_chat_message(
                    chat_id=user.telegram_id,
                    message_id=sent_msg.message_id,
                    disable_notification=True
                )
            
            ns = user.notification_settings or {}
            ns['trial_reminder_sent'] = True
            user.notification_settings = ns
            await db.commit()
            
            logger.info("Напоминание о триале отправлено", user_id=user.id)
            return True
        except TelegramAPIError as e:
            if "bot was blocked by the user" in str(e).lower() or "user is deactivated" in str(e).lower():
                ns = user.notification_settings or {}
                ns['trial_reminder_sent'] = True
                user.notification_settings = ns
                await db.commit()
            return False
        except Exception as e:
            logger.exception(f"Ошибка при отправке напоминания: {e}")
            return False

    async def _auto_activate_trial(self, db: AsyncSession, user: User) -> bool:
        from app.database.crud.subscription import create_trial_subscription
        
        try:
            trial_traffic_limit = None
            trial_device_limit = settings.TRIAL_DEVICE_LIMIT
            trial_squads = None
            tariff_id_for_trial = None
            trial_duration = settings.TRIAL_DURATION_DAYS

            trial_tariff = await get_trial_tariff(db)
            if not trial_tariff:
                trial_tariff_id = settings.get_trial_tariff_id()
                if trial_tariff_id > 0:
                    trial_tariff = await get_tariff_by_id(db, trial_tariff_id)
                    if trial_tariff and not trial_tariff.is_active:
                        trial_tariff = None

            if trial_tariff:
                trial_traffic_limit = trial_tariff.traffic_limit_gb
                trial_device_limit = trial_tariff.device_limit
                trial_squads = trial_tariff.allowed_squads or []
                tariff_id_for_trial = trial_tariff.id
                tariff_trial_days = getattr(trial_tariff, 'trial_duration_days', None)
                if tariff_trial_days:
                    trial_duration = tariff_trial_days

            subscription = await create_trial_subscription(
                db=db,
                user=user,
                duration_days=trial_duration,
                device_limit=trial_device_limit,
                traffic_limit_gb=trial_traffic_limit,
                connected_squads=trial_squads,
                tariff_id=tariff_id_for_trial,
            )

            ns = user.notification_settings or {}
            ns['trial_auto_activated'] = True
            user.notification_settings = ns
            await db.commit()

            # Отправляем уведомление
            texts = get_texts(user.language)
            message_text = texts.t(
                'TRIAL_AUTO_ACTIVATED_MESSAGE',
                f'🤖 <b>Мы автоматически активировали для вас тестовый период!</b>\n\n'
                f'Вам начислено {trial_duration} дней бесплатного VPN. Вы можете перейти в меню '
                f'и подключить устройства.'
            )
            keyboard = get_main_menu_keyboard(user.language)
            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

            logger.info("Триал авто-активирован", user_id=user.id)
            return True
        except Exception as e:
            logger.exception(f"Ошибка при авто-активации триала для юзера {user.id}: {e}")
            return False

trial_automation_service = TrialAutomationService()
