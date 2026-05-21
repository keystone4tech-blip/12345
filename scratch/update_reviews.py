import sys, re

path = 'bot/app/handlers/reviews.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update the call to get_user_reviews_carousel_keyboard
target1 = '''        # Если текст в новой колонке
        if review_obj.review_type == 'text' and review_obj.review_text:
            review_text += f"\\n\\n{review_obj.review_text}"
        
        kb = get_user_reviews_carousel_keyboard(current_page, total_pages, media_msg_id=new_media_msg_id, language=db_user.language)'''

replacement1 = '''        # Если текст в новой колонке
        if review_obj.review_type == 'text' and review_obj.review_text:
            review_text += f"\\n\\n{review_obj.review_text}"
            
        has_review = False
        user_review_check = await db.scalar(select(UserReview.id).where(UserReview.user_id == db_user.id))
        if user_review_check:
            has_review = True
        
        kb = get_user_reviews_carousel_keyboard(
            current_page, 
            total_pages, 
            media_msg_id=new_media_msg_id, 
            language=db_user.language,
            has_review=has_review
        )'''

if target1 in content:
    content = content.replace(target1, replacement1)
else:
    print("Could not find target1 in reviews.py")

# 2. Add the handle_user_review_start function before handle_user_reviews_carousel
target2 = '''@router.callback_query(F.data.startswith("user_reviews_carousel:"))
async def handle_user_reviews_carousel('''

replacement2 = '''@router.callback_query(F.data == 'user_review_start')
async def handle_user_review_start(
    callback: types.CallbackQuery,
    db_user: User,
    db: AsyncSession
):
    from app.services.reviews_service import reviews_service
    
    if not reviews_service.bot:
        reviews_service.set_bot(callback.bot)
        
    # Удаляем текущее сообщение (карусель), так как запрос на отзыв придет новым сообщением
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    await reviews_service._send_single_request(db_user)
    await callback.answer('Пожалуйста, оцените наш сервис!')


@router.callback_query(F.data.startswith("user_reviews_carousel:"))
async def handle_user_reviews_carousel('''

if target2 in content:
    content = content.replace(target2, replacement2)
else:
    print("Could not find target2 in reviews.py")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
