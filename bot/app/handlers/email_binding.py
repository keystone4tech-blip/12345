
import re
import uuid
from datetime import datetime, timedelta, UTC

import structlog
import bcrypt
from aiogram import Router, F, types, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.database.crud.user import update_user, get_user_by_id
from app.localization.texts import get_texts
from app.cabinet.services.email_service import email_service
from app.keyboards.inline import get_main_menu_keyboard_async
from app.services.main_menu_button_service import MainMenuButtonService
from app.services.support_settings_service import SupportSettingsService
from app.services.user_cart_service import user_cart_service

logger = structlog.get_logger(__name__)

router = Router(name="email_binding")

class EmailBindingState(StatesGroup):
    waiting_for_email = State()
    waiting_for_password = State()

def is_valid_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@router.callback_query(F.data == "bind_email")
async def start_email_binding(callback: types.CallbackQuery, state: FSMContext, db_user: User):
    texts = get_texts(db_user.language)
    
    if db_user.email_verified:
        await callback.answer(texts.t("EMAIL_ALREADY_VERIFIED", "✅ Ваш Email уже привязан!"), show_alert=True)
        return

    await callback.message.edit_text(
        texts.t("BIND_EMAIL_PROMPT", "📧 <b>Привязка Email</b>\n\nВведите ваш адрес электронной почты для регистрации в личном кабинете:"),
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=texts.t("CANCEL", "❌ Отмена"), callback_data="cancel_email_binding")]
        ]),
        parse_mode="HTML"
    )
    await state.set_state(EmailBindingState.waiting_for_email)
    await callback.answer()

@router.callback_query(F.data == "cancel_email_binding")
async def cancel_email_binding(callback: types.CallbackQuery, state: FSMContext, db_user: User, db: AsyncSession):
    await state.clear()
    texts = get_texts(db_user.language)
    
    # Расчет флагов подписки и статуса модератора для корректного отображения меню
    subscription = db_user.subscription
    has_active_subscription = False
    subscription_is_active = False
    
    if subscription:
        actual_status = getattr(subscription, 'actual_status', None)
        has_active_subscription = actual_status in {'active', 'trial'}
        subscription_is_active = bool(getattr(subscription, 'is_active', False))
    
    is_admin = settings.is_admin(db_user.telegram_id)
    is_moderator = (not is_admin) and SupportSettingsService.is_moderator(db_user.telegram_id)
    
    # Проверяем наличие сохраненной корзины
    try:
        has_saved_cart = await user_cart_service.has_user_cart(db_user.id)
    except Exception:
        has_saved_cart = False

    # Получаем кастомные кнопки
    custom_buttons = []
    if not settings.is_text_main_menu_mode():
        custom_buttons = await MainMenuButtonService.get_buttons_for_user(
            db,
            is_admin=is_admin,
            has_active_subscription=has_active_subscription,
            subscription_is_active=subscription_is_active,
        )

    keyboard = await get_main_menu_keyboard_async(
        db=db, 
        user=db_user, 
        language=db_user.language,
        is_admin=is_admin,
        is_moderator=is_moderator,
        has_had_paid_subscription=db_user.has_had_paid_subscription,
        has_active_subscription=has_active_subscription,
        subscription_is_active=subscription_is_active,
        balance_kopeks=db_user.balance_kopeks,
        subscription=db_user.subscription,
        has_saved_cart=has_saved_cart,
        custom_buttons=custom_buttons,
    )
    from app.handlers.menu import get_main_menu_text
    menu_text = await get_main_menu_text(db_user, texts, db)
    
    await callback.message.edit_text(menu_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.message(EmailBindingState.waiting_for_email)
async def process_email(message: types.Message, state: FSMContext, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)
    email = message.text.strip().lower()

    if not is_valid_email(email):
        await message.answer(texts.t("INVALID_EMAIL_FORMAT", "❌ Некорректный формат Email. Попробуйте еще раз:"))
        return

    # Проверка на дубликаты
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.email == email, User.id != db_user.id))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        try:
            from app.services.merge_service import MergeService
            from app.cabinet.services.email_service import email_service
            
            merge_service = MergeService()
            merge_token = await merge_service.create_merge_token(db_user.id, existing_user.id)
            cabinet_url = settings.CABINET_URL or "https://lk.mozhnovpn.tech"
            merge_url = f"{cabinet_url}/merge/{merge_token}"
            
            subject = texts.t("MERGE_EMAIL_SUBJECT", "Слияние аккаунтов")
            body_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .button {{
                        display: inline-block;
                        padding: 12px 24px;
                        background-color: #007bff;
                        color: white !important;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 20px 0;
                    }}
                    .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>Здравствуйте!</h2>
                    <p>Вы (или кто-то другой) запросили объединение вашего аккаунта на сайте с новым аккаунтом в Telegram.</p>
                    <p>Для подтверждения слияния аккаунтов, пожалуйста, нажмите на кнопку ниже:</p>
                    <a href="{merge_url}" class="button">Объединить аккаунты</a>
                    <p>Или скопируйте и вставьте эту ссылку в браузер:</p>
                    <p><a href="{merge_url}">{merge_url}</a></p>
                    <p>Ссылка действительна в течение 15 минут.</p>
                    <p>Если вы не запрашивали объединение аккаунтов, просто проигнорируйте это письмо.</p>
                    <div class="footer">
                        <p>С уважением,<br>{settings.SMTP_FROM_NAME}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            email_service.send_email(to_email=existing_user.email, subject=subject, body_html=body_html)
            
            await message.answer(
                texts.t("EMAIL_ALREADY_EXISTS_MERGE_SENT", "⚠️ <b>Этот Email уже используется.</b>\n\nВ целях безопасности мы отправили письмо на указанную почту.\n\nПожалуйста, перейдите по ссылке в письме, чтобы подтвердить владение Email и объединить аккаунты."),
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text=texts.t("CANCEL", "❌ Отмена / Готово"), callback_data="cancel_email_binding")]
                ]),
                parse_mode="HTML"
            )
            await state.clear()
            return
        except Exception as e:
            logger.error("Error creating merge token", error=e)
            await message.answer(texts.t("SYSTEM_ERROR", "❌ Произошла системная ошибка. Пожалуйста, попробуйте позже."))
            await state.clear()
            return

    await state.update_data(email=email)
    await message.answer(
        texts.t("BIND_PASSWORD_PROMPT", "🔑 <b>Установка пароля</b>\n\nПридумайте пароль для входа на сайт (минимум 8 символов):"),
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=texts.t("CANCEL", "❌ Отмена"), callback_data="cancel_email_binding")]
        ]),
        parse_mode="HTML"
    )
    await state.set_state(EmailBindingState.waiting_for_password)

@router.message(EmailBindingState.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)
    user_id = message.from_user.id
    logger.info("Starting process_password", user_id=user_id)
    password = message.text.strip()
    
    # Инициализируем переменные заранее, чтобы они были доступны в блоке формирования меню
    user_first_name = db_user.first_name
    user_username = db_user.username
    user_language = db_user.language
    user_telegram_id = db_user.telegram_id

    if len(password) < 8:
        logger.warning("Password too short", user_id=user_id)
        await message.answer(texts.t("PASSWORD_TOO_SHORT", "❌ Пароль слишком короткий. Минимум 8 символов:"))
        return

    logger.info("Retrieving state data", user_id=user_id)
    data = await state.get_data()
    email = data.get('email')
    
    if not email:
        logger.error("Email not found in state data", user_id=user_id)
        await message.answer(texts.t("SYSTEM_ERROR", "❌ Произошла системная ошибка. Пожалуйста, попробуйте позже."))
        await state.clear()
        return

    try:
        logger.info("Hashing password", user_id=user_id)
        # Хешируем пароль через нативный bcrypt
        # bcrypt.hashpw ожидает байты, поэтому кодируем пароль
        salt = bcrypt.gensalt()
        password_bytes = password.encode('utf-8')
        password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
        
        # Генерируем токен верификации
        verification_token = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=settings.get_cabinet_email_verification_expire_hours())

        logger.info("Updating user object in session", user_id=user_id, email=email)
        # Обновляем пользователя
        db_user.email = email
        db_user.password_hash = password_hash
        db_user.email_verification_token = verification_token
        db_user.email_verification_expires = expires_at
        db_user.email_verified = False
        
        logger.info("Committing transaction", user_id=user_id)
        await db.commit()
        logger.info("Transaction committed successfully", user_id=user_id)
        
        # Заново получаем пользователя из БД со всеми необходимыми связями, 
        # чтобы избежать MissingGreenlet при отрисовке меню
        logger.info("Refetching user from DB with relations", user_id=user_id)
        from app.database.crud.user import get_user_by_id
        db_user = await get_user_by_id(db, db_user.id)
        logger.info("User refetched successfully", user_id=user_id)

        # Отправляем письмо
        logger.info("Sending verification email", user_id=user_id, email=email)
        cabinet_url = settings.CABINET_URL or "https://lk.mozhnovpn.tech"
        # Путь для верификации на сайте
        verification_url = f"{cabinet_url}/verify-email"
        
        sent = email_service.send_verification_email(
            to_email=email,
            verification_token=verification_token,
            verification_url=verification_url,
            username=user_first_name or user_username,
            language=user_language
        )

        if sent:
            logger.info("Verification email sent successfully", user_id=user_id)
            await message.answer(
                texts.t("EMAIL_VERIFICATION_SENT", "✅ <b>Письмо отправлено!</b>\n\nМы отправили ссылку для подтверждения на <code>{email}</code>. Пожалуйста, проверьте почту (включая папку Спам).").format(email=email),
                parse_mode="HTML"
            )
        else:
            logger.warning("Failed to send verification email", user_id=user_id)
            await message.answer(texts.t("EMAIL_SEND_ERROR", "❌ Ошибка при отправке письма. Пожалуйста, обратитесь в поддержку."))

    except Exception as e:
        logger.error("Error in email binding process", error=e, user_id=user_id)
        await message.answer(texts.t("SYSTEM_ERROR", "❌ Произошла системная ошибка. Пожалуйста, попробуйте позже."))
        logger.info("Rolling back transaction", user_id=user_id)
        await db.rollback()

    logger.info("Clearing state", user_id=user_id)
    await state.clear()
    
    # Возвращаем в главное меню
    # Используем db_user, который мы заново получили из базы после комита
    logger.info("Generating main menu keyboard", user_id=user_id)
    
    # Расчет флагов подписки и статуса модератора для корректного отображения меню
    subscription = db_user.subscription
    has_active_subscription = False
    subscription_is_active = False
    
    if subscription:
        actual_status = getattr(subscription, 'actual_status', None)
        has_active_subscription = actual_status in {'active', 'trial'}
        subscription_is_active = bool(getattr(subscription, 'is_active', False))

    is_admin = settings.is_admin(user_telegram_id)
    is_moderator = (not is_admin) and SupportSettingsService.is_moderator(user_telegram_id)
    
    # Проверяем наличие сохраненной корзины
    try:
        has_saved_cart = await user_cart_service.has_user_cart(db_user.id)
    except Exception:
        has_saved_cart = False

    # Получаем кастомные кнопки
    custom_buttons = []
    if not settings.is_text_main_menu_mode():
        custom_buttons = await MainMenuButtonService.get_buttons_for_user(
            db,
            is_admin=is_admin,
            has_active_subscription=has_active_subscription,
            subscription_is_active=subscription_is_active,
        )

    keyboard = await get_main_menu_keyboard_async(
        db=db, 
        user=db_user, 
        language=user_language,
        is_admin=is_admin,
        is_moderator=is_moderator,
        has_had_paid_subscription=db_user.has_had_paid_subscription,
        has_active_subscription=has_active_subscription,
        subscription_is_active=subscription_is_active,
        balance_kopeks=db_user.balance_kopeks,
        subscription=db_user.subscription,
        has_saved_cart=has_saved_cart,
        custom_buttons=custom_buttons,
    )
    
    logger.info("Generating main menu text", user_id=user_id)
    from app.handlers.menu import get_main_menu_text
    menu_text = await get_main_menu_text(db_user, texts, db)
    
    logger.info("Sending main menu message", user_id=user_id)
    await message.answer(menu_text, reply_markup=keyboard, parse_mode="HTML")
    logger.info("Process password completed", user_id=user_id)

def register_handlers(dp: Dispatcher):
    dp.include_router(router)
