from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

from app.config import settings
from app.localization.texts import get_texts


def get_main_reply_keyboard(language: str = 'ru', is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Создает основное Reply-меню пользователя.
    """
    texts = get_texts(language)

    def _make_btn(text_key, default_text, settings_text_attr, settings_style_attr, settings_emoji_attr):
        """Хелпер для создания кнопки с учетом новых полей Bot API 9.4+"""
        text = getattr(settings, settings_text_attr) or texts.t(text_key, default_text)
        style = getattr(settings, settings_style_attr) or 'default'
        emoji_id = getattr(settings, settings_emoji_attr)

        kwargs = {'text': text}
        # style и icon_custom_emoji_id доступны в aiogram 3.22+ (Bot API 9.4+)
        if style and style != 'default':
            kwargs['style'] = style
        if emoji_id:
            kwargs['icon_custom_emoji_id'] = str(emoji_id)

        return KeyboardButton(**kwargs)

    # Первый ряд: Статус и Подключиться
    keyboard = [
        [
            _make_btn('MENU_STATUS', '📊 Статус', 'MENU_STATUS_TEXT', 'MENU_STATUS_STYLE', 'MENU_STATUS_EMOJI'),
            _make_btn('MENU_CONNECT_W_EMOJI', '⚡ Подключиться', 'MENU_CONNECT_TEXT', 'MENU_CONNECT_STYLE', 'MENU_CONNECT_EMOJI'),
        ]
    ]

    # Второй ряд: Оплатить и Помощь
    keyboard.append(
        [
            _make_btn('MENU_PAY', '💥 Оплатить', 'MENU_PAY_TEXT', 'MENU_PAY_STYLE', 'MENU_PAY_EMOJI'),
            _make_btn('MENU_HELP_RED', '❓ Помощь', 'MENU_HELP_TEXT', 'MENU_HELP_STYLE', 'MENU_HELP_EMOJI'),
        ]
    )

    # Третий ряд: Админ-панель (только для админов)
    if is_admin:
        admin_button_text = texts.t('ADMIN_PANEL_BUTTON', '🏠 Админ панель')
        keyboard.append([KeyboardButton(text=admin_button_text)])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=False)


def get_admin_reply_keyboard(language: str = 'ru') -> ReplyKeyboardMarkup:
    """
    Возвращает Reply-клавиатуру для админ-панели.
    """
    texts = get_texts(language)

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.ADMIN_USERS), KeyboardButton(text=texts.ADMIN_SUBSCRIPTIONS)],
            [KeyboardButton(text=texts.ADMIN_PROMOCODES), KeyboardButton(text=texts.ADMIN_MESSAGES)],
            [KeyboardButton(text=texts.ADMIN_STATISTICS), KeyboardButton(text=texts.ADMIN_MONITORING)],
            [KeyboardButton(text=texts.t('ADMIN_MAIN_MENU', '🏠 Главное меню'))],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_cancel_keyboard(language: str = 'ru') -> ReplyKeyboardMarkup:
    texts = get_texts(language)

    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.CANCEL)]], resize_keyboard=True, one_time_keyboard=True
    )


def get_confirmation_reply_keyboard(language: str = 'ru') -> ReplyKeyboardMarkup:
    texts = get_texts(language)

    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.YES), KeyboardButton(text=texts.NO)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_skip_keyboard(language: str = 'ru') -> ReplyKeyboardMarkup:
    texts = get_texts(language)
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.REFERRAL_CODE_SKIP)]], resize_keyboard=True, one_time_keyboard=True
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def get_contact_keyboard(language: str = 'ru') -> ReplyKeyboardMarkup:
    texts = get_texts(language)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.t('SEND_CONTACT_BUTTON', '📱 Отправить контакт'), request_contact=True)],
            [KeyboardButton(text=texts.CANCEL)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_location_keyboard(language: str = 'ru') -> ReplyKeyboardMarkup:
    texts = get_texts(language)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.t('SEND_LOCATION_BUTTON', '📍 Отправить геолокацию'), request_location=True)],
            [KeyboardButton(text=texts.CANCEL)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
