"""
Обработчики для управления отзывами в админ-панели.
"""

import structlog
from aiogram import Router, F, types, Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.database.models import User, UserReview
from app.keyboards.admin import (
    get_admin_reviews_keyboard,
    get_admin_reviews_pagination_keyboard,
)
from app.localization.texts import get_texts

logger = structlog.get_logger(__name__)
router = Router(name='admin_reviews')

REVIEWS_PER_PAGE = 5


@router.callback_query(F.data == 'admin_reviews')
async def handle_admin_reviews_main(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
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

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_reviews_keyboard(db_user.language),
        parse_mode='HTML'
    )
    await callback.answer()


@router.callback_query(F.data.startswith('admin_reviews_list:'))
async def handle_admin_reviews_list(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    """Пагинированный список отзывов."""
    texts = get_texts(db_user.language)
    page = int(callback.data.split(':')[1])

    # Считаем общее количество завершённых отзывов
    total_result = await db.execute(
        select(func.count(UserReview.id)).where(UserReview.status == 'COMPLETED')
    )
    total_reviews = total_result.scalar() or 0

    if total_reviews == 0:
        await callback.answer(texts.t('ADMIN_REVIEWS_NO_DATA', 'Нет отзывов.'), show_alert=True)
        return

    total_pages = (total_reviews + REVIEWS_PER_PAGE - 1) // REVIEWS_PER_PAGE

    # Получаем отзывы для текущей страницы
    result = await db.execute(
        select(UserReview, User)
        .join(User, User.id == UserReview.user_id)
        .where(UserReview.status == 'COMPLETED')
        .order_by(desc(UserReview.created_at))
        .offset(page * REVIEWS_PER_PAGE)
        .limit(REVIEWS_PER_PAGE)
    )
    reviews_data = result.all()

    text_lines = [
        f"<b>{texts.t('ADMIN_REVIEWS_LIST', '📋 Список отзывов')}</b>\n",
        f"<i>{texts.t('ADMIN_REVIEWS_PAGE', 'Страница {current} из {total}').format(current=page+1, total=max(1, total_pages))}</i>\n"
    ]

    for review, user in reviews_data:
        stars = '⭐' * review.rating if review.rating else 'Нет оценки'
        content_type = review.review_type or 'none'
        
        type_str = 'Отсутствует'
        if content_type == 'text':
            type_str = '📝 Текст'
        elif content_type == 'voice':
            type_str = '🎙 Голос'
        elif content_type == 'video_note':
            type_str = '🎥 Видео'
            
        user_name = user.full_name
        if user.username:
            user_name += f" (@{user.username})"
            
        date_str = review.created_at.strftime('%d.%m.%Y %H:%M')
        
        text_lines.append(
            f"👤 <b>{user_name}</b> (ID: {user.telegram_id})\n"
            f"Оценка: {stars}\n"
            f"Контент: {type_str}\n"
            f"Награда: +{review.star_reward_days + review.content_reward_days} дн.\n"
            f"📅 {date_str}\n"
            f"──────────────"
        )

    text = '\n'.join(text_lines)

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_reviews_pagination_keyboard(page, total_pages, db_user.language),
        parse_mode='HTML'
    )
    await callback.answer()


def register_handlers(dp: Dispatcher) -> None:
    dp.include_router(router)
    logger.info('⭐ Зарегистрированы админские обработчики отзывов')
