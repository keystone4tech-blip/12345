from aiogram import types
from aiogram.types import InaccessibleMessage, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.keyboards.inline import (
    get_device_selection_keyboard,
    get_dynamic_connect_button,
    get_happ_cryptolink_keyboard,
    get_happ_download_button_row,
)
from app.localization.texts import get_texts
from app.utils.subscription_utils import (
    convert_subscription_link_to_happ_scheme,
    get_display_subscription_link,
    get_happ_cryptolink_redirect_link,
)

from .common import get_platforms_list, load_app_config_async, logger


async def handle_connect_subscription(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    # Проверяем, доступно ли сообщение для редактирования
    if isinstance(callback.message, InaccessibleMessage):
        await callback.answer()
        return

    texts = get_texts(db_user.language)
    subscription = db_user.subscription
    subscription_link = get_display_subscription_link(subscription)
    hide_subscription_link = settings.should_hide_subscription_link()

    if not subscription_link:
        await callback.answer(
            texts.t(
                'SUBSCRIPTION_NO_ACTIVE_LINK',
                '⚠ У вас нет активной подписки или ссылка еще генерируется',
            ),
            show_alert=True,
        )
        return

    if connect_mode != 'guide':
        keyboard_rows = [[get_dynamic_connect_button(texts, subscription_link)]]
        
        if connect_mode in ['link', 'happ_cryptolink']:
            happ_row = get_happ_download_button_row(texts)
            if happ_row:
                keyboard_rows.append(happ_row)
        
        keyboard_rows.append([InlineKeyboardButton(text=texts.BACK, callback_data='menu_subscription')])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        if connect_mode == 'miniapp_subscription':
            message_text = texts.t(
                'SUBSCRIPTION_CONNECT_MINIAPP_MESSAGE',
                """📱 <b>Подключить подписку</b>\n\n🚀 Нажмите кнопку ниже, чтобы открыть подписку в мини-приложении Telegram:""",
            )
        elif connect_mode == 'miniapp_custom':
            message_text = texts.t(
                'SUBSCRIPTION_CONNECT_CUSTOM_MESSAGE',
                """🚀 <b>Подключить подписку</b>\n\n📱 Нажмите кнопку ниже, чтобы открыть приложение:""",
            )
        else: # link or happ_cryptolink
            message_text = texts.t(
                'SUBSCRIPTION_CONNECT_LINK_MESSAGE',
                """🚀 <b>Подключить подписку</b>\n\n🔗 Нажмите кнопку ниже, чтобы открыть ссылку подписки:""",
            )

        await callback.message.edit_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='HTML',
        )
    else:
        # Guide mode: load config and build dynamic platform keyboard
        platforms = None
        try:
            config = await load_app_config_async()
            if config:
                platforms = get_platforms_list(config) or None
        except Exception as e:
            logger.warning('Failed to load platforms for guide mode', error=e)

        if not platforms:
            await callback.message.edit_text(
                texts.t(
                    'GUIDE_CONFIG_NOT_SET',
                    '⚠️ <b>Конфигурация не настроена</b>\n\n'
                    'Администратор ещё не настроил конфигурацию приложений.\n'
                    'Обратитесь к администратору.',
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=texts.BACK, callback_data='menu_subscription')],
                    ]
                ),
                parse_mode='HTML',
            )
            await callback.answer()
            return

        if hide_subscription_link:
            device_text = texts.t(
                'SUBSCRIPTION_CONNECT_DEVICE_MESSAGE_HIDDEN',
                """📱 <b>Подключить подписку</b>

ℹ️ Ссылка подписки доступна по кнопкам ниже или в разделе "Моя подписка".

💡 <b>Выберите ваше устройство</b> для получения подробной инструкции по настройке:""",
            )
        else:
            device_text = texts.t(
                'SUBSCRIPTION_CONNECT_DEVICE_MESSAGE',
                """📱 <b>Подключить подписку</b>

🔗 <b>Ссылка подписки:</b>
<code>{subscription_url}</code>

💡 <b>Выберите ваше устройство</b> для получения подробной инструкции по настройке:""",
            ).format(subscription_url=subscription_link)

        await callback.message.edit_text(
            device_text,
            reply_markup=get_device_selection_keyboard(db_user.language, platforms=platforms),
            parse_mode='HTML',
        )

    await callback.answer()


async def handle_open_subscription_link(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    texts = get_texts(db_user.language)
    subscription = db_user.subscription
    subscription_link = get_display_subscription_link(subscription)

    if not subscription_link:
        await callback.answer(
            texts.t('SUBSCRIPTION_LINK_UNAVAILABLE', '❌ Ссылка подписки недоступна'),
            show_alert=True,
        )
        return

    if settings.is_happ_cryptolink_mode():
        redirect_link = get_happ_cryptolink_redirect_link(subscription_link)
        happ_scheme_link = convert_subscription_link_to_happ_scheme(subscription_link)
        happ_message = (
            texts.t(
                'SUBSCRIPTION_HAPP_OPEN_TITLE',
                '🔗 <b>Подключение через Happ</b>',
            )
            + '\n\n'
            + texts.t(
                'SUBSCRIPTION_HAPP_OPEN_LINK',
                '<a href="{subscription_link}">🔓 Открыть ссылку в Happ</a>',
            ).format(subscription_link=happ_scheme_link)
            + '\n\n'
            + texts.t(
                'SUBSCRIPTION_HAPP_OPEN_HINT',
                '💡 Если ссылка не открывается автоматически, скопируйте её вручную:',
            )
        )

        if redirect_link:
            happ_message += '\n\n' + texts.t(
                'SUBSCRIPTION_HAPP_OPEN_BUTTON_HINT',
                '▶️ Нажмите кнопку "Подключиться" ниже, чтобы открыть Happ и добавить подписку автоматически.',
            )

        happ_message += '\n\n' + texts.t(
            'SUBSCRIPTION_HAPP_CRYPTOLINK_BLOCK',
            '<blockquote expandable><code>{crypto_link}</code></blockquote>',
        ).format(crypto_link=subscription_link)

        keyboard = get_happ_cryptolink_keyboard(
            subscription_link,
            db_user.language,
            redirect_link=redirect_link,
        )

        await callback.message.answer(
            happ_message,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
        await callback.answer()
        return

    link_text = (
        texts.t('SUBSCRIPTION_DEVICE_LINK_TITLE', '🔗 <b>Ссылка подписки:</b>')
        + '\n\n'
        + f'<code>{subscription_link}</code>\n\n'
        + texts.t('SUBSCRIPTION_LINK_USAGE_TITLE', '📱 <b>Как использовать:</b>')
        + '\n'
        + '\n'.join(
            [
                texts.t(
                    'SUBSCRIPTION_LINK_STEP1',
                    '1. Нажмите на ссылку выше чтобы её скопировать',
                ),
                texts.t(
                    'SUBSCRIPTION_LINK_STEP2',
                    '2. Откройте ваше VPN приложение',
                ),
                texts.t(
                    'SUBSCRIPTION_LINK_STEP3',
                    '3. Найдите функцию "Добавить подписку" или "Import"',
                ),
                texts.t(
                    'SUBSCRIPTION_LINK_STEP4',
                    '4. Вставьте скопированную ссылку',
                ),
            ]
        )
        + '\n\n'
        + texts.t(
            'SUBSCRIPTION_LINK_HINT',
            '💡 Если ссылка не скопировалась, выделите её вручную и скопируйте.',
        )
    )

    await callback.message.edit_text(
        link_text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [get_dynamic_connect_button(texts, subscription_link)],
                [InlineKeyboardButton(text=texts.BACK, callback_data='menu_subscription')],
            ]
        ),
        parse_mode='HTML',
    )
    await callback.answer()
