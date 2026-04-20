from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

from app.config import settings
from app.localization.texts import get_texts


def get_main_reply_keyboard(language: str = 'ru', is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Создает основное Reply-меню пользователя.
    """
    texts = get_texts(language)

    # Первый ряд: Статус и Подключиться
    keyboard = [
        [
            KeyboardButton(text=texts.t('MENU_STATUS', '📊 Статус')),
            KeyboardButton(text=texts.t('MENU_CONNECT_W_EMOJI', '⚡ Подключиться')),
        ]
    ]

    # Второй ряд: Оплатить и Помощь
    keyboard.append(
        [
            KeyboardButton(text=texts.t('MENU_PAY', '💥 Оплатить')),
            KeyboardButton(text=texts.t('MENU_HELP_RED', '❓ Помощь')),
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
