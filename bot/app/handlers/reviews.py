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
from aiogram import Router, F, types, Dispatcher, Bot
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
            f'✅ <b>Спасибо за вашу оценку {stars}!</b>\n',
            '─────────────────────\n',
            '😔 <b>Что мы можем сделать лучше?</b>\n',
            'Пожалуйста, расскажите, что вам не понравилось. Ваша обратная связь критически важна для нас, чтобы исправить проблемы.\n'
        ]
        
        has_content_rewards = any(d > 0 for d in [text_days, voice_days, video_days])
        if has_content_rewards:
            text_lines.append('В качестве извинений и благодарности за развёрнутый ответ мы начислим дополнительные дни.\n')
            
        text_lines.append('<i>Просто отправьте текст, голосовое сообщение или видео-кружок прямо сейчас!</i>')
        text = '\n'.join(text_lines)
    else:
        text_lines = [
            f'✅ <b>Спасибо за оценку {stars}!</b>\n',
            '─────────────────────\n',
            '📝 <b>Хотите получить дополнительные бонусы?</b>\n',
            'Оставьте развёрнутый отзыв о нашем сервисе! Расскажите, что вам нравится больше всего или чего не хватает.\n'
        ]
        
        has_content_rewards = any(d > 0 for d in [text_days, voice_days, video_days])
        if has_content_rewards:
            text_lines.append('<i>Просто отправьте текст, голосовое или видео-кружок прямо сейчас, и мы увеличим ваш бонус!</i>\n')
            
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
        '🎉 <b>Благодарим вас за оценку!</b>\n\n'
    )
    if total_days > 0:
        text += f'В качестве благодарности мы начислили вам <b>+{total_days} дн.</b> дополнительно к вашему тарифу! 🎁\n\n'
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
        content_id=str(message.message_id),
    )


@router.message(ReviewStates.waiting_for_content, F.voice)
async def handle_voice_review(
    message: types.Message,
    db_user: User,
    db: AsyncSession,
    state: FSMContext,
):
    """Обработка голосового отзыва от пользователя."""
    await _finalize_review(
        db=db,
        db_user=db_user,
        state=state,
        message=message,
        review_type='voice',
        content_id=str(message.message_id),
    )


@router.message(ReviewStates.waiting_for_content, F.video_note)
async def handle_video_note_review(
    message: types.Message,
    db_user: User,
    db: AsyncSession,
    state: FSMContext,
):
    """Обработка видео-кружка от пользователя."""
    await _finalize_review(
        db=db,
        db_user=db_user,
        state=state,
        message=message,
        review_type='video_note',
        content_id=str(message.message_id),
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

    # === НОВАЯ ЛОГИКА СОХРАНЕНИЯ КОНТЕНТА ===
    # Сохраняем медиа/текст в админском чате, чтобы оно не исчезло при удалении у пользователя
    final_content_id = content_id
    if content_id:
        from app.config import settings
        admin_chat_id = settings.get_admin_notifications_chat_id()
        
        admin_ids = settings.get_admin_ids()
        if not admin_chat_id and admin_ids:
            admin_chat_id = admin_ids[0]
            
        if admin_chat_id:
            try:
                # Копируем само сообщение пользователя
                copied_msg = await message.bot.copy_message(
                    chat_id=admin_chat_id,
                    from_chat_id=message.chat.id,
                    message_id=int(content_id)
                )
                
                # Сохраняем связку chat_id:message_id
                final_content_id = f"{admin_chat_id}:{copied_msg.message_id}"
                
                # Формируем текст уведомления
                import html
                stars = '⭐' * review.rating if review.rating else 'Нет оценки'
                c_type = review_type or 'none'
                
                type_str = 'Отсутствует'
                if c_type == 'text':
                    type_str = '📝 Текст'
                elif c_type == 'voice':
                    type_str = '🎙 Голос'
                elif c_type == 'video_note':
                    type_str = '🎥 Видео'
                    
                user_name = html.escape(db_user.full_name) if db_user.full_name else 'Без имени'
                if db_user.username:
                    user_name += f" (@{html.escape(db_user.username)})"
                    
                date_str = review.created_at.strftime('%d.%m.%Y %H:%M') if review.created_at else 'Неизвестно'
                
                star_reward = review.star_reward_days or 0
                content_reward = review.content_reward_days or 0
                total_reward = star_reward + content_reward
                
                text = (
                    f"📥 <b>Новый отзыв в системе</b>\n\n"
                    f"👤 <b>{user_name}</b> (ID: <code>{db_user.telegram_id}</code>)\n"
                    f"Оценка: {stars}\n"
                    f"Контент: {type_str}\n"
                    f"Награда: +{total_reward} дн.\n"
                    f"📅 {date_str}"
                )
                
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text='✅ Одобрить', callback_data=f'notif_review_approve:{review.id}'),
                        InlineKeyboardButton(text='🗑 Удалить', callback_data=f'notif_review_del_conf:{review.id}')
                    ]
                ])
                
                await message.bot.send_message(
                    chat_id=admin_chat_id,
                    text=text,
                    reply_markup=markup,
                    parse_mode='HTML',
                    reply_to_message_id=copied_msg.message_id
                )
                
            except Exception as e:
                logger.error("Failed to backup review message to admin chat", error=str(e), user_id=db_user.id)

    # Завершаем отзыв
    total_days = await reviews_service.complete_review(
        db=db,
        review=review,
        review_type=review_type,
        content_id=final_content_id,
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

    # Формируем благодарственное сообщение без разбивки наград
    text_lines = [
        f'🎉 <b>Благодарим вас за {type_name}!</b>\n'
    ]
        
    if total_days > 0:
        text_lines.append(f'В качестве благодарности мы начислили вам <b>+{total_days} дн.</b> дополнительно к вашему тарифу! 🎁\n')
    
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

@router.callback_query(F.data.startswith("user_reviews_carousel:"))
async def handle_user_reviews_carousel(
    callback: types.CallbackQuery,
    db: AsyncSession,
    db_user: User,
    bot: Bot
):
    try:
        parts = callback.data.split(":")
        current_page = int(parts[1]) if len(parts) > 1 else 0
        media_msg_id = int(parts[2]) if len(parts) > 2 and parts[2] and parts[2] != "0" else 0

        from sqlalchemy import select, func, desc
        from app.database.models import UserReview, User
        
        count_stmt = select(func.count(UserReview.id)).where(UserReview.status == "APPROVED")
        total_reviews = await db.scalar(count_stmt)
        
        if total_reviews == 0:
            await callback.answer("Одобренных отзывов пока нет.", show_alert=True)
            return
            
        limit = 1
        total_pages = total_reviews
        if current_page < 0:
            current_page = 0
        if current_page >= total_pages:
            current_page = total_pages - 1
            
        offset = current_page * limit
        
        stmt = select(UserReview).where(UserReview.status == "APPROVED").order_by(desc(UserReview.created_at)).offset(offset).limit(limit)
        review_obj = await db.scalar(stmt)
        
        if not review_obj:
            await callback.answer("Отзыв не найден.", show_alert=True)
            return

        from app.keyboards.inline import get_user_reviews_carousel_keyboard
        import html
        
        result = await db.execute(select(User).where(User.id == review_obj.user_id))
        review_user = result.scalar_one_or_none()
        
        if media_msg_id > 0:
            try:
                await bot.delete_message(chat_id=callback.message.chat.id, message_id=media_msg_id)
            except Exception:
                pass
                
        try:
            await callback.message.delete()
        except Exception:
            pass

        new_media_msg_id = 0
        if review_obj.review_content_id:
            try:
                if ':' in review_obj.review_content_id:
                    from_chat_id, msg_id_str = review_obj.review_content_id.split(':')
                    from_chat_id = int(from_chat_id)
                    msg_id = int(msg_id_str)
                else:
                    from_chat_id = review_obj.user_id
                    msg_id = int(review_obj.review_content_id)
                    
                copied_msg = await bot.copy_message(
                    chat_id=callback.message.chat.id,
                    from_chat_id=from_chat_id,
                    message_id=msg_id
                )
                new_media_msg_id = copied_msg.message_id
            except ValueError:
                try:
                    if review_obj.review_type == 'voice':
                        sent_msg = await bot.send_voice(chat_id=callback.message.chat.id, voice=review_obj.review_content_id)
                        new_media_msg_id = sent_msg.message_id
                    elif review_obj.review_type == 'video_note':
                        sent_msg = await bot.send_video_note(chat_id=callback.message.chat.id, video_note=review_obj.review_content_id)
                        new_media_msg_id = sent_msg.message_id
                except Exception:
                    pass
            except Exception:
                pass

        user_name = html.escape(review_user.full_name) if review_user and review_user.full_name else 'Без имени'
        if review_user and review_user.username:
            user_name += f" (@{html.escape(review_user.username)})"
            
        review_text = f"👤 <b>{user_name}</b>\n"
        if review_obj.rating:
            review_text += f"Оценка: {'⭐' * review_obj.rating}\n"
        review_text += f"📅 {review_obj.created_at.strftime('%d.%m.%Y')}"
        
        kb = get_user_reviews_carousel_keyboard(current_page, total_pages, media_msg_id=new_media_msg_id, language=db_user.language)
        
        await bot.send_message(chat_id=callback.message.chat.id, text=review_text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        import structlog
        logger = structlog.get_logger(__name__)
        logger.error("Error in user reviews carousel", error=str(e))
        await callback.answer("Произошла ошибка", show_alert=True)

def register_handlers(dp: Dispatcher) -> None:
    """Регистрирует роутер отзывов в диспетчере."""
    dp.include_router(router)
    logger.info('⭐ Зарегистрированы обработчики системы отзывов')
