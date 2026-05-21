"""
Обработчики для управления отзывами в админ-панели.
"""

import html
import structlog
from aiogram import Router, F, types, Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.database.models import User, UserReview
from app.keyboards.admin import (
    get_admin_reviews_keyboard,
    get_admin_review_viewer_keyboard,
    get_admin_review_del_confirm_keyboard,
)
from app.localization.texts import get_texts

logger = structlog.get_logger(__name__)
router = Router(name='admin_reviews')

@router.callback_query(F.data == 'admin_reviews')
async def handle_admin_reviews_main(callback: types.CallbackQuery, db: AsyncSession, db_user: User, send_new: bool = False):
    """Главное меню отзывов (Статистика)."""
    texts = get_texts(db_user.language)

    # Получаем статистику
    result = await db.execute(
        select(
            func.count(UserReview.id).label('total'),
            func.avg(UserReview.rating).label('avg_rating')
        ).where(UserReview.status == 'COMPLETED')
    )
    row = result.fetchone()
    total = row.total if row and row.total else 0
    avg_rating = round(row.avg_rating, 1) if row and row.avg_rating else 0.0

    text = texts.t('ADMIN_REVIEWS_TITLE', '⭐ Отзывы пользователей\n\nВсего отзывов: {total}\nСредняя оценка: {avg_rating} ⭐').format(
        total=total,
        avg_rating=avg_rating
    )

    if send_new:
        await callback.message.answer(text, reply_markup=get_admin_reviews_keyboard(db_user.language), parse_mode='HTML')
    else:
        await callback.message.edit_text(text, reply_markup=get_admin_reviews_keyboard(db_user.language), parse_mode='HTML')
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith('admin_reviews_list:'))
@router.callback_query(F.data.startswith('admin_reviews_nav:'))
async def handle_admin_reviews_viewer(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    """Показ одного отзыва (Карусель)."""
    parts = callback.data.split(':')
    page = int(parts[1])
    
    old_media_msg_id = 0
    if len(parts) > 2:
        old_media_msg_id = int(parts[2])

    # Удаляем старые сообщения (если листаем)
    if old_media_msg_id > 0:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=old_media_msg_id)
        except Exception:
            pass
            
    # Удаляем текущее сообщение (меню или старый отзыв), чтобы порядок сообщений был верным
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Считаем общее количество завершённых отзывов
    total_result = await db.execute(
        select(func.count(UserReview.id)).where(UserReview.status == 'COMPLETED')
    )
    total_reviews = total_result.scalar() or 0

    if total_reviews == 0:
        await callback.answer('Нет отзывов.', show_alert=True)
        # Так как мы удалили сообщение, нужно обязательно вернуть главное меню
        await handle_admin_reviews_main(callback, db, db_user, send_new=True)
        return

    # Получаем 1 отзыв для текущей страницы
    result = await db.execute(
        select(UserReview, User)
        .join(User, User.id == UserReview.user_id)
        .where(UserReview.status == 'COMPLETED')
        .order_by(desc(UserReview.created_at))
        .offset(page)
        .limit(1)
    )
    data = result.first()
    
    if not data:
        # Если дошли до конца (или удалили последний на странице), переходим на предыдущую
        if page > 0:
            callback.data = f'admin_reviews_nav:{page - 1}:0'
            await handle_admin_reviews_viewer(callback, db, db_user)
            return
            
        await callback.answer('Отзыв не найден.', show_alert=True)
        return
        
    review, user = data

    new_media_msg_id = 0
    if review.review_content_id:
        try:
            if ':' in review.review_content_id:
                from_chat_id, msg_id_str = review.review_content_id.split(':')
                from_chat_id = int(from_chat_id)
                msg_id = int(msg_id_str)
            else:
                from_chat_id = user.telegram_id
                msg_id = int(review.review_content_id)
                
            copied_msg = await callback.bot.copy_message(
                chat_id=callback.message.chat.id,
                from_chat_id=from_chat_id,
                message_id=msg_id
            )
            new_media_msg_id = copied_msg.message_id
        except ValueError:
            # Легаси: если там сохранен file_id (строка с буквами)
            try:
                if review.review_type == 'voice':
                    sent_msg = await callback.bot.send_voice(chat_id=callback.message.chat.id, voice=review.review_content_id)
                    new_media_msg_id = sent_msg.message_id
                elif review.review_type == 'video_note':
                    sent_msg = await callback.bot.send_video_note(chat_id=callback.message.chat.id, video_note=review.review_content_id)
                    new_media_msg_id = sent_msg.message_id
            except Exception as le:
                logger.warning('Failed to send legacy review media', error=str(le), review_id=review.id)
        except Exception as e:
            logger.warning('Failed to copy review media', error=str(e), review_id=review.id)

    stars = '⭐' * review.rating if review.rating else 'Нет оценки'
    content_type = review.review_type or 'none'
    
    type_str = 'Отсутствует'
    if content_type == 'text':
        type_str = '📝 Текст'
    elif content_type == 'voice':
        type_str = '🎙 Голос'
    elif content_type == 'video_note':
        type_str = '🎥 Видео'
        
    user_name = html.escape(user.full_name) if user.full_name else 'Без имени'
    if user.username:
        user_name += f" (@{html.escape(user.username)})"
        
    date_str = review.created_at.strftime('%d.%m.%Y %H:%M') if review.created_at else 'Неизвестно'
    
    star_reward = review.star_reward_days or 0
    content_reward = review.content_reward_days or 0
    total_reward = star_reward + content_reward
    
    text = (
        f"👤 <b>{user_name}</b> (ID: <code>{user.telegram_id}</code>)\n"
        f"Оценка: {stars}\n"
        f"Контент: {type_str}\n"
        f"Награда: +{total_reward} дн.\n"
        f"📅 {date_str}"
    )

    markup = get_admin_review_viewer_keyboard(
        review_id=review.id, 
        current_page=page, 
        total_pages=total_reviews, 
        media_msg_id=new_media_msg_id, 
        language=db_user.language
    )

    await callback.message.answer(text, reply_markup=markup, parse_mode='HTML')
        
    try:
        await callback.answer()
    except Exception:
        pass


@router.callback_query(F.data.startswith('admin_reviews_approve:'))
async def handle_admin_reviews_approve(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    """Одобрение отзыва (переход к следующему)."""
    parts = callback.data.split(':')
    # review_id = int(parts[1]) # Можно использовать для смены статуса в БД в будущем
    page = int(parts[2])
    media_msg_id = int(parts[3])
    
    await callback.answer('✅ Отзыв просмотрен!', show_alert=False)
    
    # Просто перелистываем вперед (к старому отзыву, т.к. сортировка desc(created_at))
    # Либо назад? Нумерация 0, 1, 2... 0 - самый новый. 
    # Так как мы просто смотрим, переходим к следующей странице
    callback.data = f'admin_reviews_nav:{page + 1}:{media_msg_id}'
    await handle_admin_reviews_viewer(callback, db, db_user)


@router.callback_query(F.data.startswith('admin_reviews_del_conf:'))
async def handle_admin_reviews_del_conf(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    """Подтверждение удаления отзыва."""
    parts = callback.data.split(':')
    review_id = int(parts[1])
    page = int(parts[2])
    media_msg_id = int(parts[3])
    
    markup = get_admin_review_del_confirm_keyboard(review_id, page, media_msg_id, db_user.language)
    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer('Подтвердите удаление', show_alert=False)


@router.callback_query(F.data.startswith('admin_reviews_del_yes:'))
async def handle_admin_reviews_del_yes(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    """Удаление отзыва после подтверждения."""
    parts = callback.data.split(':')
    review_id = int(parts[1])
    page = int(parts[2])
    media_msg_id = int(parts[3])
    
    result = await db.execute(select(UserReview).where(UserReview.id == review_id))
    review = result.scalar_one_or_none()
    
    if review:
        await db.delete(review)
        await db.commit()
        await callback.answer('🗑 Отзыв удалён!', show_alert=False)
    else:
        await callback.answer('❌ Отзыв не найден!', show_alert=True)
        
    # При удалении количество отзывов уменьшилось, поэтому остаемся на той же странице (page)
    callback.data = f'admin_reviews_nav:{page}:{media_msg_id}'
    await handle_admin_reviews_viewer(callback, db, db_user)


@router.callback_query(F.data.startswith('admin_reviews_exit:'))
async def handle_admin_reviews_exit(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    """Выход из карусели отзывов."""
    parts = callback.data.split(':')
    media_msg_id = int(parts[1]) if len(parts) > 1 else 0
    
    if media_msg_id > 0:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=media_msg_id)
        except Exception:
            pass
            
    # Заменяем текущее сообщение с кнопками на главное меню
    await handle_admin_reviews_main(callback, db, db_user, send_new=False)


@router.callback_query(F.data == 'admin_review_test')
async def handle_admin_review_test(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    """Тестовая отправка сообщения с запросом на отзыв администратору."""
    from app.services.reviews_service import reviews_service
    
    try:
        if not reviews_service.bot:
            reviews_service.set_bot(callback.bot)
        await reviews_service._send_single_request(db_user)
        await callback.answer('✅ Тестовый запрос отправлен вам в личные сообщения!', show_alert=True)
    except Exception as e:
        logger.error('Failed to send test review request', error=str(e), user_id=db_user.id)
        await callback.answer('❌ Ошибка при отправке тестового запроса.', show_alert=True)


def register_handlers(dp: Dispatcher):
    dp.include_router(router)
