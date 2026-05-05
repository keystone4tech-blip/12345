"""Gift system routes for cabinet."""

import uuid
from datetime import datetime, UTC

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.tariff import get_tariff_by_id, get_all_tariffs
from app.database.crud.transaction import create_transaction
from app.database.crud.user import subtract_user_balance, get_user_by_id
from app.database.models import Gift, Tariff, TransactionType, User, Subscription
from app.utils.formatters import strip_telegram_tags

from ..dependencies import get_cabinet_db, get_current_cabinet_user
from ..schemas.gift import (
    GiftConfig,
    GiftTariff,
    GiftTariffPeriod,
    GiftPurchaseRequest,
    GiftPurchaseResponse,
    GiftPurchaseStatus,
    PendingGift,
    SentGift,
    ReceivedGift,
    ActivateGiftResponse,
    ActivateGiftRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix='/gift', tags=['Cabinet Gift'])


@router.get('/config', response_model=GiftConfig)
async def get_gift_config(
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get gift system configuration and available tariffs."""
    # Check if gifts are enabled via branding/settings
    from .branding import get_setting_value, GIFT_ENABLED_KEY
    gift_enabled_val = await get_setting_value(db, GIFT_ENABLED_KEY)
    is_enabled = gift_enabled_val.lower() == 'true' if gift_enabled_val else getattr(settings, 'GIFTS_ENABLED', False)

    # Get active tariffs
    tariffs = await get_all_tariffs(db, include_inactive=False)
    
    gift_tariffs = []
    for t in tariffs:
        if t.is_trial_available:  # Skip trial-only tariffs
            continue
            
        periods = []
        if t.period_prices:
            for days_str, price in t.period_prices.items():
                try:
                    days = int(days_str)
                    periods.append(GiftTariffPeriod(
                        days=days,
                        price_kopeks=price,
                        price_label=f"{price / 100} RUB",
                        original_price_kopeks=None,
                        discount_percent=None
                    ))
                except (ValueError, TypeError):
                    continue
            
        gift_tariffs.append(GiftTariff(
            id=t.id,
            name=strip_telegram_tags(t.name),
            description=t.description,
            traffic_limit_gb=t.traffic_limit_gb,
            device_limit=t.device_limit,
            periods=sorted(periods, key=lambda x: x.days)
        ))

    return GiftConfig(
        is_enabled=is_enabled,
        tariffs=gift_tariffs,
        payment_methods=[],  # Minimal implementation: balance only
        balance_kopeks=user.balance_kopeks,
        currency_symbol="RUB",
        promo_group_name=None,
        active_discount_percent=None,
        active_discount_expires_at=None
    )


@router.post('/purchase', response_model=GiftPurchaseResponse)
async def create_gift_purchase(
    request: GiftPurchaseRequest,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Purchase a gift subscription."""
    # 1. Validate tariff
    tariff = await get_tariff_by_id(db, request.tariff_id)
    if not tariff or not tariff.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tariff not found or inactive")

    # 2. Find period price
    price = None
    if tariff.period_prices:
        price = tariff.period_prices.get(str(request.period_days))
    
    if price is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid period for this tariff")

    # 3. Process payment
    if request.payment_mode == 'balance':
        if user.balance_kopeks < price:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient balance")
            
        # Deduct balance
        await subtract_user_balance(db, user.id, price)
        
        # Create transaction
        await create_transaction(
            db,
            user_id=user.id,
            amount_kopeks=-price,
            transaction_type=TransactionType.GIFT_VPN,
            description=f"Purchase gift: {tariff.name} ({request.period_days} days)"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="External payment methods are not supported in this version of cabinet gifts"
        )

    # 4. Create gift
    token = str(uuid.uuid4()).replace('-', '')[:32]
    gift = Gift(
        token=token,
        tariff_id=tariff.id,
        period_days=request.period_days,
        gifter_id=user.id,
        is_used=False,
        created_at=datetime.now(UTC)
    )
    db.add(gift)
    await db.commit()

    logger.info('User purchased a gift', user_id=user.id, tariff_id=tariff.id, token=token)

    return GiftPurchaseResponse(
        status='paid',
        purchase_token=token,
        payment_url=None,
        warning=None
    )


@router.get('/pending', response_model=list[PendingGift])
async def get_pending_gifts(
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get gifts purchased by user that are not yet activated."""
    query = (
        select(Gift)
        .where(Gift.gifter_id == user.id, Gift.is_used == False)
        .order_by(desc(Gift.created_at))
    )
    result = await db.execute(query)
    gifts = result.scalars().all()
    
    items = []
    for g in gifts:
        # Load tariff (can be optimized with selectinload)
        tariff = await get_tariff_by_id(db, g.tariff_id)
        items.append(PendingGift(
            token=g.token,
            tariff_name=strip_telegram_tags(tariff.name) if tariff else "Unknown",
            period_days=g.period_days,
            gift_message=None,
            sender_display=user.display_name or user.username or "Anonymous",
            created_at=g.created_at
        ))
    return items


@router.get('/sent', response_model=list[SentGift])
async def get_sent_gifts(
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get all gifts sent by user."""
    query = (
        select(Gift)
        .where(Gift.gifter_id == user.id)
        .order_by(desc(Gift.created_at))
    )
    result = await db.execute(query)
    gifts = result.scalars().all()
    
    items = []
    for g in gifts:
        tariff = await get_tariff_by_id(db, g.tariff_id)
        recipient = None
        if g.recipient_id:
            recipient = await get_user_by_id(db, g.recipient_id)
        
        items.append(SentGift(
            token=g.token,
            tariff_name=strip_telegram_tags(tariff.name) if tariff else "Unknown",
            period_days=g.period_days,
            device_limit=tariff.device_limit if tariff else 0,
            status="activated" if g.is_used else "pending",
            gift_recipient_value=recipient.display_name if recipient else None,
            gift_message=None,
            activated_by_username=recipient.username if recipient else None,
            created_at=g.created_at
        ))
    return items


@router.get('/received', response_model=list[ReceivedGift])
async def get_received_gifts(
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get all gifts received and activated by user."""
    query = (
        select(Gift)
        .where(Gift.recipient_id == user.id)
        .order_by(desc(Gift.activated_at))
    )
    result = await db.execute(query)
    gifts = result.scalars().all()
    
    items = []
    for g in gifts:
        tariff = await get_tariff_by_id(db, g.tariff_id)
        gifter = None
        if g.gifter_id:
            gifter = await get_user_by_id(db, g.gifter_id)
        
        items.append(ReceivedGift(
            token=g.token,
            tariff_name=strip_telegram_tags(tariff.name) if tariff else "Unknown",
            period_days=g.period_days,
            device_limit=tariff.device_limit if tariff else 0,
            status="activated",
            sender_display=gifter.display_name if gifter else "System",
            gift_message=None,
            created_at=g.created_at
        ))
    return items


@router.post('/activate', response_model=ActivateGiftResponse)
async def activate_gift(
    request: ActivateGiftRequest,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Activate a gift code."""
    # Find gift
    query = select(Gift).where(Gift.token == request.code)
    result = await db.execute(query)
    gift = result.scalar_one_or_none()
    
    if not gift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gift code not found")
        
    if gift.is_used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gift already activated")
        
    # Get tariff
    tariff = await get_tariff_by_id(db, gift.tariff_id)
    if not tariff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tariff no longer exists")

    # Process activation
    from app.database.crud.subscription import (
        create_paid_subscription, 
        extend_subscription, 
        get_subscription_by_user_id
    )
    
    sub = await get_subscription_by_user_id(db, user.id)
    if sub:
        # Extend existing subscription
        # Note: In a production system, we should check if the tariff is compatible.
        # For simplicity, we just add days.
        await extend_subscription(db, sub.id, gift.period_days)
    else:
        # Create new subscription
        await create_paid_subscription(
            db, 
            user_id=user.id, 
            tariff_id=tariff.id, 
            days=gift.period_days
        )
        
    # Mark gift as used
    gift.is_used = True
    gift.recipient_id = user.id
    gift.activated_at = datetime.now(UTC)
    
    await db.commit()
    
    logger.info('User activated a gift', user_id=user.id, token=gift.token)
    
    return ActivateGiftResponse(
        status='ok',
        tariff_name=strip_telegram_tags(tariff.name),
        period_days=gift.period_days
    )
