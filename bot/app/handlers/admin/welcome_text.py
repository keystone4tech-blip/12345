import re

import structlog
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.welcome_text import (
    get_available_placeholders,
    get_current_welcome_text_or_default,
    get_current_welcome_text_settings,
    set_welcome_text,
    toggle_welcome_text_status,
)
from app.database.models import User
from app.keyboards.admin import get_welcome_text_keyboard
from app.states import AdminStates
from app.utils.decorators import admin_required, error_handler
from app.utils.validators import get_html_help_text, validate_html_tags


logger = structlog.get_logger(__name__)





@admin_required
@error_handler
async def show_welcome_text_panel(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    welcome_settings = await get_current_welcome_text_settings(db)
    status_emoji = '🟢' if welcome_settings['is_enabled'] else '🔴'
    status_text = 'включено' if welcome_settings['is_enabled'] else 'отключено'

    await callback.message.edit_text(
        f'👋 Управление приветственным текстом\n\n'
        f'{status_emoji} <b>Статус:</b> {status_text}\n\n'
        f'Здесь вы можете управлять текстом, который показывается новым пользователям после регистрации.\n\n'
        f'💡 Доступные плейсхолдеры для автозамены:',
        reply_markup=get_welcome_text_keyboard(db_user.language, welcome_settings['is_enabled']),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def toggle_welcome_text(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    new_status = await toggle_welcome_text_status(db, db_user.id)

    status_emoji = '🟢' if new_status else '🔴'
    status_text = 'включено' if new_status else 'отключено'
    action_text = 'включены' if new_status else 'отключены'

    await callback.message.edit_text(
        f'👋 Управление приветственным текстом\n\n'
        f'{status_emoji} <b>Статус:</b> {status_text}\n\n'
        f'✅ Приветственные сообщения {action_text}!\n\n'
        f'Здесь вы можете управлять текстом, который показывается новым пользователям после регистрации.\n\n'
        f'💡 Доступные плейсхолдеры для автозамены:',
        reply_markup=get_welcome_text_keyboard(db_user.language, new_status),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def show_current_welcome_text(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    welcome_settings = await get_current_welcome_text_settings(db)
    current_text = welcome_settings['text']
    is_enabled = welcome_settings['is_enabled']

    if not welcome_settings['id']:
        status = '📝 Используется стандартный текст:'
    else:
        status = '📝 Текущий приветственный текст:'

    status_emoji = '🟢' if is_enabled else '🔴'
    status_text = 'включено' if is_enabled else 'отключено'

    placeholders = get_available_placeholders()
    placeholders_text = '\n'.join([f'• <code>{key}</code> - {desc}' for key, desc in placeholders.items()])

    await callback.message.edit_text(
        f'{status_emoji} <b>Статус:</b> {status_text}\n\n'
        f'{status}\n\n'
        f'<code>{current_text}</code>\n\n'
        f'💡 Доступные плейсхолдеры:\n{placeholders_text}',
        reply_markup=get_welcome_text_keyboard(db_user.language, is_enabled),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def show_placeholders_help(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    welcome_settings = await get_current_welcome_text_settings(db)
    placeholders = get_available_placeholders()
    placeholders_text = '\n'.join([f'• <code>{key}</code>\n  {desc}' for key, desc in placeholders.items()])

    help_text = (
        '💡 Доступные плейсхолдеры для автозамены:\n\n'
        f'{placeholders_text}\n\n'
        '📌 Примеры использования:\n'
        '• <code>Привет, {user_name}! Добро пожаловать!</code>\n'
        '• <code>Здравствуйте, {first_name}! Рады видеть вас!</code>\n'
        '• <code>Привет, {username}! Спасибо за регистрацию!</code>\n\n'
        "При отсутствии данных пользователя используется слово 'друг'."
    )

    await callback.message.edit_text(
        help_text,
        reply_markup=get_welcome_text_keyboard(db_user.language, welcome_settings['is_enabled']),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def show_formatting_help(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    welcome_settings = await get_current_welcome_text_settings(db)
    formatting_info = get_html_help_text()

    await callback.message.edit_text(
        formatting_info,
        reply_markup=get_welcome_text_keyboard(db_user.language, welcome_settings['is_enabled']),
        parse_mode='HTML',
    )
    await callback.answer()


@admin_required
@error_handler
async def start_edit_welcome_text(callback: types.CallbackQuery, state: FSMContext, db_user: User, db: AsyncSession):
    welcome_settings = await get_current_welcome_text_settings(db)
    current_text = welcome_settings['text']

    placeholders = get_available_placeholders()
    placeholders_text = '\n'.join([f'• <code>{key}</code> - {desc}' for key, desc in placeholders.items()])

    await callback.message.edit_text(
        f'📝 Редактирование приветственного текста\n\n'
        f'Текущий текст:\n'
        f'<code>{current_text}</code>\n\n'
        f'💡 Доступные плейсхолдеры:\n{placeholders_text}\n\n'
        f'Отправьте новый текст:',
        parse_mode='HTML',
    )

    await state.set_state(AdminStates.editing_welcome_text)
    await callback.answer()


@admin_required
@error_handler
async def process_welcome_text_edit(message: types.Message, state: FSMContext, db_user: User, db: AsyncSession):
    new_text = (message.html_text or "").strip()

    if len(new_text) < 10:
        await message.answer('❌ Текст слишком короткий! Минимум 10 символов.')
        return

    if len(new_text) > 4000:
        await message.answer('❌ Текст слишком длинный! Максимум 4000 символов.')
        return

    # Проверяем HTML-теги на валидность
    is_valid, error_msg = validate_html_tags(new_text)
    if not is_valid:
        await message.answer(f'❌ Ошибка в HTML-разметке:\n\n{error_msg}')
        return

    success = await set_welcome_text(db, new_text, db_user.id)

    if success:
        welcome_settings = await get_current_welcome_text_settings(db)
        status_emoji = '🟢' if welcome_settings['is_enabled'] else '🔴'
        status_text = 'включено' if welcome_settings['is_enabled'] else 'отключено'

        placeholders = get_available_placeholders()
        placeholders_text = '\n'.join([f'• <code>{key}</code>' for key in placeholders.keys()])

        await message.answer(
            f'✅ Приветственный текст успешно обновлен!\n\n'
            f'{status_emoji} <b>Статус:</b> {status_text}\n\n'
            f'Новый текст:\n'
            f'<code>{new_text}</code>\n\n'
            f'💡 Будут заменяться плейсхолдеры: {placeholders_text}',
            reply_markup=get_welcome_text_keyboard(db_user.language, welcome_settings['is_enabled']),
            parse_mode='HTML',
        )
    else:
        welcome_settings = await get_current_welcome_text_settings(db)
        await message.answer(
            '❌ Ошибка при сохранении текста. Попробуйте еще раз.',
            reply_markup=get_welcome_text_keyboard(db_user.language, welcome_settings['is_enabled']),
        )

    await state.clear()


@admin_required
@error_handler
async def reset_welcome_text(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    default_text = await get_current_welcome_text_or_default()
    success = await set_welcome_text(db, default_text, db_user.id)

    if success:
        welcome_settings = await get_current_welcome_text_settings(db)
        status_emoji = '🟢' if welcome_settings['is_enabled'] else '🔴'
        status_text = 'включено' if welcome_settings['is_enabled'] else 'отключено'

        await callback.message.edit_text(
            f'✅ Приветственный текст сброшен на стандартный!\n\n'
            f'{status_emoji} <b>Статус:</b> {status_text}\n\n'
            f'Стандартный текст:\n'
            f'<code>{default_text}</code>\n\n'
            f'💡 Плейсхолдер <code>{{user_name}}</code> будет заменяться на имя пользователя',
            reply_markup=get_welcome_text_keyboard(db_user.language, welcome_settings['is_enabled']),
            parse_mode='HTML',
        )
    else:
        welcome_settings = await get_current_welcome_text_settings(db)
        await callback.message.edit_text(
            '❌ Ошибка при сбросе текста. Попробуйте еще раз.',
            reply_markup=get_welcome_text_keyboard(db_user.language, welcome_settings['is_enabled']),
        )

    await callback.answer()


@admin_required
@error_handler
async def show_preview_welcome_text(callback: types.CallbackQuery, db_user: User, db: AsyncSession):
    from app.database.crud.welcome_text import get_welcome_text_for_user

    class TestUser:
        def __init__(self):
            self.first_name = 'Иван'
            self.username = 'test_user'

    test_user = TestUser()
    preview_text = await get_welcome_text_for_user(db, test_user)

    welcome_settings = await get_current_welcome_text_settings(db)

    if preview_text:
        await callback.message.edit_text(
            f'👁️ Предварительный просмотр\n\n'
            f"Как будет выглядеть текст для пользователя 'Иван' (@test_user):\n\n"
            f'<code>{preview_text}</code>',
            reply_markup=get_welcome_text_keyboard(db_user.language, welcome_settings['is_enabled']),
            parse_mode='HTML',
        )
    else:
        await callback.message.edit_text(
            '👁️ Предварительный просмотр\n\n'
            '🔴 Приветственные сообщения отключены.\n'
            'Новые пользователи не будут получать приветственный текст после регистрации.',
            reply_markup=get_welcome_text_keyboard(db_user.language, welcome_settings['is_enabled']),
            parse_mode='HTML',
        )

    await callback.answer()


def register_welcome_text_handlers(dp: Dispatcher):
    dp.callback_query.register(show_welcome_text_panel, F.data == 'welcome_text_panel')

    dp.callback_query.register(toggle_welcome_text, F.data == 'toggle_welcome_text')

    dp.callback_query.register(show_current_welcome_text, F.data == 'show_welcome_text')

    dp.callback_query.register(show_placeholders_help, F.data == 'show_placeholders_help')

    dp.callback_query.register(show_formatting_help, F.data == 'show_formatting_help')

    dp.callback_query.register(show_preview_welcome_text, F.data == 'preview_welcome_text')

    dp.callback_query.register(start_edit_welcome_text, F.data == 'edit_welcome_text')

    dp.callback_query.register(reset_welcome_text, F.data == 'reset_welcome_text')

    dp.message.register(process_welcome_text_edit, AdminStates.editing_welcome_text)
