import html
from datetime import datetime

import structlog
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.localization.texts import get_texts
from app.services.faq_service import FaqService
from app.states import AdminStates
from app.utils.decorators import admin_required, error_handler
from app.utils.validators import get_html_help_text, validate_html_tags, strip_html


logger = structlog.get_logger(__name__)


def _format_timestamp(value: datetime | None) -> str:
    if not value:
        return ''
    try:
        return value.strftime('%d.%m.%Y %H:%M')
    except Exception:
        return ''


async def _build_overview(
    db_user: User,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)

    normalized_language = FaqService.normalize_language(db_user.language)
    setting = await FaqService.get_setting(
        db,
        db_user.language,
        fallback=False,
    )

    pages = await FaqService.get_pages(
        db,
        db_user.language,
        include_inactive=True,
        fallback=False,
    )

    total_pages = len(pages)
    active_pages = sum(1 for page in pages if page.is_active)

    description = texts.t(
        'ADMIN_FAQ_DESCRIPTION',
        'FAQ отображается в разделе «Инфо».',
    )

    if setting and not setting.is_enabled:
        status_text = texts.t(
            'ADMIN_FAQ_STATUS_DISABLED',
            '⚠️ Показ FAQ выключен.',
        )
    elif active_pages:
        status_text = texts.t(
            'ADMIN_FAQ_STATUS_ENABLED',
            '✅ FAQ включён. Активных страниц: {count}.',
        ).format(count=active_pages)
    elif total_pages:
        status_text = texts.t(
            'ADMIN_FAQ_STATUS_ENABLED_EMPTY',
            '⚠️ FAQ включён, но нет активных страниц.',
        )
    else:
        status_text = texts.t(
            'ADMIN_FAQ_STATUS_EMPTY',
            '⚠️ FAQ ещё не настроен.',
        )

    pages_overview = texts.t(
        'ADMIN_FAQ_PAGES_EMPTY',
        'Страницы ещё не созданы.',
    )

    if pages:
        rows: list[str] = []
        for index, page in enumerate(pages, start=1):
            title = (page.title or '').strip()
            if not title:
                title = texts.t('FAQ_PAGE_UNTITLED', 'Без названия')
            if len(title) > 60:
                title = f'{title[:57]}...'

            status_label = texts.t(
                'ADMIN_FAQ_PAGE_STATUS_ACTIVE',
                '✅ Активна',
            )
            if not page.is_active:
                status_label = texts.t(
                    'ADMIN_FAQ_PAGE_STATUS_INACTIVE',
                    '🚫 Выключена',
                )

            updated = _format_timestamp(getattr(page, 'updated_at', None))
            updated_block = f' ({updated})' if updated else ''
            rows.append(f'{index}. {strip_html(title)} — {status_label}{updated_block}')

        pages_list_header = texts.t(
            'ADMIN_FAQ_PAGES_OVERVIEW',
            '<b>Список страниц:</b>\n{items}',
        )
        pages_overview = pages_list_header.format(items='\n'.join(rows))

    language_block = texts.t(
        'ADMIN_FAQ_LANGUAGE',
        'Язык: <code>{lang}</code>',
    ).format(lang=normalized_language)

    stats_block = texts.t(
        'ADMIN_FAQ_PAGE_STATS',
        'Всего страниц: {total}',
    ).format(total=total_pages)

    header = texts.t('ADMIN_FAQ_HEADER', '❓ <b>FAQ</b>')
    actions_prompt = texts.t(
        'ADMIN_FAQ_ACTION_PROMPT',
        'Выберите действие:',
    )

    message_parts = [
        header,
        description,
        language_block,
        status_text,
        stats_block,
        pages_overview,
        actions_prompt,
    ]

    overview_text = '\n\n'.join(part for part in message_parts if part)

    buttons: list[list[types.InlineKeyboardButton]] = []

    buttons.append(
        [
            types.InlineKeyboardButton(
                text=texts.t(
                    'ADMIN_FAQ_ADD_PAGE_BUTTON',
                    '➕ Добавить страницу',
                ),
                callback_data='admin_faq_create',
            )
        ]
    )

    for page in pages[:25]:
        title = (page.title or '').strip()
        if not title:
            title = texts.t('FAQ_PAGE_UNTITLED', 'Без названия')
        if len(title) > 40:
            title = f'{title[:37]}...'
        buttons.append(
            [
                types.InlineKeyboardButton(
                    text=f'{page.display_order}. {strip_html(title)}',
                    callback_data=f'admin_faq_page:{page.id}',
                )
            ]
        )

    toggle_text = texts.t(
        'ADMIN_FAQ_ENABLE_BUTTON',
        '✅ Включить показ',
    )
    if setting and setting.is_enabled:
        toggle_text = texts.t(
            'ADMIN_FAQ_DISABLE_BUTTON',
            '🚫 Отключить показ',
        )

    buttons.append(
        [
            types.InlineKeyboardButton(
                text=toggle_text,
                callback_data='admin_faq_toggle',
            )
        ]
    )

    buttons.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_FAQ_HTML_HELP', 'ℹ️ HTML помощь'),
                callback_data='admin_faq_help',
            )
        ]
    )

    buttons.append(
        [
            types.InlineKeyboardButton(
                text=texts.BACK,
                callback_data='admin_submenu_settings',
            )
        ]
    )

    return overview_text, types.InlineKeyboardMarkup(inline_keyboard=buttons)


@admin_required
@error_handler
async def show_faq_management(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    overview_text, markup = await _build_overview(db_user, db)

    await callback.message.edit_text(
        overview_text,
        reply_markup=markup,
    )
    await callback.answer()


@admin_required
@error_handler
async def toggle_faq(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)
    setting = await FaqService.toggle_enabled(db, db_user.language)

    if setting.is_enabled:
        alert_text = texts.t(
            'ADMIN_FAQ_ENABLED_ALERT',
            '✅ FAQ включён.',
        )
    else:
        alert_text = texts.t(
            'ADMIN_FAQ_DISABLED_ALERT',
            '🚫 FAQ отключён.',
        )

    overview_text, markup = await _build_overview(db_user, db)

    await callback.message.edit_text(
        overview_text,
        reply_markup=markup,
    )
    await callback.answer(alert_text, show_alert=True)


@admin_required
@error_handler
async def start_create_faq_page(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)

    await state.set_state(AdminStates.creating_faq_title)
    await state.update_data(faq_language=db_user.language)

    await callback.message.edit_text(
        texts.t(
            'ADMIN_FAQ_ENTER_TITLE',
            'Введите заголовок для новой страницы FAQ:',
        ),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=texts.t(
                            'ADMIN_FAQ_CANCEL_BUTTON',
                            '⬅️ Отмена',
                        ),
                        callback_data='admin_faq_cancel',
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def cancel_faq_creation(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    await state.clear()
    await show_faq_management(callback, db_user, db)


@admin_required
@error_handler
async def process_new_faq_title(
    message: types.Message,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)
    title = (message.html_text or '').strip()

    if not title:
        await message.answer(
            texts.t(
                'ADMIN_FAQ_TITLE_EMPTY',
                '❌ Заголовок не может быть пустым.',
            )
        )
        return

    if len(title) > 255:
        await message.answer(
            texts.t(
                'ADMIN_FAQ_TITLE_TOO_LONG',
                '❌ Заголовок слишком длинный. Максимум 255 символов.',
            )
        )
        return

    is_valid, error_message = validate_html_tags(title)
    if not is_valid:
        await message.answer(
            texts.t(
                'ADMIN_FAQ_HTML_ERROR',
                '❌ Ошибка в HTML: {error}',
            ).format(error=error_message)
        )
        return

    await state.update_data(faq_title=title)
    await state.set_state(AdminStates.creating_faq_content)

    await message.answer(
        texts.t(
            'ADMIN_FAQ_ENTER_CONTENT',
            'Отправьте содержимое страницы FAQ. Допускается HTML.',
        )
    )


@admin_required
@error_handler
async def process_new_faq_content(
    message: types.Message,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)
    content = message.html_text or ''

    if len(content) > 6000:
        await message.answer(
            texts.t(
                'ADMIN_FAQ_CONTENT_TOO_LONG',
                '❌ Текст слишком длинный. Максимум 6000 символов.',
            )
        )
        return

    if not content.strip():
        await message.answer(
            texts.t(
                'ADMIN_FAQ_CONTENT_EMPTY',
                '❌ Текст не может быть пустым.',
            )
        )
        return

    is_valid, error_message = validate_html_tags(content)
    if not is_valid:
        await message.answer(
            texts.t(
                'ADMIN_FAQ_HTML_ERROR',
                '❌ Ошибка в HTML: {error}',
            ).format(error=error_message)
        )
        return

    data = await state.get_data()
    title = data.get('faq_title') or texts.t('FAQ_PAGE_UNTITLED', 'Без названия')
    language = data.get('faq_language', db_user.language)

    await FaqService.create_page(
        db,
        language=language,
        title=title,
        content=content,
    )

    logger.info('Админ создал страницу FAQ (символов)', telegram_id=db_user.telegram_id, content_count=len(content))

    await state.clear()

    success_text = texts.t(
        'ADMIN_FAQ_PAGE_CREATED',
        '✅ Страница FAQ создана.',
    )

    reply_markup = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text=texts.t(
                        'ADMIN_FAQ_BACK_TO_LIST',
                        '⬅️ К настройкам FAQ',
                    ),
                    callback_data='admin_faq',
                )
            ]
        ]
    )

    await message.answer(success_text, reply_markup=reply_markup)


@admin_required
@error_handler
async def show_faq_page_details(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)

    raw_id = (callback.data or '').split(':', 1)[-1]
    try:
        page_id = int(raw_id)
    except ValueError:
        await callback.answer()
        return

    page = await FaqService.get_page(
        db,
        page_id,
        db_user.language,
        fallback=False,
        include_inactive=True,
    )

    if not page:
        await callback.answer(
            texts.t(
                'ADMIN_FAQ_PAGE_NOT_FOUND',
                '⚠️ Страница не найдена.',
            ),
            show_alert=True,
        )
        return

    header = texts.t('ADMIN_FAQ_PAGE_HEADER', '📄 <b>Страница FAQ</b>')
    title = (page.title or '').strip() or texts.t('FAQ_PAGE_UNTITLED', 'Без названия')
    status_label = texts.t(
        'ADMIN_FAQ_PAGE_STATUS_ACTIVE',
        '✅ Активна',
    )
    if not page.is_active:
        status_label = texts.t(
            'ADMIN_FAQ_PAGE_STATUS_INACTIVE',
            '🚫 Выключена',
        )

    updated_at = _format_timestamp(getattr(page, 'updated_at', None))
    updated_block = ''
    if updated_at:
        updated_block = texts.t(
            'ADMIN_FAQ_PAGE_UPDATED',
            'Обновлено: {timestamp}',
        ).format(timestamp=updated_at)

    preview = (page.content or '').strip()
    preview_text = texts.t(
        'ADMIN_FAQ_PAGE_PREVIEW_EMPTY',
        'Текст ещё не задан.',
    )
    if preview:
        from app.utils.text import strip_html
        if len(preview) > 1000:
            preview_trimmed = strip_html(preview)[:1000] + '...'
        else:
            preview_trimmed = preview
            
        preview_text = texts.t('ADMIN_FAQ_PAGE_PREVIEW', '<b>Превью:</b>\n{content}').format(
            content=preview_trimmed
        )

    message_parts = [
        header,
        texts.t(
            'ADMIN_FAQ_PAGE_TITLE',
            '<b>Заголовок:</b> {title}',
        ).format(title=title),
        texts.t(
            'ADMIN_FAQ_PAGE_STATUS',
            'Статус: {status}',
        ).format(status=status_label),
        preview_text,
        updated_block,
    ]

    message_text = '\n\n'.join(part for part in message_parts if part)

    buttons: list[list[types.InlineKeyboardButton]] = []

    buttons.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_FAQ_EDIT_TITLE_BUTTON', '✏️ Изменить заголовок'),
                callback_data=f'admin_faq_edit_title:{page.id}',
            )
        ]
    )
    buttons.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_FAQ_EDIT_CONTENT_BUTTON', '📝 Изменить текст'),
                callback_data=f'admin_faq_edit_content:{page.id}',
            )
        ]
    )

    buttons.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_FAQ_EDIT_MEDIA_BUTTON', '🖼️ Изменить медиа'),
                callback_data=f'admin_faq_edit_media:{page.id}',
            )
        ]
    )
    buttons.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_FAQ_EDIT_BUTTONS_BUTTON', '🔘 Настроить кнопки'),
                callback_data=f'admin_faq_edit_buttons:{page.id}',
            )
        ]
    )

    toggle_text = texts.t('ADMIN_FAQ_PAGE_ENABLE_BUTTON', '✅ Включить страницу')
    if page.is_active:
        toggle_text = texts.t(
            'ADMIN_FAQ_PAGE_DISABLE_BUTTON',
            '🚫 Выключить страницу',
        )

    buttons.append(
        [
            types.InlineKeyboardButton(
                text=toggle_text,
                callback_data=f'admin_faq_toggle_page:{page.id}',
            )
        ]
    )

    buttons.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_FAQ_PAGE_MOVE_UP', '⬆️ Выше'),
                callback_data=f'admin_faq_move:{page.id}:up',
            ),
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_FAQ_PAGE_MOVE_DOWN', '⬇️ Ниже'),
                callback_data=f'admin_faq_move:{page.id}:down',
            ),
        ]
    )

    buttons.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_FAQ_PAGE_DELETE_BUTTON', '🗑️ Удалить'),
                callback_data=f'admin_faq_delete:{page.id}',
            )
        ]
    )

    buttons.append(
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_FAQ_BACK_TO_LIST', '⬅️ К настройкам FAQ'),
                callback_data='admin_faq',
            )
        ]
    )

    try:
        await callback.message.edit_text(
            message_text,
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode='HTML'
        )
    except Exception:
        pass
    await callback.answer()


@admin_required
@error_handler
async def start_edit_faq_title(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)

    raw_id = (callback.data or '').split(':', 1)[-1]
    try:
        page_id = int(raw_id)
    except ValueError:
        await callback.answer()
        return

    page = await FaqService.get_page(
        db,
        page_id,
        db_user.language,
        fallback=False,
        include_inactive=True,
    )

    if not page:
        await callback.answer(
            texts.t(
                'ADMIN_FAQ_PAGE_NOT_FOUND',
                '⚠️ Страница не найдена.',
            ),
            show_alert=True,
        )
        return

    await state.set_state(AdminStates.editing_faq_title)
    await state.update_data(faq_page_id=page.id)

    await callback.message.edit_text(
        texts.t(
            'ADMIN_FAQ_EDIT_TITLE_PROMPT',
            'Введите новый заголовок для страницы:',
        ),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=texts.t(
                            'ADMIN_FAQ_CANCEL_BUTTON',
                            '⬅️ Отмена',
                        ),
                        callback_data=f'admin_faq_page:{page.id}',
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def process_edit_faq_title(
    message: types.Message,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)
    title = (message.html_text or '').strip()

    if not title:
        await message.answer(
            texts.t(
                'ADMIN_FAQ_TITLE_EMPTY',
                '❌ Заголовок не может быть пустым.',
            )
        )
        return

    if len(title) > 255:
        await message.answer(
            texts.t(
                'ADMIN_FAQ_TITLE_TOO_LONG',
                '❌ Заголовок слишком длинный. Максимум 255 символов.',
            )
        )
        return

    is_valid, error_message = validate_html_tags(title)
    if not is_valid:
        await message.answer(
            texts.t(
                'ADMIN_FAQ_HTML_ERROR',
                '❌ Ошибка в HTML: {error}',
            ).format(error=error_message)
        )
        return

    data = await state.get_data()
    page_id = data.get('faq_page_id')

    if not page_id:
        await state.clear()
        await message.answer(texts.t('ADMIN_FAQ_UNEXPECTED_STATE', '⚠️ Состояние сброшено.'))
        return

    page = await FaqService.get_page(
        db,
        page_id,
        db_user.language,
        fallback=False,
        include_inactive=True,
    )

    if not page:
        await message.answer(
            texts.t('ADMIN_FAQ_PAGE_NOT_FOUND', '⚠️ Страница не найдена.'),
        )
        await state.clear()
        return

    await FaqService.update_page(db, page, title=title)
    await state.clear()

    await message.answer(
        texts.t('ADMIN_FAQ_TITLE_UPDATED', '✅ Заголовок обновлён.'),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=texts.t('ADMIN_FAQ_BACK_TO_LIST', '⬅️ К настройкам FAQ'),
                        callback_data='admin_faq',
                    )
                ]
            ]
        ),
    )


@admin_required
@error_handler
async def start_edit_faq_content(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)

    raw_id = (callback.data or '').split(':', 1)[-1]
    try:
        page_id = int(raw_id)
    except ValueError:
        await callback.answer()
        return

    page = await FaqService.get_page(
        db,
        page_id,
        db_user.language,
        fallback=False,
        include_inactive=True,
    )

    if not page:
        await callback.answer(
            texts.t('ADMIN_FAQ_PAGE_NOT_FOUND', '⚠️ Страница не найдена.'),
            show_alert=True,
        )
        return

    await state.set_state(AdminStates.editing_faq_content)
    await state.update_data(faq_page_id=page.id)

    await callback.message.edit_text(
        texts.t(
            'ADMIN_FAQ_EDIT_CONTENT_PROMPT',
            'Отправьте новый текст для страницы FAQ.',
        ),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=texts.t(
                            'ADMIN_FAQ_CANCEL_BUTTON',
                            '⬅️ Отмена',
                        ),
                        callback_data=f'admin_faq_page:{page.id}',
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@admin_required
@error_handler
async def process_edit_faq_content(
    message: types.Message,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)
    content = message.html_text or ''

    if len(content) > 6000:
        await message.answer(
            texts.t(
                'ADMIN_FAQ_CONTENT_TOO_LONG',
                '❌ Текст слишком длинный. Максимум 6000 символов.',
            )
        )
        return

    if not content.strip():
        await message.answer(
            texts.t(
                'ADMIN_FAQ_CONTENT_EMPTY',
                '❌ Текст не может быть пустым.',
            )
        )
        return

    is_valid, error_message = validate_html_tags(content)
    if not is_valid:
        await message.answer(
            texts.t(
                'ADMIN_FAQ_HTML_ERROR',
                '❌ Ошибка в HTML: {error}',
            ).format(error=error_message)
        )
        return

    data = await state.get_data()
    page_id = data.get('faq_page_id')

    if not page_id:
        await state.clear()
        await message.answer(texts.t('ADMIN_FAQ_UNEXPECTED_STATE', '⚠️ Состояние сброшено.'))
        return

    page = await FaqService.get_page(
        db,
        page_id,
        db_user.language,
        fallback=False,
        include_inactive=True,
    )

    if not page:
        await message.answer(
            texts.t('ADMIN_FAQ_PAGE_NOT_FOUND', '⚠️ Страница не найдена.'),
        )
        await state.clear()
        return

    await FaqService.update_page(db, page, content=content)
    await state.clear()

    await message.answer(
        texts.t('ADMIN_FAQ_CONTENT_UPDATED', '✅ Текст страницы обновлён.'),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=texts.t('ADMIN_FAQ_BACK_TO_LIST', '⬅️ К настройкам FAQ'),
                        callback_data='admin_faq',
                    )
                ]
            ]
        ),
    )


@admin_required
@error_handler
async def toggle_faq_page(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)

    parts = (callback.data or '').split(':')
    try:
        page_id = int(parts[1])
    except (ValueError, IndexError):
        await callback.answer()
        return

    page = await FaqService.get_page(
        db,
        page_id,
        db_user.language,
        fallback=False,
        include_inactive=True,
    )

    if not page:
        await callback.answer(
            texts.t('ADMIN_FAQ_PAGE_NOT_FOUND', '⚠️ Страница не найдена.'),
            show_alert=True,
        )
        return

    updated_page = await FaqService.update_page(db, page, is_active=not page.is_active)

    alert_text = texts.t(
        'ADMIN_FAQ_PAGE_ENABLED_ALERT',
        '✅ Страница включена.',
    )
    if not updated_page.is_active:
        alert_text = texts.t(
            'ADMIN_FAQ_PAGE_DISABLED_ALERT',
            '🚫 Страница выключена.',
        )

    await callback.answer(alert_text, show_alert=True)
    await show_faq_page_details(callback, db_user, db)


@admin_required
@error_handler
async def delete_faq_page(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)

    parts = (callback.data or '').split(':')
    try:
        page_id = int(parts[1])
    except (ValueError, IndexError):
        await callback.answer()
        return

    page = await FaqService.get_page(
        db,
        page_id,
        db_user.language,
        fallback=False,
        include_inactive=True,
    )

    if not page:
        await callback.answer(
            texts.t('ADMIN_FAQ_PAGE_NOT_FOUND', '⚠️ Страница не найдена.'),
            show_alert=True,
        )
        return

    await FaqService.delete_page(db, page.id)

    remaining_pages = await FaqService.get_pages(
        db,
        db_user.language,
        include_inactive=True,
        fallback=False,
    )

    if remaining_pages:
        remaining_sorted = sorted(
            remaining_pages,
            key=lambda item: (item.display_order, item.id),
        )
        await FaqService.reorder_pages(db, db_user.language, remaining_sorted)

    await callback.answer(
        texts.t('ADMIN_FAQ_PAGE_DELETED', '🗑️ Страница удалена.'),
        show_alert=True,
    )

    await show_faq_management(callback, db_user, db)


@admin_required
@error_handler
async def move_faq_page(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)

    parts = (callback.data or '').split(':')
    try:
        page_id = int(parts[1])
        direction = parts[2]
    except (ValueError, IndexError):
        await callback.answer()
        return

    pages = await FaqService.get_pages(
        db,
        db_user.language,
        include_inactive=True,
        fallback=False,
    )

    if not pages:
        await callback.answer()
        return

    pages_sorted = sorted(pages, key=lambda item: (item.display_order, item.id))

    index = next((i for i, page in enumerate(pages_sorted) if page.id == page_id), None)

    if index is None:
        await callback.answer()
        return

    if direction == 'up' and index > 0:
        pages_sorted[index - 1], pages_sorted[index] = (
            pages_sorted[index],
            pages_sorted[index - 1],
        )
    elif direction == 'down' and index < len(pages_sorted) - 1:
        pages_sorted[index + 1], pages_sorted[index] = (
            pages_sorted[index],
            pages_sorted[index + 1],
        )
    else:
        await callback.answer()
        return

    await FaqService.reorder_pages(db, db_user.language, pages_sorted)

    await callback.answer(
        texts.t('ADMIN_FAQ_PAGE_REORDERED', '✅ Порядок обновлён.'),
        show_alert=True,
    )
    await show_faq_page_details(callback, db_user, db)


@admin_required
@error_handler
async def show_faq_html_help(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)
    help_text = get_html_help_text()

    buttons = [
        [
            types.InlineKeyboardButton(
                text=texts.t('ADMIN_FAQ_BACK_TO_LIST', '⬅️ К настройкам FAQ'),
                callback_data='admin_faq',
            )
        ]
    ]

    await callback.message.edit_text(
        help_text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()



@admin_required
@error_handler
async def start_edit_faq_media(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)
    raw_id = (callback.data or '').split(':', 1)[-1]
    
    await state.update_data(editing_faq_id=int(raw_id))
    await state.set_state(AdminStates.waiting_for_faq_media)

    await callback.message.edit_text(
        '🖼️ <b>Изменение медиафайла</b>\n\n'
        'Отправьте фото, видео или документ для этой страницы FAQ.\n'
        'Или нажмите "Удалить медиа", чтобы страница была только текстовой.',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text='🗑️ Удалить медиа',
                        callback_data='admin_faq_delete_media',
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text=texts.t('ADMIN_FAQ_CANCEL_BUTTON', '⬅️ Отмена'),
                        callback_data=f'admin_faq_page:{raw_id}',
                    )
                ]
            ]
        ),
        parse_mode='HTML'
    )
    await callback.answer()

@admin_required
@error_handler
async def delete_faq_media(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    data = await state.get_data()
    page_id = data.get('editing_faq_id')
    if not page_id:
        await callback.answer('Ошибка.', show_alert=True)
        return
        
    page = await FaqService.get_page(db, page_id, db_user.language, fallback=False, include_inactive=True)
    if page:
        await FaqService.update_page(db, page, media_type=None, media_file_id=None, media_group_data=None)
    await state.clear()
    
    callback.data = f'admin_faq_page:{page_id}'
    await show_faq_page_details(callback, db_user, db)

@admin_required
@error_handler
async def process_faq_media(
    message: types.Message,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    data = await state.get_data()
    page_id = data.get('editing_faq_id')
    
    if message.media_group_id:
        media_group_data = data.get('faq_media_group_data', [])
        current_group_id = data.get('faq_media_group_id')
        
        if current_group_id != message.media_group_id:
            media_group_data = []
            await state.update_data(faq_media_group_id=message.media_group_id)
            
        media_item = {}
        if message.photo:
            media_item = {'type': 'photo', 'media': message.photo[-1].file_id}
        elif message.video:
            media_item = {'type': 'video', 'media': message.video.file_id}
        elif message.audio:
            media_item = {'type': 'audio', 'media': message.audio.file_id}
        elif message.document:
            media_item = {'type': 'document', 'media': message.document.file_id}
            
        if media_item:
            if message.caption:
                media_item['caption'] = message.caption
            media_group_data.append(media_item)
            await state.update_data(faq_media_group_data=media_group_data)
            
        page = await FaqService.get_page(db, page_id, db_user.language, fallback=False, include_inactive=True)
        if page:
            await FaqService.update_page(db, page, media_group_data=media_group_data, media_file_id=None, media_type=None)
        
        if not data.get(f'faq_album_{message.media_group_id}'):
            await state.update_data({f'faq_album_{message.media_group_id}': True})
            await message.answer(
                '✅ <b>Медиагруппа добавлена!</b>',
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[[
                        types.InlineKeyboardButton(text='⬅️ К странице', callback_data=f'admin_faq_page:{page_id}')
                    ]]
                ),
                parse_mode='HTML'
            )
        return
        
    media_file_id = None
    media_type = None
    
    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = 'photo'
    elif message.video:
        media_file_id = message.video.file_id
        media_type = 'video'
    elif message.document:
        media_file_id = message.document.file_id
        media_type = 'document'
    elif message.voice:
        media_file_id = message.voice.file_id
        media_type = 'voice'
    elif message.video_note:
        media_file_id = message.video_note.file_id
        media_type = 'video_note'
    elif message.audio:
        media_file_id = message.audio.file_id
        media_type = 'audio'
    else:
        await message.answer('❌ Пожалуйста, отправьте фото, видео, документ, голос, аудио, кружок или альбом.')
        return
        
    page = await FaqService.get_page(db, page_id, db_user.language, fallback=False, include_inactive=True)
    if page:
        await FaqService.update_page(db, page, media_type=media_type, media_file_id=media_file_id, media_group_data=None)
    await state.clear()
    
    await message.answer(
        '✅ <b>Медиа обновлено!</b>',
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[
                types.InlineKeyboardButton(text='⬅️ К странице', callback_data=f'admin_faq_page:{page_id}')
            ]]
        ),
        parse_mode='HTML'
    )

@admin_required
@error_handler
async def start_edit_faq_buttons(
    callback: types.CallbackQuery,
    db_user: User,
    state: FSMContext,
    db: AsyncSession,
):
    texts = get_texts(db_user.language)
    raw_id = (callback.data or '').split(':', 1)[-1]
    
    page = await FaqService.get_page(db, int(raw_id), db_user.language, fallback=False, include_inactive=True)
    if not page:
        await callback.answer('Страница не найдена')
        return
        
    buttons = page.inline_buttons or []
    
    await state.update_data(editing_faq_id=int(raw_id), current_faq_buttons=buttons)
    
    await show_faq_buttons_editor(callback, db_user, state, db)
    await callback.answer()

async def show_faq_buttons_editor(callback: types.CallbackQuery, db_user: User, state: FSMContext, db: AsyncSession):
    data = await state.get_data()
    page_id = data.get('editing_faq_id')
    buttons = data.get('current_faq_buttons', [])
    
    text = '🔘 <b>Настройка кнопок</b>\n\nТекущие кнопки:\n'
    for i, btn in enumerate(buttons, 1):
        text += f"{i}. {btn.get('text')} - {btn.get('url')}\n"
        
    if not buttons:
        text += "Нет кнопок."
        
    keyboard = []
    if len(buttons) < 5:
        keyboard.append([types.InlineKeyboardButton(text='➕ Добавить кнопку', callback_data='admin_faq_add_btn')])
    if buttons:
        keyboard.append([types.InlineKeyboardButton(text='🗑️ Очистить кнопки', callback_data='admin_faq_clear_btns')])
        
    keyboard.append([types.InlineKeyboardButton(text='💾 Сохранить', callback_data='admin_faq_save_btns')])
    keyboard.append([types.InlineKeyboardButton(text='⬅️ Назад', callback_data=f'admin_faq_page:{page_id}')])
    
    try:
        await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='HTML')
    except Exception:
        await callback.message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='HTML')

@admin_required
@error_handler
async def add_faq_button(callback: types.CallbackQuery, db_user: User, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_faq_button_text)
    
    try:
        await callback.message.edit_text(
            'Введите текст для новой кнопки:',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='❌ Отмена', callback_data='admin_faq_cancel_btn')]]
            )
        )
    except Exception:
        await callback.message.answer(
            'Введите текст для новой кнопки:',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text='❌ Отмена', callback_data='admin_faq_cancel_btn')]]
            )
        )
    await callback.answer()

@admin_required
@error_handler
async def process_faq_btn_text(message: types.Message, db_user: User, state: FSMContext):
    await state.update_data(temp_btn_text=message.text)
    await state.set_state(AdminStates.waiting_for_faq_button_url)
    await message.answer('Введите ссылку для кнопки (начинается с http/https/tg):')

@admin_required
@error_handler
async def process_faq_btn_url(message: types.Message, db_user: User, state: FSMContext, db: AsyncSession):
    url = message.text.strip()
    if not url.startswith(('http://', 'https://', 'tg://')):
        await message.answer('Неверный формат ссылки. Попробуйте снова:')
        return
        
    await state.update_data(temp_btn_url=url)
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text='🔵 Синяя', callback_data='admin_faq_style_primary'),
                types.InlineKeyboardButton(text='🟢 Зеленая', callback_data='admin_faq_style_success'),
            ],
            [
                types.InlineKeyboardButton(text='🔴 Красная', callback_data='admin_faq_style_danger'),
                types.InlineKeyboardButton(text='⚪ Обычная', callback_data='admin_faq_style_default'),
            ],
            [types.InlineKeyboardButton(text='❌ Отмена', callback_data='admin_faq_cancel_btn')],
        ]
    )
    
    await message.answer(
        '🎨 <b>Выберите стиль (цвет) для кнопки:</b>\n\n'
        '<i>Стили — это новая функция Telegram. Если клиент пользователя не поддерживает их, кнопка будет обычной.</i>',
        parse_mode='HTML',
        reply_markup=keyboard,
    )
    await state.set_state(AdminStates.waiting_for_faq_button_style)

@admin_required
@error_handler
async def process_faq_btn_style(callback: types.CallbackQuery, db_user: User, state: FSMContext):
    style = callback.data.replace('admin_faq_style_', '')
    await state.update_data(temp_btn_style=style)
    
    from app.keyboards.admin import get_broadcast_button_emoji_keyboard
    
    try:
        await callback.message.edit_text(
            '✨ <b>Отправьте премиум эмодзи для кнопки:</b>\n\n'
            '<i>Или просто любой эмодзи. Он будет добавлен в начало текста кнопки.</i>\n'
            '<i>Нажмите "Пропустить", если эмодзи не нужен.</i>',
            parse_mode='HTML',
            reply_markup=get_broadcast_button_emoji_keyboard(db_user.language)
        )
    except Exception:
        await callback.message.answer(
            '✨ <b>Отправьте премиум эмодзи для кнопки:</b>\n\n'
            '<i>Или просто любой эмодзи. Он будет добавлен в начало текста кнопки.</i>\n'
            '<i>Нажмите "Пропустить", если эмодзи не нужен.</i>',
            parse_mode='HTML',
            reply_markup=get_broadcast_button_emoji_keyboard(db_user.language)
        )
    await state.set_state(AdminStates.waiting_for_faq_button_emoji)
    await callback.answer()

@admin_required
@error_handler
async def process_faq_btn_emoji(message: types.Message, db_user: User, state: FSMContext, db: AsyncSession):
    emoji_text = message.text.strip()
    from app.utils.message_patch import get_custom_emoji_id
    custom_emoji_id = get_custom_emoji_id(message)
    
    data = await state.get_data()
    text = data.get('temp_btn_text')
    url = data.get('temp_btn_url')
    style = data.get('temp_btn_style')
    
    if custom_emoji_id:
        final_text = text 
    else:
        final_text = f"{emoji_text} {text}"
        
    buttons = data.get('current_faq_buttons', [])
    btn_data = {'text': final_text, 'url': url}
    if style and style != 'default':
        btn_data['style'] = style
    if custom_emoji_id:
        btn_data['emoji_id'] = str(custom_emoji_id)
        
    buttons.append(btn_data)
    
    await state.update_data(current_faq_buttons=buttons)
    await message.answer('✅ Кнопка добавлена.')
    
    mock_callback = types.CallbackQuery(id='0', from_user=message.from_user, chat_instance='', data='', message=message)
    await show_faq_buttons_editor(mock_callback, db_user, state, db)

@admin_required
@error_handler
async def process_faq_btn_emoji_skip(callback: types.CallbackQuery, db_user: User, state: FSMContext, db: AsyncSession):
    data = await state.get_data()
    text = data.get('temp_btn_text')
    url = data.get('temp_btn_url')
    style = data.get('temp_btn_style')
    
    buttons = data.get('current_faq_buttons', [])
    btn_data = {'text': text, 'url': url}
    if style and style != 'default':
        btn_data['style'] = style
        
    buttons.append(btn_data)
    
    await state.update_data(current_faq_buttons=buttons)
    await show_faq_buttons_editor(callback, db_user, state, db)
    await callback.answer('Кнопка добавлена.')

@admin_required
@error_handler
async def clear_faq_buttons(callback: types.CallbackQuery, db_user: User, state: FSMContext, db: AsyncSession):
    await state.update_data(current_faq_buttons=[])
    await show_faq_buttons_editor(callback, db_user, state, db)
    await callback.answer('Кнопки очищены')

@admin_required
@error_handler
async def save_faq_buttons(callback: types.CallbackQuery, db_user: User, state: FSMContext, db: AsyncSession):
    data = await state.get_data()
    page_id = data.get('editing_faq_id')
    buttons = data.get('current_faq_buttons', [])
    
    page = await FaqService.get_page(db, page_id, db_user.language, fallback=False, include_inactive=True)
    if page:
        await FaqService.update_page(db, page, inline_buttons=buttons)
    await state.clear()
    
    callback.data = f'admin_faq_page:{page_id}'
    await show_faq_page_details(callback, db_user, db)

@admin_required
@error_handler
async def cancel_faq_btn(callback: types.CallbackQuery, db_user: User, state: FSMContext, db: AsyncSession):
    await show_faq_buttons_editor(callback, db_user, state, db)
    await callback.answer()



def register_handlers(dp: Dispatcher) -> None:
    dp.callback_query.register(start_edit_faq_media, F.data.startswith('admin_faq_edit_media:'))
    dp.callback_query.register(delete_faq_media, F.data == 'admin_faq_delete_media')
    dp.message.register(process_faq_media, AdminStates.waiting_for_faq_media)
    
    dp.callback_query.register(start_edit_faq_buttons, F.data.startswith('admin_faq_edit_buttons:'))
    dp.callback_query.register(add_faq_button, F.data == 'admin_faq_add_btn')
    dp.message.register(process_faq_btn_text, AdminStates.waiting_for_faq_button_text)
    dp.message.register(process_faq_btn_url, AdminStates.waiting_for_faq_button_url)
    dp.callback_query.register(process_faq_btn_style, F.data.startswith('admin_faq_style_'))
    dp.message.register(process_faq_btn_emoji, AdminStates.waiting_for_faq_button_emoji)
    dp.callback_query.register(process_faq_btn_emoji_skip, F.data == 'admin_broadcast_skip_emoji', AdminStates.waiting_for_faq_button_emoji)
    
    dp.callback_query.register(clear_faq_buttons, F.data == 'admin_faq_clear_btns')
    dp.callback_query.register(save_faq_buttons, F.data == 'admin_faq_save_btns')
    dp.callback_query.register(cancel_faq_btn, F.data == 'admin_faq_cancel_btn')

    dp.callback_query.register(
        show_faq_management,
        F.data == 'admin_faq',
    )
    dp.callback_query.register(
        toggle_faq,
        F.data == 'admin_faq_toggle',
    )
    dp.callback_query.register(
        start_create_faq_page,
        F.data == 'admin_faq_create',
    )
    dp.callback_query.register(
        cancel_faq_creation,
        F.data == 'admin_faq_cancel',
    )
    dp.callback_query.register(
        show_faq_page_details,
        F.data.startswith('admin_faq_page:'),
    )
    dp.callback_query.register(
        start_edit_faq_title,
        F.data.startswith('admin_faq_edit_title:'),
    )
    dp.callback_query.register(
        start_edit_faq_content,
        F.data.startswith('admin_faq_edit_content:'),
    )
    dp.callback_query.register(
        toggle_faq_page,
        F.data.startswith('admin_faq_toggle_page:'),
    )
    dp.callback_query.register(
        delete_faq_page,
        F.data.startswith('admin_faq_delete:'),
    )
    dp.callback_query.register(
        move_faq_page,
        F.data.startswith('admin_faq_move:'),
    )
    dp.callback_query.register(
        show_faq_html_help,
        F.data == 'admin_faq_help',
    )

    dp.message.register(
        process_new_faq_title,
        AdminStates.creating_faq_title,
    )
    dp.message.register(
        process_new_faq_content,
        AdminStates.creating_faq_content,
    )
    dp.message.register(
        process_edit_faq_title,
        AdminStates.editing_faq_title,
    )
    dp.message.register(
        process_edit_faq_content,
        AdminStates.editing_faq_content,
    )
