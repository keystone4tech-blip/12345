import sys, re
path = 'bot/app/handlers/reviews.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace handle_text_review to _finalize_review block
def replace_handlers(m):
    return '''@router.message(ReviewStates.waiting_for_content, F.text)
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
        text_content=message.html_text or message.text,
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
        content_id=message.voice.file_id,
        text_content=None,
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
        content_id=message.video_note.file_id,
        text_content=None,
    )


@router.message(ReviewStates.waiting_for_content)
async def handle_unsupported_content(
    message: types.Message,
):
    """Обработка неподдерживаемого типа контента."""
    await message.answer(
        '❌ <b>Неподдерживаемый формат</b>\\n\\n'
        'Пожалуйста, отправьте:\\n'
        '📝 Текстовое сообщение\\n'
        '🎙 Голосовое сообщение\\n'
        '🎥 Видео-кружок\\n\\n'
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
    text_content: str | None = None,
) -> None:
    """
    Общая логика завершения отзыва с контентом.
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
            '❌ Отзыв не найден. Возможно, время истекло.\\n'
            'Попробуйте оставить отзыв позже.',
            parse_mode='HTML',
        )
        await state.clear()
        return

    # === НОВАЯ ЛОГИКА СОХРАНЕНИЯ КОНТЕНТА ===
    # Отправляем в админский чат независимо
    from app.config import settings
    admin_chat_id = settings.get_admin_notifications_chat_id()
    
    admin_ids = settings.get_admin_ids()
    if not admin_chat_id and admin_ids:
        admin_chat_id = admin_ids[0]
        
    if admin_chat_id:
        try:
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
            content_reward = reviews_service.get_content_reward(c_type)
            total_reward = star_reward + content_reward
            
            caption = (
                f"📥 <b>Новый отзыв в системе</b>\\n\\n"
                f"👤 <b>{user_name}</b> (ID: <code>{db_user.telegram_id}</code>)\\n"
                f"Оценка: {stars}\\n"
                f"Контент: {type_str}\\n"
                f"Награда: +{total_reward} дн.\\n"
                f"📅 {date_str}"
            )
            if c_type == 'text' and text_content:
                caption += f"\\n\\n<b>Текст отзыва:</b>\\n{text_content}"
                
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text='✅ Одобрить', callback_data=f'notif_review_approve:{review.id}'),
                    InlineKeyboardButton(text='🗑 Удалить', callback_data=f'notif_review_del_conf:{review.id}')
                ]
            ])
            
            if c_type == 'text':
                await message.bot.send_message(chat_id=admin_chat_id, text=caption, reply_markup=markup, parse_mode='HTML')
            elif c_type == 'voice' and content_id:
                await message.bot.send_voice(chat_id=admin_chat_id, voice=content_id, caption=caption, reply_markup=markup, parse_mode='HTML')
            elif c_type == 'video_note' and content_id:
                await message.bot.send_message(chat_id=admin_chat_id, text=caption, reply_markup=markup, parse_mode='HTML')
                await message.bot.send_video_note(chat_id=admin_chat_id, video_note=content_id)
                
        except Exception as e:
            logger.error("Failed to send review to admin chat", error=str(e), user_id=db_user.id)

    # Завершаем отзыв
    total_days = await reviews_service.complete_review(
        db=db,
        review=review,
        review_type=review_type,
        content_id=content_id,
        text_content=text_content,
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
        f'🎉 <b>Благодарим вас за {type_name}!</b>\\n'
    ]
        
    if total_days > 0:
        text_lines.append(f'В качестве благодарности мы начислили вам <b>+{total_days} дн.</b> дополнительно к вашему тарифу! 🎁\\n')
    
    text_lines.extend([
        '💙 Ваше мнение очень ценно для нас!',
        'Благодаря вашим отзывам мы становимся лучше ❤️'
    ])
    final_text = '\\n'.join(text_lines)

    await message.answer(
        final_text,
        parse_mode='HTML',
        message_effect_id='5046509860389126442',  # 🎉 Эффект праздника
    )

    logger.info(
        '⭐ Отзыв полностью завершён и бонус начислен',
        user_id=db_user.id,
        review_id=review.id,
        review_type=review_type,
        total_days=total_days,
    )'''

content = re.sub(
    r'@router\.message\(ReviewStates\.waiting_for_content, F\.text\).*?logger\.info\(\n        \'⭐ Отзыв полностью завершён и бонус начислен\',\n        user_id=db_user\.id,\n        review_id=review\.id,\n        review_type=review_type,\n        total_days=total_days,\n    \)',
    replace_handlers,
    content,
    flags=re.DOTALL
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
