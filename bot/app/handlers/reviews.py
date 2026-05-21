"""
Обработчики пользовательского интерфейса для системы отзывов.

Поток взаимодействия:
1. Пользователь получает запрос → нажимает на звёзды (1-5)
2. Создаётся запись в БД, начисляются дни за оценку
3. Предлагается оставить развёрнутый отзыв (текст/голос/видео)
4. Пользователь отправляет контент → начисляются дополнительные дни
5. Подписка продлевается, отправляется благодарственное сообщение
"""

import structlog
from aiogram import Router, F, types, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import User
from app.services.reviews_service import reviews_service
from app.utils.decorators import error_handler

# Логгер модуля
logger = structlog.get_logger(__name__)

# Роутер для регистрации хендлеров
router = Router(name='reviews')


# ──────────────────────────── FSM состояния ────────────────────────────

class ReviewStates(StatesGroup):
    """Состояния конечного автомата для сбора отзывов."""
    waiting_for_content = State()  # Ожидаем текст/голос/видео-кружок


# ──────────────────────────── Обработчики callback ────────────────────────────

@router.callback_query(F.data.startswith('review_rate:'))
async def handle_review_rating(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
    state: FSMContext,
):
    """
    Обработка нажатия на кнопку оценки (1-5 звёзд).
    
    Создаёт запись в БД и предлагает оставить развёрнутый отзыв.
    """
    # Извлекаем оценку из callback_data
    rating = int(callback.data.split(':')[1])

    # Валидация рейтинга
    if rating < 1 or rating > 5:
        await callback.answer('❌ Некорректная оценка', show_alert=True)
        return

    # Проверяем, нет ли уже незавершённого отзыва
    pending = await reviews_service.get_pending_review(db, db_user.id)
    if pending:
        # Обновляем рейтинг существующего незавершённого отзыва
        pending.rating = rating
        pending.star_reward_days = reviews_service.get_star_reward(rating)
        await db.commit()
        review = pending
        logger.info(
            '⭐ Обновлён рейтинг незавершённого отзыва',
            review_id=review.id,
            rating=rating,
        )
    else:
        # Создаём новый отзыв
        review = await reviews_service.create_review(db, db_user.id, rating)

    # Сохраняем review_id в состоянии FSM
    await state.set_state(ReviewStates.waiting_for_content)
    await state.update_data(review_id=review.id)

    # Формируем звёзды для отображения
    stars = '⭐' * rating

    # Информация о наградах
    star_days = review.star_reward_days
    text_days = settings.REVIEWS_REWARD_CONTENT_TEXT
    voice_days = settings.REVIEWS_REWARD_CONTENT_VOICE
    video_days = settings.REVIEWS_REWARD_CONTENT_VIDEO

    if rating <= 3:
        text_lines = [
            f'✅ <b>Спасибо за вашу оценку {stars}!</b>\n'
        ]
        if star_days > 0:
            text_lines.append(f'За оценку вам начислено <b>+{star_days} дн.</b> подписки.\n')
            
        text_lines.extend([
            '─────────────────────\n',
            '😔 <b>Что мы можем сделать лучше?</b>\n\n',
            'Пожалуйста, расскажите, что вам не понравилось или чего не хватает в нашем сервисе. Ваша обратная связь поможет нам стать лучше!\n\n'
        ])
        
        has_content_rewards = any(d > 0 for d in [text_days, voice_days, video_days])
        if has_content_rewards:
            text_lines.append('В качестве благодарности за ваш развёрнутый ответ мы начислим дополнительные дни:\n')
            if text_days > 0:
                text_lines.append(f'📝 Текст → <b>+{text_days} дн.</b>')
            if voice_days > 0:
                text_lines.append(f'🎙 Голосовое → <b>+{voice_days} дн.</b>')
            if video_days > 0:
                text_lines.append(f'🎥 Видео-кружок → <b>+{video_days} дн.</b>')
            text_lines.append('')
            
        text_lines.append('<i>Просто отправьте текст, голосовое сообщение или видео-кружок прямо сейчас!</i>')
        text = '\n'.join(text_lines)
    else:
        text_lines = [
            f'✅ <b>Спасибо за оценку {stars}!</b>\n'
        ]
        if star_days > 0:
            text_lines.append(f'За вашу оценку вы получите <b>+{star_days} дн.</b> подписки.\n')
            
        text_lines.extend([
            '─────────────────────\n',
            '📝 <b>Хотите получить ещё больше дней?</b>\n\n',
            'Оставьте развёрнутый отзыв о нашем сервисе и получите дополнительные бонусные дни:\n\n'
        ])
        
        if text_days > 0:
            text_lines.append(f'📝 Текстовый отзыв → <b>+{text_days} дн.</b>')
        if voice_days > 0:
            text_lines.append(f'🎙 Голосовое сообщение → <b>+{voice_days} дн.</b>')
        if video_days > 0:
            text_lines.append(f'🎥 Видео-кружок → <b>+{video_days} дн.</b>')
            
        text_lines.extend([
            '\n<i>Просто отправьте текст, голосовое или видео-кружок прямо сейчас!</i>'
        ])
        text = '\n'.join(text_lines)

    # Кнопка «Пропустить» — завершить без контента
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='⏩ Пропустить', callback_data='review_skip_content')],
        ]
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode='HTML',
        )
    except Exception:
        # Если не удалось отредактировать (сообщение слишком старое),
        # отправляем новое
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode='HTML',
        )

    await callback.answer()


@router.callback_query(F.data == 'review_skip_content')
async def handle_skip_content(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession,
    state: FSMContext,
):
    """
    Пользователь решил не оставлять развёрнутый отзыв.
    
    Завершает отзыв только с рейтингом и начисляет дни за звёзды.
    """
    # Получаем данные из FSM
    data = await state.get_data()
    review_id = data.get('review_id')

    if not review_id:
        # Пробуем найти незавершённый отзыв
        review = await reviews_service.get_pending_review(db, db_user.id)
        if not review:
            await callback.answer('❌ Отзыв не найден', show_alert=True)
            await state.clear()
            return
    else:
        # Получаем отзыв по ID
        from sqlalchemy import select
        from app.database.models import UserReview

        result = await db.execute(select(UserReview).where(UserReview.id == review_id))
        review = result.scalar_one_or_none()
        if not review:
            await callback.answer('❌ Отзыв не найден', show_alert=True)
            await state.clear()
            return

    # Завершаем отзыв без контента
    total_days = await reviews_service.complete_review(db, review, review_type='none')

    # Начисляем бонусные дни
    if total_days > 0:
        await reviews_service.award_bonus_days(db, db_user.id, total_days, callback.bot)

    # Очищаем состояние FSM
    await state.clear()

    # Отправляем благодарственное сообщение
    text = (
        '🎉 <b>Спасибо за вашу оценку!</b>\n\n'
    )
    if total_days > 0:
        text += f'🎁 Вам начислено <b>+{total_days} дн.</b> к подписке!\n\n'
    text += '💙 Ваше мнение очень важно для нас!'

    try:
        await callback.message.edit_text(text, parse_mode='HTML')
    except Exception:
        await callback.message.answer(text, parse_mode='HTML')

    await callback.answer()


@router.callback_query(F.data == 'review_dismiss')
async def handle_dismiss(
    callback: types.CallbackQuery,
    state: FSMContext,
):
    """Пользователь отказался оставлять отзыв (нажал «Не сейчас»)."""
    await state.clear()

    try:
        await callback.message.edit_text(
            '👋 Хорошо! Мы спросим вас позже.\n\n'
            '💙 Спасибо, что пользуетесь нашим сервисом!',
            parse_mode='HTML',
        )
    except Exception:
        pass

    await callback.answer()


# ──────────────────────────── Обработчики контента ────────────────────────────

@router.message(ReviewStates.waiting_for_content, F.text)
async def handle_text_review(
    message: types.Message,
    db_user: User,
    db: AsyncSession,
    state: FSMContext,
):
    """Обработка текстового отзыва от пользователя."""
    # Проверяем минимальную длину текста
    text_content = message.text.strip()
    if len(text_content) < 5:
        await message.answer(
            '✏️ Пожалуйста, напишите хотя бы несколько слов (минимум 5 символов).',
            parse_mode='HTML',
        )
        return

    # Завершаем отзыв
    await _finalize_review(
        db=db,
        db_user=db_user,
        state=state,
        message=message,
        review_type='text',
        content_id=None,
    )


@router.message(ReviewStates.waiting_for_content, F.voice)
async def handle_voice_review(
    message: types.Message,
    db_user: User,
    db: AsyncSession,
    state: FSMContext,
):
    """Обработка голосового отзыва от пользователя."""
    # Получаем file_id голосового сообщения
    voice_file_id = message.voice.file_id

    await _finalize_review(
        db=db,
        db_user=db_user,
        state=state,
        message=message,
        review_type='voice',
        content_id=voice_file_id,
    )


@router.message(ReviewStates.waiting_for_content, F.video_note)
async def handle_video_note_review(
    message: types.Message,
    db_user: User,
    db: AsyncSession,
    state: FSMContext,
):
    """Обработка видео-кружка от пользователя."""
    # Получаем file_id видео-кружка
    video_file_id = message.video_note.file_id

    await _finalize_review(
        db=db,
        db_user=db_user,
        state=state,
        message=message,
        review_type='video_note',
        content_id=video_file_id,
    )


@router.message(ReviewStates.waiting_for_content)
async def handle_unsupported_content(
    message: types.Message,
):
    """Обработка неподдерживаемого типа контента."""
    await message.answer(
        '❌ <b>Неподдерживаемый формат</b>\n\n'
        'Пожалуйста, отправьте:\n'
        '📝 Текстовое сообщение\n'
        '🎙 Голосовое сообщение\n'
        '🎥 Видео-кружок\n\n'
        'Или нажмите <b>⏩ Пропустить</b>, чтобы завершить без отзыва.',
        parse_mode='HTML',
    )


# ──────────────────────────── Вспомогательные функции ────────────────────────────

async def _finalize_review(
    db: AsyncSession,
    db_user: User,
    state: FSMContext,
    message: types.Message,
    review_type: str,
    content_id: str | None,
) -> None:
    """
    Общая логика завершения отзыва с контентом.

    Args:
        db: Сессия базы данных
        db_user: Объект пользователя
        state: Контекст FSM
        message: Сообщение пользователя
        review_type: Тип контента ('text', 'voice', 'video_note')
        content_id: Telegram file_id (None для текста)
    """
    # Получаем ID отзыва из FSM
    data = await state.get_data()
    review_id = data.get('review_id')

    # Ищем отзыв
    if review_id:
        from sqlalchemy import select
        from app.database.models import UserReview

        result = await db.execute(select(UserReview).where(UserReview.id == review_id))
        review = result.scalar_one_or_none()
    else:
        review = await reviews_service.get_pending_review(db, db_user.id)

    if not review:
        await message.answer(
            '❌ Отзыв не найден. Возможно, время истекло.\n'
            'Попробуйте оставить отзыв позже.',
            parse_mode='HTML',
        )
        await state.clear()
        return

    # Завершаем отзыв
    total_days = await reviews_service.complete_review(
        db=db,
        review=review,
        review_type=review_type,
        content_id=content_id,
    )

    # Начисляем бонусные дни
    if total_days > 0:
        await reviews_service.award_bonus_days(db, db_user.id, total_days, message.bot)

    # Очищаем FSM
    await state.clear()

    # Определяем название типа контента для сообщения
    type_names = {
        'text': '📝 текстовый отзыв',
        'voice': '🎙 голосовое сообщение',
        'video_note': '🎥 видео-кружок',
    }
    type_name = type_names.get(review_type, 'отзыв')

    # Формируем благодарственное сообщение с разбивкой наград
    star_days = review.star_reward_days
    content_days = review.content_reward_days

    text_lines = [
        f'🎉 <b>Спасибо за ваш {type_name}!</b>\n\n',
        '─────────────────────'
    ]
    if star_days > 0:
        text_lines.append(f'⭐ За оценку: <b>+{star_days} дн.</b>')
    if content_days > 0:
        text_lines.append(f'📝 За отзыв: <b>+{content_days} дн.</b>')
    
    if star_days > 0 or content_days > 0:
        text_lines.append('─────────────────────\n')
        
    if total_days > 0:
        text_lines.append(f'🎁 <b>Итого: +{total_days} дн.</b> к подписке!\n')
    
    text_lines.extend([
        '💙 Ваше мнение очень ценно для нас!',
        'Благодаря вашим отзывам мы становимся лучше ❤️'
    ])
    text = '\n'.join(text_lines)

    await message.answer(
        text,
        parse_mode='HTML',
        message_effect_id='5046509860389126442',  # 🎉 Эффект праздника
    )

    logger.info(
        '⭐ Отзыв полностью завершён и бонус начислен',
        user_id=db_user.id,
        review_id=review.id,
        review_type=review_type,
        total_days=total_days,
    )


# ──────────────────────────── Регистрация хендлеров ────────────────────────────

def register_handlers(dp: Dispatcher) -> None:
    """Регистрирует роутер отзывов в диспетчере."""
    dp.include_router(router)
    logger.info('⭐ Зарегистрированы обработчики системы отзывов')
