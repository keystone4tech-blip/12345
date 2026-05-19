"""
Unified notification delivery service for all user types.

This service handles notification delivery through appropriate channels:
- Telegram Bot for users with telegram_id
- Email + WebSocket for email-only users
"""

import asyncio
from enum import Enum
from typing import Any

import structlog
from aiogram import Bot

from app.config import settings
from app.database.models import User, UserStatus


logger = structlog.get_logger(__name__)


class NotificationType(Enum):
    """Types of notifications that can be sent to users."""

    # Balance notifications
    BALANCE_TOPUP = 'balance_topup'
    BALANCE_CHANGE = 'balance_change'
    BALANCE_LOW = 'balance_low'

    # Subscription notifications
    SUBSCRIPTION_ACTIVATED = 'subscription_activated'
    SUBSCRIPTION_EXPIRING = 'subscription_expiring'
    SUBSCRIPTION_EXPIRED = 'subscription_expired'
    SUBSCRIPTION_RENEWED = 'subscription_renewed'

    # Autopay notifications
    AUTOPAY_SUCCESS = 'autopay_success'
    AUTOPAY_FAILED = 'autopay_failed'
    AUTOPAY_INSUFFICIENT_FUNDS = 'autopay_insufficient_funds'

    # Daily subscription notifications
    DAILY_DEBIT = 'daily_debit'
    DAILY_INSUFFICIENT_FUNDS = 'daily_insufficient_funds'
    TRAFFIC_RESET = 'traffic_reset'

    # Account notifications
    BAN_NOTIFICATION = 'ban_notification'
    UNBAN_NOTIFICATION = 'unban_notification'
    WARNING_NOTIFICATION = 'warning_notification'

    # Referral notifications
    REFERRAL_BONUS = 'referral_bonus'
    REFERRAL_REGISTERED = 'referral_registered'

    # Gift notifications
    GIFT_ACCEPTED = 'gift_accepted'
    GIFT_RECEIVED = 'gift_received'

    # Partner notifications
    PARTNER_APPLICATION_APPROVED = 'partner_application_approved'
    PARTNER_APPLICATION_REJECTED = 'partner_application_rejected'

    # Withdrawal notifications
    WITHDRAWAL_APPROVED = 'withdrawal_approved'
    WITHDRAWAL_REJECTED = 'withdrawal_rejected'

    # Auth emails
    EMAIL_VERIFICATION = 'email_verification'
    PASSWORD_RESET = 'password_reset'

    # Webhook subscription events
    WEBHOOK_SUB_EXPIRED = 'webhook_sub_expired'
    WEBHOOK_SUB_DISABLED = 'webhook_sub_disabled'
    WEBHOOK_SUB_ENABLED = 'webhook_sub_enabled'
    WEBHOOK_SUB_LIMITED = 'webhook_sub_limited'
    WEBHOOK_SUB_TRAFFIC_RESET = 'webhook_sub_traffic_reset'
    WEBHOOK_SUB_DELETED = 'webhook_sub_deleted'
    WEBHOOK_SUB_REVOKED = 'webhook_sub_revoked'
    WEBHOOK_SUB_EXPIRING = 'webhook_sub_expiring'
    WEBHOOK_SUB_FIRST_CONNECTED = 'webhook_sub_first_connected'
    WEBHOOK_SUB_BANDWIDTH_THRESHOLD = 'webhook_sub_bandwidth_threshold'
    WEBHOOK_USER_NOT_CONNECTED = 'webhook_user_not_connected'
    WEBHOOK_DEVICE_ADDED = 'webhook_device_added'
    WEBHOOK_DEVICE_DELETED = 'webhook_device_deleted'

    # Other
    BROADCAST = 'broadcast'
    PAYMENT_RECEIVED = 'payment_received'


class NotificationDeliveryService:
    """
    Service for delivering notifications to users through appropriate channels.

    For Telegram users: sends via Telegram Bot
    For email-only users: sends via Email and WebSocket (if connected)
    """

    def __init__(self):
        self._email_service = None
        self._email_templates = None
        self._ws_manager = None

    @property
    def email_service(self):
        """Lazy load email service."""
        if self._email_service is None:
            from app.cabinet.services.email_service import email_service

            self._email_service = email_service
        return self._email_service

    @property
    def email_templates(self):
        """Lazy load email templates."""
        if self._email_templates is None:
            from app.cabinet.services.email_templates import EmailNotificationTemplates

            self._email_templates = EmailNotificationTemplates()
        return self._email_templates

    @property
    def ws_manager(self):
        """Lazy load WebSocket manager."""
        if self._ws_manager is None:
            from app.cabinet.routes.websocket import cabinet_ws_manager

            self._ws_manager = cabinet_ws_manager
        return self._ws_manager

    def _is_notification_enabled(self, user: User, notification_type: NotificationType, context: dict[str, Any]) -> bool:
        """
        Проверяет, включен ли данный тип уведомлений в настройках пользователя.
        Все подробные настройки извлекаются из JSON-поля notification_settings модели User.
        """
        # Извлекаем настройки уведомлений из JSON-поля пользователя (по умолчанию пустой словарь)
        settings_data = getattr(user, 'notification_settings', None) or {}
        
        # 1. Проверка для уведомления об истечении подписки
        if notification_type == NotificationType.SUBSCRIPTION_EXPIRING:
            enabled = settings_data.get('subscription_expiry_enabled', True) # По умолчанию True
            logger.debug("Проверка настройки: уведомление об истечении подписки", user_id=user.id, enabled=enabled)
            return enabled
            
        # 2. Проверка для уведомления о низком балансе
        if notification_type == NotificationType.BALANCE_LOW:
            enabled = settings_data.get('balance_low_enabled', True) # По умолчанию True
            if not enabled:
                logger.debug("Проверка настройки: уведомление о низком балансе отключено", user_id=user.id)
                return False
            # Проверяем порог списания (лимит)
            threshold = settings_data.get('balance_low_threshold', 100) # По умолчанию 100 копеек (1 рубль)
            balance = context.get('new_balance_kopeks', user.balance_kopeks)
            is_low = balance <= threshold
            logger.debug("Проверка настройки: порог баланса", user_id=user.id, threshold=threshold, balance=balance, is_low=is_low)
            return is_low

        # 3. Проверка для массовых объявлений и новостей (Broadcast)
        if notification_type == NotificationType.BROADCAST:
            is_promo = context.get('is_promo', False) # Является ли акцией/промо-предложением
            if is_promo:
                enabled = settings_data.get('promo_offers_enabled', True)
                logger.debug("Проверка настройки: промо-акции", user_id=user.id, enabled=enabled)
                return enabled
            enabled = settings_data.get('news_enabled', True)
            logger.debug("Проверка настройки: новости сервиса", user_id=user.id, enabled=enabled)
            return enabled
            
        # По умолчанию все остальные важные типы уведомлений (активация подписки, начисления рефералов) всегда включены
        return True

    async def _send_webpush_notification(
        self,
        user: User,
        notification_type: NotificationType,
        context: dict[str, Any],
        telegram_message: str | None = None,
    ) -> bool:
        """
        Отправляет Web Push уведомления на все зарегистрированные PWA-устройства пользователя.
        Связывает системные уведомления бэкенда с установленным PWA-приложением на телефоне/ПК.
        """
        from sqlalchemy import select
        from app.database.models import PushSubscription
        from app.database.database import db_manager
        from pywebpush import webpush, WebPushException
        from app.utils.vapid import generate_vapid_headers
        import json
        import re

        logger.info("Попытка отправки Web Push уведомления", user_id=user.id, notification_type=notification_type.value)

        # 1. Получаем все активные подписки пользователя из базы данных
        try:
            async with db_manager.session(read_only=True) as db:
                stmt = select(PushSubscription).where(PushSubscription.user_id == user.id)
                result = await db.execute(stmt)
                subscriptions = result.scalars().all()
        except Exception as db_err:
            logger.error("Ошибка при запросе подписок из БД", user_id=user.id, error=str(db_err))
            return False

        if not subscriptions:
            logger.debug("У пользователя нет активных подписок на Web Push (приложение PWA не настроено/не установлено)", user_id=user.id)
            return False

        # 2. Формируем тело (body) уведомления.
        # Если передан готовый текст для Telegram (telegram_message), очищаем его от HTML-тегов и используем
        body = ""
        if telegram_message:
            # Очищаем HTML-теги с помощью регулярного выражения для красивого отображения в нативном пуше
            body = re.sub(r'<[^>]+>', '', telegram_message)
            # Убираем множественные пустые строки и пробелы
            body = re.sub(r'\n+', '\n', body).strip()

        # Если тело пустое (например, telegram_message отсутствует), формируем стандартные качественные тексты по типу уведомления
        if not body:
            if notification_type == NotificationType.BALANCE_TOPUP:
                body = f"Ваш баланс успешно пополнен на {context.get('formatted_amount', 'сумму')}! 🎉"
            elif notification_type == NotificationType.BALANCE_CHANGE:
                body = f"Баланс изменен на {context.get('formatted_amount', 'сумму')}."
            elif notification_type == NotificationType.SUBSCRIPTION_EXPIRING:
                body = f"Ваша подписка истекает через {context.get('days_left', 'несколько')} дн. Рекомендуем продлить! 💎"
            elif notification_type == NotificationType.SUBSCRIPTION_EXPIRED:
                body = "Срок действия вашей подписки истек. VPN-доступ приостановлен. ⚠️"
            elif notification_type == NotificationType.SUBSCRIPTION_ACTIVATED:
                body = "Ваша VPN подписка успешно активирована! Приятного использования. 🚀"
            elif notification_type == NotificationType.SUBSCRIPTION_RENEWED:
                body = "Ваша подписка успешно продлена! 💎"
            elif notification_type == NotificationType.REFERRAL_BONUS:
                body = f"Вам начислен реферальный бонус {context.get('formatted_bonus', '')} за покупку реферала {context.get('referral_name', '')}! 👥"
            elif notification_type == NotificationType.REFERRAL_REGISTERED:
                body = f"Новый реферал успешно зарегистрирован по вашей реферальной ссылке! 👥"
            elif notification_type == NotificationType.GIFT_ACCEPTED:
                body = f"Ваш подарок успешно активирован! Пользователь {context.get('recipient_name', '')} активировал подаренный вами тариф {context.get('tariff_name', '')}. 🎁"
            elif notification_type == NotificationType.GIFT_RECEIVED:
                body = f"Вам прислали подарок! Пользователь {context.get('gifter_name', '')} отправил вам тариф {context.get('tariff_name', '')} на {context.get('period_days', '')} дн. 🎁"
            elif notification_type == NotificationType.AUTOPAY_SUCCESS:
                body = f"Автоплатеж успешно выполнен на сумму {context.get('formatted_amount', '')}! Подписка продлена. 💎"
            elif notification_type == NotificationType.AUTOPAY_FAILED:
                body = f"Не удалось выполнить автоплатеж. Причина: {context.get('reason', 'ошибка транзакции')}."
            elif notification_type == NotificationType.DAILY_DEBIT:
                body = f"Ежедневное списание по подписке выполнено: {context.get('formatted_amount', '')}."
            elif notification_type == NotificationType.BAN_NOTIFICATION:
                body = f"Ваш аккаунт заблокирован. Причина: {context.get('reason', '')}."
            elif notification_type == NotificationType.UNBAN_NOTIFICATION:
                body = "Ваш аккаунт успешно разблокирован! 🚀"
            elif notification_type == NotificationType.BROADCAST:
                body = context.get('message', 'Новое уведомление от нашего сервиса.')
            else:
                body = "У вас новое важное уведомление в личном кабинете MozhnoVPN."

        # 3. Задаем красивые и интуитивно понятные заголовки пушей в зависимости от типа
        title = "MozhnoVPN"
        url = "/profile" # Дефолтный путь перехода по клику на пуш

        if 'balance' in notification_type.value:
            title = "MozhnoVPN — Баланс 💳"
            url = "/profile"
        elif 'subscription' in notification_type.value or 'autopay' in notification_type.value or 'daily' in notification_type.value:
            title = "MozhnoVPN — Подписка 💎"
            url = "/connection"
        elif 'referral' in notification_type.value or 'partner' in notification_type.value or 'withdrawal' in notification_type.value or 'gift' in notification_type.value:
            title = "MozhnoVPN — Подарки 🎁" if 'gift' in notification_type.value else "MozhnoVPN — Рефералы 👥"
            url = "/connection" if 'gift' in notification_type.value else "/referral"
        elif 'broadcast' in notification_type.value:
            title = "MozhnoVPN — Объявление 📢"
            url = "/"

        # Полезная нагрузка (payload) пуша
        payload = {
            "title": title,
            "body": body,
            "icon": "/icons/icon-192x192.png",
            "badge": "/icons/icon-192x192.png",
            "data": {
                "url": url
            }
        }

        logger.info(
            "Подготовка пакетов Web Push для отправки", 
            user_id=user.id, 
            type=notification_type.value, 
            payload=payload,
            subscriptions_count=len(subscriptions)
        )

        push_sent_count = 0
        for sub in subscriptions:
            try:
                # Генерируем VAPID-заголовки авторизации (используем безопасную генерацию без багов py-vapid)
                vapid_headers = generate_vapid_headers(sub.endpoint)
                
                if not vapid_headers:
                    logger.warning("Пропуск отправки на устройство: не удалось сгенерировать VAPID-заголовок", subscription_id=sub.id)
                    continue

                # Вызываем pywebpush для шифрования пакета и отправки на пуш-сервер (Google/Apple/Mozilla)
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {
                            "p256dh": sub.p256dh,
                            "auth": sub.auth
                        }
                    },
                    data=json.dumps(payload),
                    headers=vapid_headers
                )
                push_sent_count += 1
                logger.info("Web Push успешно доставлен на устройство пользователя", user_id=user.id, subscription_id=sub.id)
            except WebPushException as e:
                # Если пуш-служба вернула ошибку 410 (Gone) — это значит, что подписка устарела или удалена на устройстве.
                # Мы должны незамедлительно очистить ее из базы данных, чтобы не слать лишние запросы.
                logger.warning("Ошибка отправки Web Push (подписка недействительна)", error=str(e), subscription_id=sub.id)
                if getattr(e, 'response', None) is not None and e.response.status_code == 410:
                    try:
                        async with db_manager.session() as db_write:
                            # Находим и удаляем подписку по первичному ключу в отдельной транзакции записи
                            stmt_del = select(PushSubscription).where(PushSubscription.id == sub.id)
                            res_del = await db_write.execute(stmt_del)
                            sub_to_del = res_del.scalar_one_or_none()
                            if sub_to_del:
                                await db_write.delete(sub_to_del)
                        logger.info("Успешно удалена устаревшая подписка из базы данных", subscription_id=sub.id)
                    except Exception as del_err:
                        logger.error("Не удалось удалить недействительную подписку из БД", error=str(del_err), subscription_id=sub.id)
            except Exception as e:
                logger.error("Непредвиденная ошибка при отправке Web Push на устройство", error=str(e), subscription_id=sub.id)

        return push_sent_count > 0

    async def send_notification(
        self,
        user: User,
        notification_type: NotificationType,
        context: dict[str, Any],
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
        message_effect_id: str | None = None,
    ) -> bool:
        """
        Отправляет уведомление пользователю по всем доступным каналам доставки.
        Автоматически интегрирует отправку Web Push (PWA) параллельно со стандартными каналами.
        Все каналы имеют независимые try-except блоки во избежание взаимного влияния при ошибках.
        """
        # 1. Проверяем, активен ли статус пользователя
        if user.status in (UserStatus.BLOCKED.value, UserStatus.DELETED.value):
            logger.debug('Пропускаем уведомление для заблокированного/удаленного пользователя', user_id=user.id, status=user.status)
            return False

        # 2. Проверяем настройки уведомлений пользователя (включен ли данный тип)
        if not self._is_notification_enabled(user, notification_type, context):
            logger.info(
                'Уведомление отключено в настройках пользователя, пропускаем отправку по всем каналам',
                user_id=user.id,
                notification_type=notification_type.value,
            )
            return False

        sent_successfully = False

        # 3. Отправка Web Push (всегда отправляется на зарегистрированные PWA устройства пользователя!)
        webpush_sent = False
        try:
            webpush_sent = await self._send_webpush_notification(
                user=user,
                notification_type=notification_type,
                context=context,
                telegram_message=telegram_message,
            )
            if webpush_sent:
                sent_successfully = True
        except Exception as e:
            logger.exception("Ошибка при отправке Web Push в фоновом режиме", user_id=user.id, error=e)

        # 4. Отправка через Telegram Bot (если у пользователя привязан Telegram аккаунт)
        telegram_sent = False
        if user.telegram_id:
            try:
                telegram_sent = await self._send_telegram_notification(
                    user=user,
                    notification_type=notification_type,
                    context=context,
                    bot=bot,
                    message=telegram_message,
                    markup=telegram_markup,
                    message_effect_id=message_effect_id,
                )
                if telegram_sent:
                    sent_successfully = True
            except Exception as e:
                logger.exception("Ошибка при отправке Telegram уведомления", user_id=user.id, error=e)

        # 5. Отправка на Email (если у пользователя подключен и подтвержден Email)
        email_sent = False
        if user.email and user.email_verified:
            try:
                email_sent = await self._send_email_notification(user, notification_type, context)
                if email_sent:
                    sent_successfully = True
            except Exception as e:
                logger.exception("Ошибка при отправке Email уведомления", user_id=user.id, error=e)

        # 6. Отправка через WebSocket в личный кабинет
        ws_sent = False
        try:
            ws_sent = await self._send_websocket_notification(user, notification_type, context)
            if ws_sent:
                sent_successfully = True
        except Exception as e:
            logger.debug('Ошибка отправки WebSocket уведомления', user_id=user.id, error=e)

        logger.info(
            "Результат доставки уведомлений по всем каналам",
            user_id=user.id,
            notification_type=notification_type.value,
            telegram_sent=telegram_sent,
            webpush_sent=webpush_sent,
            email_sent=email_sent,
            ws_sent=ws_sent,
        )

        return sent_successfully

    async def _send_telegram_notification(
        self,
        user: User,
        notification_type: NotificationType,
        context: dict[str, Any],
        bot: Bot | None,
        message: str | None,
        markup: Any | None,
        message_effect_id: str | None = None,
    ) -> bool:
        """Send notification via Telegram bot."""
        if not bot:
            logger.warning('Bot instance not provided for Telegram notification to user', telegram_id=user.telegram_id)
            return False

        if not message:
            logger.warning(
                'No Telegram message provided for notification to user',
                notification_type_value=notification_type.value,
                telegram_id=user.telegram_id,
            )
            return False

        try:
            from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

            await asyncio.wait_for(
                bot.send_message(
                    chat_id=user.telegram_id,
                    text=message,
                    reply_markup=markup,
                    parse_mode='HTML',
                    message_effect_id=message_effect_id,
                ),
                timeout=15.0,
            )
            return True

        except TimeoutError:
            logger.warning('Timeout при отправке Telegram уведомления пользователю', telegram_id=user.telegram_id)
            return False

        except TelegramForbiddenError:
            logger.warning('Telegram user заблокировал бота', telegram_id=user.telegram_id)
            return False

        except TelegramBadRequest as e:
            logger.warning('Ошибка отправки Telegram уведомления пользователю', telegram_id=user.telegram_id, e=e)
            return False

        except Exception as e:
            logger.error('Неожиданная ошибка при отправке Telegram уведомления', e=e)
            return False

    async def _send_email_notification(
        self,
        user: User,
        notification_type: NotificationType,
        context: dict[str, Any],
    ) -> bool:
        """Send notification via email."""
        if not self.email_service.is_configured():
            logger.debug('SMTP не настроен, пропускаем email уведомление')
            return False

        if not user.email or not user.email_verified:
            logger.debug('У пользователя нет подтверждённого email', user_id=user.id)
            return False

        try:
            # Get email template (check DB override first, then fall back to hardcoded)
            language = user.language or 'ru'

            # Try DB override
            template = None
            try:
                from app.cabinet.services.email_template_overrides import get_template_override

                override = await get_template_override(notification_type.value, language)
                if override:
                    # Wrap custom body in base template
                    full_html = self.email_templates._get_base_template(override['body_html'], language)
                    template = {
                        'subject': override['subject'],
                        'body_html': full_html,
                    }
            except Exception as e:
                logger.debug('Не удалось проверить override шаблона', e=e)

            if not template:
                template = self.email_templates.get_template(notification_type, language, context)

            if not template:
                logger.warning('Не найден email шаблон для', notification_type_value=notification_type.value)
                return False

            # Send email (sync smtplib — run in thread to avoid blocking event loop)
            success = await asyncio.to_thread(
                self.email_service.send_email,
                to_email=user.email,
                subject=template['subject'],
                body_html=template['body_html'],
                body_text=template.get('body_text'),
            )

            if success:
                logger.info(
                    'Email уведомление отправлено пользователю',
                    notification_type_value=notification_type.value,
                    user_id=user.id,
                    email=user.email,
                )

            return success

        except Exception as e:
            logger.error('Ошибка отправки email уведомления пользователю', user_id=user.id, e=e)
            return False

    async def _send_websocket_notification(
        self,
        user: User,
        notification_type: NotificationType,
        context: dict[str, Any],
    ) -> bool:
        """Send notification via WebSocket to cabinet."""
        try:
            message = {
                'type': f'notification.{notification_type.value}',
                **context,
            }

            await self.ws_manager.send_to_user(user.id, message)
            return True

        except Exception as e:
            logger.debug('WebSocket уведомление не отправлено пользователю', user_id=user.id, e=e)
            return False

    # ============================================================================
    # Convenience methods for common notification types
    # ============================================================================

    async def notify_balance_topup(
        self,
        user: User,
        amount_kopeks: int,
        new_balance_kopeks: int,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
    ) -> bool:
        """Notify user about balance top-up."""
        context = {
            'amount_kopeks': amount_kopeks,
            'amount_rubles': amount_kopeks / 100,
            'new_balance_kopeks': new_balance_kopeks,
            'new_balance_rubles': new_balance_kopeks / 100,
            'formatted_amount': settings.format_price(amount_kopeks),
            'formatted_balance': settings.format_price(new_balance_kopeks),
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.BALANCE_TOPUP,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
        )

    async def notify_subscription_expiring(
        self,
        user: User,
        days_left: int,
        expires_at: Any,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
    ) -> bool:
        """Notify user about expiring subscription."""
        context = {
            'days_left': days_left,
            'expires_at': str(expires_at),
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.SUBSCRIPTION_EXPIRING,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
        )

    async def notify_subscription_expired(
        self,
        user: User,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
    ) -> bool:
        """Notify user about expired subscription."""
        return await self.send_notification(
            user=user,
            notification_type=NotificationType.SUBSCRIPTION_EXPIRED,
            context={},
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
        )

    async def notify_autopay_success(
        self,
        user: User,
        amount_kopeks: int,
        new_expires_at: Any,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
    ) -> bool:
        """Notify user about successful autopay."""
        context = {
            'amount_kopeks': amount_kopeks,
            'amount_rubles': amount_kopeks / 100,
            'formatted_amount': settings.format_price(amount_kopeks),
            'new_expires_at': str(new_expires_at),
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.AUTOPAY_SUCCESS,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
        )

    async def notify_autopay_failed(
        self,
        user: User,
        reason: str,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
    ) -> bool:
        """Notify user about failed autopay."""
        context = {
            'reason': reason,
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.AUTOPAY_FAILED,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
        )

    async def notify_ban(
        self,
        user: User,
        reason: str | None = None,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
    ) -> bool:
        """Notify user about account ban."""
        context = {
            'reason': reason or 'Нарушение правил использования',
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.BAN_NOTIFICATION,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
        )

    async def notify_unban(
        self,
        user: User,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
    ) -> bool:
        """Notify user about account unban."""
        return await self.send_notification(
            user=user,
            notification_type=NotificationType.UNBAN_NOTIFICATION,
            context={},
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
        )

    async def notify_referral_bonus(
        self,
        user: User,
        bonus_kopeks: int,
        referral_name: str,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
        message_effect_id: str | None = None,
    ) -> bool:
        """Notify user about referral bonus."""
        context = {
            'bonus_kopeks': bonus_kopeks,
            'bonus_rubles': bonus_kopeks / 100,
            'formatted_bonus': settings.format_price(bonus_kopeks),
            'referral_name': referral_name,
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.REFERRAL_BONUS,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
            message_effect_id=message_effect_id,
        )

    async def notify_referral_registered(
        self,
        user: User,
        referral_name: str,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
        message_effect_id: str | None = None,
    ) -> bool:
        """Notify user about new referral registration."""
        context = {
            'referral_name': referral_name,
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.REFERRAL_REGISTERED,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
            message_effect_id=message_effect_id,
        )

    async def notify_gift_accepted(
        self,
        user: User,
        recipient_name: str,
        tariff_name: str,
        period_days: int,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
        message_effect_id: str | None = None,
    ) -> bool:
        """Notify user (gifter) that their gift has been accepted/activated."""
        context = {
            'recipient_name': recipient_name,
            'tariff_name': tariff_name,
            'period_days': period_days,
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.GIFT_ACCEPTED,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
            message_effect_id=message_effect_id,
        )

    async def notify_gift_received(
        self,
        user: User,
        gifter_name: str,
        tariff_name: str,
        period_days: int,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
        message_effect_id: str | None = None,
    ) -> bool:
        """Notify user (recipient) that they have received a gift subscription."""
        context = {
            'gifter_name': gifter_name,
            'tariff_name': tariff_name,
            'period_days': period_days,
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.GIFT_RECEIVED,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
            message_effect_id=message_effect_id,
        )

    async def notify_partner_approved(
        self,
        user: User,
        commission_percent: int,
        comment: str | None = None,
        bot: Bot | None = None,
        telegram_message: str | None = None,
    ) -> bool:
        """Notify user about partner application approval."""
        context = {
            'commission_percent': commission_percent,
            'comment': comment or '',
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.PARTNER_APPLICATION_APPROVED,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
        )

    async def notify_partner_rejected(
        self,
        user: User,
        comment: str | None = None,
        bot: Bot | None = None,
        telegram_message: str | None = None,
    ) -> bool:
        """Notify user about partner application rejection."""
        context = {
            'comment': comment or '',
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.PARTNER_APPLICATION_REJECTED,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
        )

    async def notify_withdrawal_approved(
        self,
        user: User,
        amount_kopeks: int,
        comment: str | None = None,
        bot: Bot | None = None,
        telegram_message: str | None = None,
    ) -> bool:
        """Notify user about withdrawal request approval."""
        context = {
            'amount_kopeks': amount_kopeks,
            'amount_rubles': amount_kopeks / 100,
            'formatted_amount': settings.format_price(amount_kopeks),
            'comment': comment or '',
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.WITHDRAWAL_APPROVED,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
        )

    async def notify_withdrawal_rejected(
        self,
        user: User,
        amount_kopeks: int,
        comment: str | None = None,
        bot: Bot | None = None,
        telegram_message: str | None = None,
    ) -> bool:
        """Notify user about withdrawal request rejection."""
        context = {
            'amount_kopeks': amount_kopeks,
            'amount_rubles': amount_kopeks / 100,
            'formatted_amount': settings.format_price(amount_kopeks),
            'comment': comment or '',
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.WITHDRAWAL_REJECTED,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
        )

    async def notify_daily_debit(
        self,
        user: User,
        amount_kopeks: int,
        new_balance_kopeks: int,
        bot: Bot | None = None,
        telegram_message: str | None = None,
        telegram_markup: Any | None = None,
    ) -> bool:
        """Notify user about daily subscription debit."""
        context = {
            'amount_kopeks': amount_kopeks,
            'amount_rubles': amount_kopeks / 100,
            'formatted_amount': settings.format_price(amount_kopeks),
            'new_balance_kopeks': new_balance_kopeks,
            'new_balance_rubles': new_balance_kopeks / 100,
            'formatted_balance': settings.format_price(new_balance_kopeks),
        }

        return await self.send_notification(
            user=user,
            notification_type=NotificationType.DAILY_DEBIT,
            context=context,
            bot=bot,
            telegram_message=telegram_message,
            telegram_markup=telegram_markup,
        )


# Singleton instance
notification_delivery_service = NotificationDeliveryService()
