"""Gift system routes for cabinet."""

import uuid
from datetime import datetime, UTC

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, desc, func
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
    SendGiftToUserRequest,
    SendGiftToUserResponse,
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
            description=strip_telegram_tags(t.description) if t.description else None,
            traffic_limit_gb=t.traffic_limit_gb,
            device_limit=t.device_limit,
            periods=sorted(periods, key=lambda x: x.days)
        ))

    # Динамически получаем доступные платежные методы для текущего пользователя
    # Импортируем get_payment_methods из соседнего модуля balance для получения активных в системе шлюзов
    from .balance import get_payment_methods
    from ..schemas.gift import GiftPaymentMethod, GiftPaymentMethodSubOption
    
    # Получаем актуальный список платежных шлюзов (ЮКасса, Platega, PAL24 и т.д.)
    balance_methods = await get_payment_methods(user=user, db=db)
    gift_payment_methods = []
    
    # Итерируемся по методам и приводим их к схеме GiftPaymentMethod
    for bm in balance_methods:
        sub_opts = None
        # Если у платежного метода есть под-опции (например, СБП/карта у ЮКасса), добавляем их
        if bm.options:
            sub_opts = [
                GiftPaymentMethodSubOption(id=opt['id'], name=opt['name'])
                for opt in bm.options
            ]
        gift_payment_methods.append(GiftPaymentMethod(
            method_id=bm.id,
            display_name=bm.name,
            description=bm.description,
            icon_url=None, # Иконку фронтенд может подбирать автоматически или рендерить дефолтную
            min_amount_kopeks=bm.min_amount_kopeks,
            max_amount_kopeks=bm.max_amount_kopeks,
            sub_options=sub_opts
        ))

    # Логируем загрузку конфигурации подарков для аудита
    logger.debug(
        "Loaded gift config for user",
        user_id=user.id,
        is_enabled=is_enabled,
        payment_methods_count=len(gift_payment_methods),
    )

    return GiftConfig(
        is_enabled=is_enabled,
        tariffs=gift_tariffs,
        payment_methods=gift_payment_methods,
        balance_kopeks=user.balance_kopeks,
        currency_symbol="RUB",
        promo_group_name=None,
        active_discount_percent=None,
        active_discount_expires_at=None
    )



def _format_days(days: int) -> str:
    """
    Вспомогательная функция для корректного склонения слова 'день' на русском языке.
    Пример:
    - 1 день, 21 день, 31 день
    - 2 дня, 3 дня, 4 дня
    - 5 дней, 11 дней, 14 дней
    """
    if days % 10 == 1 and days % 100 != 11:
        return f"{days} день"
    elif 2 <= days % 10 <= 4 and not (12 <= days % 100 <= 14):
        return f"{days} дня"
    else:
        return f"{days} дней"


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
            
        # Форматируем период действия подарка на русском языке (например: 14 дней, 1 день)
        formatted_period = _format_days(request.period_days)
        desc = f"Покупка подарка: {tariff.name} ({formatted_period})"
        
        # Логируем начало списания средств
        logger.info(
            "Attempting to subtract balance for gift purchase",
            user_id=user.id,
            price_kopeks=price,
            tariff_name=tariff.name,
            period_days=request.period_days
        )
        
        # Списываем средства с баланса пользователя
        await subtract_user_balance(db, user, price, description=desc)
        
        # Создаем финансовую транзакцию в БД с русским описанием
        await create_transaction(
            db,
            user_id=user.id,
            amount_kopeks=-price,
            type=TransactionType.GIFT_VPN,
            description=desc
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="External payment methods are not supported in this version of cabinet gifts"
        )

    # 4. Create gift
    token = uuid.uuid4().hex[:12]
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
    """Get gifts received by user that are not yet activated."""
    query = (
        select(Gift)
        .where(Gift.recipient_id == user.id, Gift.is_used == False)
        .order_by(desc(Gift.created_at))
    )
    result = await db.execute(query)
    gifts = result.scalars().all()
    
    items = []
    for g in gifts:
        # Load tariff (can be optimized with selectinload)
        tariff = await get_tariff_by_id(db, g.tariff_id)
        
        # Load actual gifter's info
        gifter = None
        if g.gifter_id:
            gifter = await get_user_by_id(db, g.gifter_id)
            
        sender_display = "Anonymous"
        if gifter:
            sender_display = gifter.full_name or gifter.username or "Anonymous"
            
        items.append(PendingGift(
            token=g.token,
            tariff_name=strip_telegram_tags(tariff.name) if tariff else "Unknown",
            period_days=g.period_days,
            gift_message=None,
            sender_display=sender_display,
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
            
        recipient_display = None
        if recipient:
            recipient_display = f"@{recipient.username}" if recipient.username else (recipient.full_name or "Пользователь")
        
        items.append(SentGift(
            token=g.token,
            tariff_name=strip_telegram_tags(tariff.name) if tariff else "Unknown",
            period_days=g.period_days,
            device_limit=tariff.device_limit if tariff else 0,
            status="activated" if g.is_used else "pending",
            gift_recipient_value=recipient_display,
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
            sender_display=gifter.full_name if gifter else "System",
            gift_message=None,
            created_at=g.created_at
        ))
    return items


@router.post('/activate', response_model=ActivateGiftResponse)
async def activate_gift(
    req: Request,
    payload: ActivateGiftRequest,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Activate a gift code."""
    from app.services.gift_service import GiftService
    
    bot = getattr(req.app.state, 'bot', None)
    
    result = await GiftService.activate_gift(db, user, payload.code, bot)
    
    if not result.get("success"):
        error = result.get("error")
        if error == "invalid_token":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gift code not found or already activated")
        elif error == "tariff_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tariff no longer exists")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
            
    return ActivateGiftResponse(
        status='ok',
        tariff_name=strip_telegram_tags(result.get("tariff_name")) if result.get("tariff_name") else "VPN",
        period_days=result.get("period")
    )


@router.post('/send-to-user', response_model=SendGiftToUserResponse)
async def send_gift_to_user(
    req: Request,
    payload: SendGiftToUserRequest,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Отправить подарок конкретному пользователю по его никнейму Telegram (регистронезависимо)."""
    logger.info("Direct gift send request initiated", user_id=user.id, token=payload.token, username=payload.username)

    # 1. Очистка никнейма от пробелов и возможного префикса @
    cleaned_username = payload.username.strip()
    if cleaned_username.startswith('@'):
        cleaned_username = cleaned_username[1:]
    
    if not cleaned_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Никнейм пользователя не может быть пустым."
        )

    # 2. Поиск получателя в базе данных (регистронезависимо)
    query_recipient = select(User).where(func.lower(User.username) == func.lower(cleaned_username))
    result_recipient = await db.execute(query_recipient)
    recipient = result_recipient.scalars().first()

    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с никнеймом @{cleaned_username} не зарегистрирован в личном кабинете."
        )

    # 3. Защита от отправки самому себе
    if recipient.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Вы не можете отправить подарок самому себе."
        )

    # 4. Поиск подарка в базе данных по токену и проверка прав (даритель должен быть текущим пользователем)
    # Очищаем токен подарка от возможного префикса GIFT-
    cleaned_token = payload.token.replace("GIFT-", "").strip()
    
    query_gift = select(Gift).where(Gift.token == cleaned_token, Gift.gifter_id == user.id)
    result_gift = await db.execute(query_gift)
    gift = result_gift.scalars().first()

    if not gift:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Подарок с указанным кодом не найден."
        )

    # 5. Проверка статуса подарка: не активирован ли он и не отправлен ли уже кому-то другому
    if gift.is_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот подарок уже был активирован."
        )

    if gift.recipient_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот подарок уже отправлен другому пользователю."
        )

    # 6. Привязка получателя к подарку
    gift.recipient_id = recipient.id
    await db.commit()
    logger.info("Gift recipient updated successfully", gift_id=gift.id, recipient_id=recipient.id)

    # 7. Отправка уведомления получателю в Telegram через бот (если привязан telegram_id)
    if recipient.telegram_id:
        bot = getattr(req.app.state, 'bot', None)
        if bot:
            try:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                
                # Формируем красивое сообщение с кнопкой
                gifter_name = user.full_name or (f"@{user.username}" if user.username else "Пользователь")
                
                tariff = await get_tariff_by_id(db, gift.tariff_id)
                tariff_name = strip_telegram_tags(tariff.name) if tariff else "VPN подписка"
                
                text = (
                    f"🎁 <b>Вам прислали подарок!</b>\n\n"
                    f"Пользователь {gifter_name} отправил вам подарок: "
                    f"подписку на тариф <b>{tariff_name}</b> на <b>{gift.period_days} дней</b>.\n\n"
                    f"Вы можете прямо сейчас активировать её в личном кабинете!"
                )
                
                cabinet_url = getattr(settings, 'CABINET_URL', 'https://lk.mozhnovpn.tech')
                # Добавляем код подарка в URL, чтобы на фронтенде он мог автозаполниться
                activation_url = f"{cabinet_url}/gift?tab=activate&code={gift.token}"
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🎁 Активировать подарок",
                            url=activation_url
                        )
                    ]
                ])
                
                await bot.send_message(
                    chat_id=recipient.telegram_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                logger.info("Telegram notification sent to recipient", recipient_id=recipient.id, telegram_id=recipient.telegram_id)
            except Exception as e:
                # Ошибка отправки сообщения в TG не должна приводить к падению API
                logger.warning(
                    "Failed to send Telegram notification to gift recipient",
                    recipient_id=recipient.id,
                    error=str(e)
                )
        else:
            logger.warning("Bot instance is not found in app state, skipping notification")
    else:
        logger.info("Recipient does not have a linked Telegram account, skipping notification", recipient_id=recipient.id)

    return SendGiftToUserResponse(
        status="ok",
        message="Подарок успешно отправлен получателю!"
    )
