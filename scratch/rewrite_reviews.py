import sys
path = 'bot/app/handlers/reviews.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

import re
def replace_func(m):
    return '''
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
        
        # Получаем данные пользователя для отображения имени
        result = await db.execute(select(User).where(User.id == review_obj.user_id))
        review_user = result.scalar_one_or_none()
        
        # Удаляем старое медиа сообщение (если было)
        if media_msg_id > 0:
            try:
                await bot.delete_message(chat_id=callback.message.chat.id, message_id=media_msg_id)
            except Exception:
                pass
                
        # Удаляем старое сообщение с текстом/кнопками
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
'''

new_content = re.sub(r'(?<=@router\.callback_query\(F\.data\.startswith\(\"user_reviews_carousel:\"\)\)\nasync def handle_user_reviews_carousel\().*?def register_handlers\(dp: Dispatcher\) -> None:', lambda m: replace_func(m) + '\ndef register_handlers(dp: Dispatcher) -> None:', content, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)
