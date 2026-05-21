import sys, re
path = 'bot/app/handlers/admin/admin_reviews.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

def replace_viewer(m):
    return '''async def handle_admin_reviews_viewer(callback: types.CallbackQuery, db: AsyncSession, db_user: User, override_data: str = None):
    """Показ одного отзыва (Карусель)."""
    data_to_parse = override_data if override_data else callback.data
    parts = data_to_parse.split(':')
    page = int(parts[1])
    
    old_media_msg_id = 0
    if len(parts) > 2:
        old_media_msg_id = int(parts[2])
        
    status = 'COMPLETED'
    if len(parts) > 3:
        status = parts[3]

    # Удаляем старые сообщения
    if old_media_msg_id > 0:
        try:
            await callback.bot.delete_message(chat_id=callback.from_user.id, message_id=old_media_msg_id)
        except Exception:
            pass
            
    try:
        await callback.bot.delete_message(chat_id=callback.from_user.id, message_id=callback.message.message_id)
    except Exception:
        pass

    # Считаем общее количество отзывов
    total_result = await db.execute(
        select(func.count(UserReview.id)).where(UserReview.status == status)
    )
    total_reviews = total_result.scalar() or 0

    if total_reviews == 0:
        try:
            await callback.answer('Нет отзывов.', show_alert=True)
        except Exception:
            pass
        await handle_admin_reviews_main(callback, db, db_user, send_new=True)
        return

    # Получаем 1 отзыв для текущей страницы
    result = await db.execute(
        select(UserReview, User)
        .join(User, User.id == UserReview.user_id)
        .where(UserReview.status == status)
        .order_by(desc(UserReview.created_at))
        .offset(page)
        .limit(1)
    )
    data = result.first()
    
    if not data:
        if page > 0:
            await handle_admin_reviews_viewer(callback, db, db_user, override_data=f'admin_reviews_nav:{page - 1}:0:{status}')
            return
            
        try:
            await callback.answer('Отзыв не найден.', show_alert=True)
        except Exception:
            pass
        return
        
    review, user = data

    new_media_msg_id = 0
    is_media = review.review_type in ['voice', 'video_note']
    
    if is_media and review.review_content_id:
        try:
            if ':' in review.review_content_id:
                from_chat_id, msg_id_str = review.review_content_id.split(':')
                copied_msg = await callback.bot.copy_message(
                    chat_id=callback.from_user.id,
                    from_chat_id=int(from_chat_id),
                    message_id=int(msg_id_str)
                )
                new_media_msg_id = copied_msg.message_id
            else:
                if review.review_type == 'voice':
                    sent_msg = await callback.bot.send_voice(chat_id=callback.from_user.id, voice=review.review_content_id)
                    new_media_msg_id = sent_msg.message_id
                elif review.review_type == 'video_note':
                    sent_msg = await callback.bot.send_video_note(chat_id=callback.from_user.id, video_note=review.review_content_id)
                    new_media_msg_id = sent_msg.message_id
        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.warning('Failed to send media', error=str(e), review_id=review.id)
            
    elif review.review_type == 'text' and not review.review_text and review.review_content_id and ':' in review.review_content_id:
        # Legacy text review
        try:
            from_chat_id, msg_id_str = review.review_content_id.split(':')
            copied_msg = await callback.bot.copy_message(
                chat_id=callback.from_user.id,
                from_chat_id=int(from_chat_id),
                message_id=int(msg_id_str)
            )
            new_media_msg_id = copied_msg.message_id
        except Exception:
            pass

    import html
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
        f"👤 <b>{user_name}</b> (ID: <code>{user.telegram_id}</code>)\\n"
        f"Оценка: {stars}\\n"
        f"Контент: {type_str}\\n"
        f"Награда: +{total_reward} дн.\\n"
        f"📅 {date_str}"
    )

    if review.review_type == 'text' and review.review_text:
        text += f"\\n\\n<b>Текст отзыва:</b>\\n{review.review_text}"

    markup = get_admin_review_viewer_keyboard(
        review_id=review.id, 
        current_page=page, 
        total_pages=total_reviews, 
        media_msg_id=new_media_msg_id, 
        language=db_user.language,
        status=status
    )

    await callback.bot.send_message(chat_id=callback.from_user.id, text=text, reply_markup=markup, parse_mode='HTML')
        
    try:
        await callback.answer()
    except Exception:
        pass\n\n\n'''

content = re.sub(
    r'async def handle_admin_reviews_viewer\(callback: types\.CallbackQuery.*?(?=@router\.callback_query\(F\.data\.startswith\(\'admin_reviews_approve:\'\)\))',
    replace_viewer,
    content,
    flags=re.DOTALL
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
