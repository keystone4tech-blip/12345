"""Notification settings routes for cabinet."""

from datetime import datetime, UTC
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User

from ..dependencies import get_cabinet_db, get_current_cabinet_user


logger = structlog.get_logger(__name__)

router = APIRouter(prefix='/notifications', tags=['Cabinet Notifications'])


# ============ Schemas ============


class NotificationSettingsResponse(BaseModel):
    """User notification settings."""

    subscription_expiry_enabled: bool = True
    subscription_expiry_days: int = 3
    traffic_warning_enabled: bool = True
    traffic_warning_percent: int = 80
    balance_low_enabled: bool = True
    balance_low_threshold: int = 100  # kopeks
    news_enabled: bool = True
    promo_offers_enabled: bool = True


class NotificationSettingsUpdate(BaseModel):
    """Update notification settings."""

    subscription_expiry_enabled: bool | None = None
    subscription_expiry_days: int | None = Field(None, ge=1, le=30)
    traffic_warning_enabled: bool | None = None
    traffic_warning_percent: int | None = Field(None, ge=50, le=99)
    balance_low_enabled: bool | None = None
    balance_low_threshold: int | None = Field(None, ge=0)
    news_enabled: bool | None = None
    promo_offers_enabled: bool | None = None


# ============ Helpers ============


def _get_notification_settings(user: User) -> dict[str, Any]:
    """Get notification settings from user object."""
    # Try to get from user's settings field or use defaults
    settings_data = getattr(user, 'notification_settings', None) or {}

    return {
        'subscription_expiry_enabled': settings_data.get('subscription_expiry_enabled', True),
        'subscription_expiry_days': settings_data.get('subscription_expiry_days', 3),
        'traffic_warning_enabled': settings_data.get('traffic_warning_enabled', True),
        'traffic_warning_percent': settings_data.get('traffic_warning_percent', 80),
        'balance_low_enabled': settings_data.get('balance_low_enabled', True),
        'balance_low_threshold': settings_data.get('balance_low_threshold', 100),
        'news_enabled': settings_data.get('news_enabled', True),
        'promo_offers_enabled': settings_data.get('promo_offers_enabled', True),
    }


def _update_notification_settings(user: User, updates: dict[str, Any]) -> dict[str, Any]:
    """Update notification settings on user object."""
    current_settings = _get_notification_settings(user)

    for key, value in updates.items():
        if value is not None:
            current_settings[key] = value

    return current_settings


# ============ Routes ============


@router.get('', response_model=NotificationSettingsResponse)
async def get_notification_settings(
    user: User = Depends(get_current_cabinet_user),
):
    """Get user's notification settings."""
    settings = _get_notification_settings(user)
    return NotificationSettingsResponse(**settings)


@router.patch('', response_model=NotificationSettingsResponse)
async def update_notification_settings(
    request: NotificationSettingsUpdate,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Update user's notification settings."""
    updates = request.model_dump(exclude_unset=True)

    if not updates:
        # No updates provided, return current settings
        settings = _get_notification_settings(user)
        return NotificationSettingsResponse(**settings)

    # Update settings
    new_settings = _update_notification_settings(user, updates)

    # Store in user object
    if not hasattr(user, 'notification_settings') or user.notification_settings is None:
        user.notification_settings = {}

    user.notification_settings = new_settings
    user.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(user)

    return NotificationSettingsResponse(**new_settings)


@router.post('/test')
async def send_test_notification(
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Отправка тестового push-уведомления пользователю."""
    # Переменная для отслеживания успешной отправки хотя бы одного пуша
    push_sent = False
    # Список ошибок при отправке
    push_errors = []
    
    from sqlalchemy import select
    from app.database.models import PushSubscription
    from fastapi import HTTPException
    
    # Логируем начало запроса тестового пуша
    logger.info("Запрос тестового пуш-уведомления", user_id=user.id)
    
    # Выбираем все активные подписки данного пользователя из базы данных
    stmt = select(PushSubscription).where(PushSubscription.user_id == user.id)
    result = await db.execute(stmt)
    subscriptions = result.scalars().all()
    
    # Если подписок не найдено, сразу возвращаем ошибку 400 с подробным описанием
    if not subscriptions:
        logger.warning("Отмена отправки тест-пуша: у пользователя нет активных подписок", user_id=user.id)
        raise HTTPException(
            status_code=400,
            detail="Не найдено активных подписок на push-уведомления для вашего аккаунта на этом устройстве. Пожалуйста, включите переключатель push-уведомлений ниже перед отправкой теста."
        )
        
    from pywebpush import webpush, WebPushException
    import json
    from app.config import settings
    
    # Формируем полезную нагрузку (payload) пуш-уведомления
    payload = {
        "title": "MozhnoVPN — Тест",
        "body": "Ваши пуш-уведомления успешно настроены и работают! 🎉",
        "icon": "/icons/icon-192x192.png",
        "badge": "/icons/icon-192x192.png",
        "data": {
            "url": "/profile"
        }
    }
    
    # Проходим по всем зарегистрированным подпискам пользователя
    for sub in subscriptions:
        try:
            logger.info("Попытка отправки тестового пуша", user_id=user.id, subscription_id=sub.id)
            from app.utils.vapid import generate_vapid_headers
            vapid_headers = generate_vapid_headers(sub.endpoint)
            
            # Отправляем пуш-пакет через службу push-уведомлений браузера с использованием VAPID
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
            push_sent = True
            logger.info("Тестовый пуш успешно отправлен в push-сервис", user_id=user.id, subscription_id=sub.id)
        except WebPushException as e:
            # Если подписка устарела или удалена на стороне браузера (410 Gone) — удаляем её из базы данных
            logger.warning("Ошибка отправки web push", error=str(e), subscription_id=sub.id)
            push_errors.append(str(e))
            if getattr(e, 'response', None) is not None and e.response.status_code == 410:
                logger.info("Удаление устаревшей подписки на пуши из БД", subscription_id=sub.id)
                await db.delete(sub)
                await db.commit()
        except Exception as e:
            # Логируем другие непредвиденные ошибки
            logger.error("Непредвиденная ошибка во время отправки web push", error=str(e))
            push_errors.append(str(e))

    # Если ни один пуш не был успешно отправлен, возвращаем ошибку 400
    if not push_sent:
        logger.error("Не удалось доставить тестовый пуш ни на одно устройство", user_id=user.id, errors=push_errors)
        raise HTTPException(
            status_code=400,
            detail=f"Не удалось отправить тестовое push-уведомление. Ошибки: {', '.join(push_errors)}"
        )

    return {
        'success': True,
        'message': 'Тестовое уведомление успешно отправлено на ваши устройства.',
        'push_sent': push_sent,
        'push_subscriptions_count': len(subscriptions),
        'push_errors': push_errors
    }


@router.get('/history')
async def get_notification_history(
    limit: int = 20,
    offset: int = 0,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get user's notification history."""
    # For now, return empty list - notification history can be implemented later
    # when there's a notification log table
    return {
        'notifications': [],
        'total': 0,
        'limit': limit,
        'offset': offset,
    }
