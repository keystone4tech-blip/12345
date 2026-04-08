"""Обработчики функционала «Подарить VPN»."""

import urllib.parse
import structlog
from datetime import datetime, UTC
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database.crud.tariff import get_tariff_by_id, get_tariffs_for_user
from app.database.crud.transaction import create_transaction
from app.database.crud.user import subtract_user_balance
from app.database.models import Tariff, TransactionType, User, Transaction
from app.handlers.subscription.tariff_purchase import (
    _format_price_kopeks,
    _format_period,
    _apply_promo_discount,
    _get_user_period_discount,
    format_tariffs_list_text,
)
from app.localization.texts import get_texts
from app.services.gift_service import GiftService
from app.utils.decorators import error_handler

logger = structlog.get_logger(__name__)


def get_gift_tariffs_keyboard(
    tariffs: list[Tariff],
    language: str,
) -> InlineKeyboardMarkup:
    """Клавиатура выбора тарифов для подарка."""
    texts = get_texts(language)
    buttons = []

    for tariff in tariffs:
        buttons.append([InlineKeyboardButton(text=tariff.name, callback_data=f'gift_tariff_select:{tariff.id}')])

    buttons.append([InlineKeyboardButton(text=texts.BACK, callback_data='back_to_menu')])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_gift_history_keyboard(language: str) -> InlineKeyboardMarkup:
    """Клавиатура для возврата из истории подарков."""
    texts = get_texts(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.BACK, callback_data='gifts_start')]]
    )


def get_gift_tariff_periods_keyboard(
    tariff: Tariff,
    language: str,
    db_user: User | None = None,
) -> InlineKeyboardMarkup:
    """Клавиатура выбора периода для подарочного тарифа."""
    texts = get_texts(language)
    buttons = []

    prices = tariff.period_prices or {}
    for period_str in sorted(prices.keys(), key=int):
        period = int(period_str)
        price = prices[period_str]

        # Получаем скидку
        discount_percent = 0
        if db_user:
            discount_percent = _get_user_period_discount(db_user, period)

        if discount_percent > 0:
            price = _apply_promo_discount(price, discount_percent)
            price_text = f'{_format_price_kopeks(price)} 🔥−{discount_percent}%'
        else:
            price_text = _format_price_kopeks(price)

        button_text = f'{_format_period(period)} — {price_text}'
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f'gift_tariff_period:{tariff.id}:{period}')])

    buttons.append([InlineKeyboardButton(text=texts.BACK, callback_data='gifts_start')])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_gift_confirm_keyboard(
    tariff_id: int,
    period: int,
    language: str,
) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения подарка."""
    texts = get_texts(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='✅ Подтвердить подарок', callback_data=f'gift_confirm:{tariff_id}:{period}')],
            [InlineKeyboardButton(text=texts.BACK, callback_data=f'gift_tariff_select:{tariff_id}')],
        ]
    )


def get_gift_insufficient_balance_keyboard(
    tariff_id: int,
    period: int,
    language: str,
) -> InlineKeyboardMarkup:
    """Клавиатура при недостаточном балансе для подарка."""
    texts = get_texts(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='💳 Пополнить баланс', callback_data='balance_topup')],
            [InlineKeyboardButton(text=texts.BACK, callback_data=f'gift_tariff_select:{tariff_id}')],
        ]
    )


@error_handler
async def gift_vpn_start(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
    state: FSMContext,
):
    """Показывает список тарифов для подарка."""
    texts = get_texts(db_user.language)
    await state.clear()

    # Для подарков не показываем суточные тарифы, только с фиксированным периодом
    promo_group_id = getattr(db_user, 'promo_group_id', None)
    all_tariffs = await get_tariffs_for_user(db, promo_group_id)
    
    # Фильтруем суточные тарифы
    tariffs = [t for t in all_tariffs if not getattr(t, 'is_daily', False)]

    if not tariffs:
        await callback.message.edit_text(
            '😔 <b>Нет доступных тарифов для подарка</b>',
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=texts.BACK, callback_data='back_to_menu')]]
            ),
            parse_mode='HTML',
        )
        await callback.answer()
        return

    # Проверяем скидки
    promo_group = getattr(db_user, 'promo_group', None)
    has_period_discounts = False
    if promo_group:
        period_discounts = getattr(promo_group, 'period_discounts', None)
        if period_discounts and isinstance(period_discounts, dict) and len(period_discounts) > 0:
            has_period_discounts = True

    tariffs_text = format_tariffs_list_text(tariffs, db_user, has_period_discounts)
    
    welcome_text = (
        "🎁 <b>Подарить VPN</b>\n\n"
        "Сделайте приятный и полезный подарок вашему другу, родственнику или коллеге! 🎉\n\n"
        "Выберите тариф и период — мы спишем средства с вашего баланса и сформируем уникальную ссылку. "
        "Отправьте её получателю, и при переходе в бота выбранный тариф активируется <b>автоматически</b>.\n\n"
        "⚠️ <i>Ссылка будет действительна 30 дней.</i>\n\n"
    )

    await callback.message.edit_text(
        welcome_text + tariffs_text, 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            *get_gift_tariffs_keyboard(tariffs, db_user.language).inline_keyboard[:-1],
            [InlineKeyboardButton(text='🎁 Мои подарки', callback_data='gift_history')],
            [InlineKeyboardButton(text=texts.BACK, callback_data='back_to_menu')]
        ]), 
        parse_mode='HTML'
    )
    await callback.answer()


@error_handler
async def gift_select_tariff(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    """Выбор периода для подарочного тарифа."""
    tariff_id = int(callback.data.split(':')[1])
    tariff = await get_tariff_by_id(db, tariff_id)

    if not tariff or not tariff.is_active or getattr(tariff, 'is_daily', False):
        await callback.answer('Тариф недоступен', show_alert=True)
        return

    traffic = 'Безлимит' if tariff.traffic_limit_gb == 0 else f'{tariff.traffic_limit_gb} ГБ'
    
    text = (
        f"🎁 <b>Подарок: {tariff.name}</b>\n\n"
        f"<b>Параметры:</b>\n"
        f"• Трафик: {traffic}\n"
        f"• Устройств: {tariff.device_limit}\n\n"
        f"Выберите период для подарка:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_gift_tariff_periods_keyboard(tariff, db_user.language, db_user=db_user),
        parse_mode='HTML',
    )
    await callback.answer()


@error_handler
async def gift_select_period(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    """Подтверждение покупки подарка."""
    parts = callback.data.split(':')
    tariff_id = int(parts[1])
    period = int(parts[2])

    tariff = await get_tariff_by_id(db, tariff_id)
    if not tariff or not tariff.is_active:
        await callback.answer('Тариф недоступен', show_alert=True)
        return

    prices = tariff.period_prices or {}
    price = prices.get(str(period))
    if price is None:
        await callback.answer('Период недоступен', show_alert=True)
        return
        
    discount_percent = _get_user_period_discount(db_user, period)
    if discount_percent > 0:
        price = _apply_promo_discount(price, discount_percent)

    user_balance = db_user.balance_kopeks or 0
    traffic = 'Безлимит' if tariff.traffic_limit_gb == 0 else f'{tariff.traffic_limit_gb} ГБ'

    text = (
        f"🎁 <b>Подтверждение подарка</b>\n\n"
        f"📦 Тариф: <b>{tariff.name}</b>\n"
        f"📅 Период: <b>{_format_period(period)}</b>\n"
        f"📊 Трафик: {traffic}\n"
        f"📱 Устройств: {tariff.device_limit}\n\n"
        f"💰 <b>Цена: {_format_price_kopeks(price)}</b>\n"
        f"💳 Ваш баланс: {_format_price_kopeks(user_balance)}\n"
    )

    if user_balance >= price:
        text += f"\nПосле оплаты: {_format_price_kopeks(user_balance - price)}\n\n<i>Средства будут списаны с вашего баланса.</i>"
        await callback.message.edit_text(
            text,
            reply_markup=get_gift_confirm_keyboard(tariff_id, period, db_user.language),
            parse_mode='HTML',
        )
    else:
        missing = price - user_balance
        text += f"\n⚠️ <b>Не хватает: {_format_price_kopeks(missing)}</b>"
        await callback.message.edit_text(
            text,
            reply_markup=get_gift_insufficient_balance_keyboard(tariff_id, period, db_user.language),
            parse_mode='HTML',
        )

    await callback.answer()


@error_handler
async def gift_confirm_purchase(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    """Списание средств и генерация ссылки подарка."""
    parts = callback.data.split(':')
    tariff_id = int(parts[1])
    period = int(parts[2])

    tariff = await get_tariff_by_id(db, tariff_id)
    if not tariff or not tariff.is_active:
        await callback.answer('Тариф недоступен', show_alert=True)
        return

    prices = tariff.period_prices or {}
    price = prices.get(str(period))
    if price is None:
        await callback.answer('Период недоступен', show_alert=True)
        return
        
    discount_percent = _get_user_period_discount(db_user, period)
    if discount_percent > 0:
        price = _apply_promo_discount(price, discount_percent)

    user_balance = db_user.balance_kopeks or 0

    if user_balance < price:
        await callback.answer('Недостаточно средств на балансе!', show_alert=True)
        await gift_select_period(callback, db_user, db)
        return

    # 1. Списание баланса
    success = await subtract_user_balance(
        db,
        user=db_user,
        amount_kopeks=price,
        description=f'Подарок: тариф {tariff.name} на {_format_period(period)}',
        create_transaction=True,
    )

    if not success:
        await callback.answer('Ошибка при списании средств.', show_alert=True)
        return
        
    # Установка типа транзакции GIFT_VPN
    try:
        last_txn = await db.execute(
            select(Transaction)
            .where(Transaction.user_id == db_user.id)
            .order_by(Transaction.id.desc())
            .limit(1)
        )
        txn = last_txn.scalar_one_or_none()
        if txn:
            txn.type = TransactionType.GIFT_VPN.value
            await db.commit()
    except Exception as e:
        logger.error(f'Ошибка установки типа транзакции GIFT_VPN: {e}')

    # 2. Генерация токена и сохранение в БД
    token = await GiftService.create_gift(
        db=db,
        tariff_id=tariff_id,
        period_days=period,
        gifter_id=db_user.id
    )

    # 3. Ссылка и кнопка 
    bot_me = await callback.bot.get_me()
    gift_link = f"https://t.me/{bot_me.username}?start=gift_{token}"
    
    share_text = (
        "🎁 Привет! Я приготовил для тебя подарок!\n\n"
        "Премиум-доступ к VPN сервису без ограничений. С любовью! ❤️\n\n"
        f"Тариф: {tariff.name} ({_format_period(period)})\n\n"
        f"⏳ Активируй по ссылке ниже:\n"
        f"{gift_link}"
    )
    encoded_text = urllib.parse.quote(share_text)
    share_url = f"https://t.me/share/url?text={encoded_text}"

    text = (
        f"✅ <b>Подарок успешно оплачен!</b>\n\n"
        f"Ваша подарочная ссылка готова. Отправьте её получателю!\n"
        f"<code>{gift_link}</code>\n\n"
        f"⚠️ <i>Ссылка действительна 30 дней и может быть активирована только одним человеком.</i>"
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='📤 Поделиться ссылкой', url=share_url)],
                [InlineKeyboardButton(text='🏠 На главную', callback_data='back_to_menu')],
            ]
        ),
        parse_mode='HTML'
    )
    await callback.answer()


@error_handler
async def gift_accept(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    """Активация подарка пользователем по кнопке."""
    token = callback.data.split(':')[1]
    user_lang = db_user.language
    
    # Пытаемся активировать подарок
    result = await GiftService.activate_gift(db, db_user, token, callback.bot)
    
    texts = get_texts(user_lang)
    
    if result['success']:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=texts.t('CONNECT_BUTTON', '🔗 Подключиться'), callback_data="subscription_connect")],
                [InlineKeyboardButton(text=texts.t('BACK_TO_MAIN_MENU_BUTTON', '⬅️ В главное меню'), callback_data="back_to_menu")],
            ]
        )
        
        try:
            await callback.message.delete()
        except Exception:
            pass
            
        await callback.message.answer(
            texts.t('GIFT_ACTIVATED_SUCCESS', 
                "🎁 <b>Подарок успешно активирован!</b>\n\n"
                "Вам подарили тариф: <b>{tariff_name}</b> на {period_days} дней!\n\n"
                "Приятного использования!"
            ).format(
                tariff_name=result['tariff_name'],
                period_days=result['period']
            ),
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    else:
        error = result.get('error')
        if error == 'invalid_token':
            await callback.answer(
                texts.t('GIFT_INVALID_TOKEN', "😔 Ссылка на подарок недействительна или уже была использована."),
                show_alert=True
            )
            await callback.message.delete()
        else:
            await callback.answer(
                texts.t('GIFT_ACTIVATION_FAILED', "❌ Ошибка при активации подарка. Попробуйте позже."),
                show_alert=True
            )

    await callback.answer()


@error_handler
async def gift_history_handler(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    """Показывает историю последних 5 подарков пользователя."""
    history = await GiftService.get_user_gift_history(db, db_user.id, limit=5)
    
    bot_me = await callback.bot.get_me()
    
    if not history:
        await callback.message.edit_text(
            "🎁 <b>У вас пока нет подаренных VPN</b>\n\n"
            "Порадуйте друзей доступом к свободному интернету! 😊",
            reply_markup=get_gift_history_keyboard(db_user.language),
            parse_mode='HTML'
        )
        return

    text = "📜 <b>Ваши последние подарки:</b>\n\n"
    
    for i, g in enumerate(history, 1):
        status = "✅ Принят" if g['is_used'] else "⏳ Ожидает"
        recipient = f" ({g['recipient_name']})" if g['recipient_name'] else ""
        link = f"<code>https://t.me/{bot_me.username}?start=gift_{g['token']}</code>"
        
        text += (
            f"{i}. 📦 <b>{g['tariff_name']}</b> ({g['period_days']} дн.)\n"
            f"   Статус: <b>{status}</b>{recipient}\n"
            f"   Ссылка: {link}\n\n"
        )
    
    text += "<i>Нажмите на ссылку, чтобы скопировать её.</i>"

    await callback.message.edit_text(
        text,
        reply_markup=get_gift_history_keyboard(db_user.language),
        parse_mode='HTML'
    )
    await callback.answer()


def register_handlers(dp: Dispatcher):
    """Регистрирует обработчики для подарков VPN."""
    dp.callback_query.register(gift_vpn_start, F.data == 'gifts_start')  # Соответствует callback_data из inline.py
    dp.callback_query.register(gift_select_tariff, F.data.startswith('gift_tariff_select:'))
    dp.callback_query.register(gift_select_period, F.data.startswith('gift_tariff_period:'))
    dp.callback_query.register(gift_confirm_purchase, F.data.startswith('gift_confirm:'))
    dp.callback_query.register(gift_history_handler, F.data == 'gift_history')
    dp.callback_query.register(gift_accept, F.data.startswith('gift_accept:'))
