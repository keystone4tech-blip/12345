import sys, re
path = 'bot/app/handlers/admin/admin_reviews.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

handlers_code = '''
@router.callback_query(F.data == 'admin_review_force_broadcast')
async def handle_admin_review_force_broadcast(callback: types.CallbackQuery, db_user: User):
    from app.keyboards.admin import get_admin_review_broadcast_confirm_keyboard
    markup = get_admin_review_broadcast_confirm_keyboard(db_user.language)
    text = "❓ <b>Действительно ли разослать отзывы?</b>\\n\\nЭто запустит принудительную рассылку запросов всем пользователям, которые подходят под условия (не оставляли отзыв 30 дней и потратили нужное количество трафика)."
    await callback.message.edit_text(text, reply_markup=markup, parse_mode='HTML')
    await callback.answer()

@router.callback_query(F.data == 'admin_review_broadcast_yes')
async def handle_admin_review_broadcast_yes(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    from app.services.reviews_service import reviews_service
    import asyncio
    
    if not reviews_service.bot:
        reviews_service.set_bot(callback.bot)
        
    asyncio.create_task(reviews_service._send_review_requests())
    
    from app.keyboards.admin import get_admin_reviews_keyboard
    stats = await reviews_service.get_review_stats(db)
    markup = get_admin_reviews_keyboard(
        db_user.language, 
        pending_count=stats['pending'], 
        approved_count=stats['approved']
    )
    
    await callback.message.edit_text(
        "✅ <b>Рассылка отзывов успешно запущена в фоновом режиме.</b>\\n\\nОна будет выполнена для всех подходящих пользователей.",
        reply_markup=markup,
        parse_mode='HTML'
    )
    await callback.answer('✅ Рассылка запущена', show_alert=False)

'''

# Add handlers after handle_admin_review_test
content = content.replace('''@router.callback_query(F.data == 'admin_review_test')
async def handle_admin_review_test(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    """Тестовая отправка сообщения с запросом на отзыв администратору."""
    from app.services.reviews_service import reviews_service
    
    try:
        if not reviews_service.bot:
            reviews_service.set_bot(callback.bot)
        await reviews_service._send_single_request(db_user)
        await callback.answer('✅ Тестовый запрос отправлен вам в личные сообщения!', show_alert=True)
    except Exception as e:
        logger.error('Failed to send test review request', error=str(e), user_id=db_user.id)''',
'''@router.callback_query(F.data == 'admin_review_test')
async def handle_admin_review_test(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    """Тестовая отправка сообщения с запросом на отзыв администратору."""
    from app.services.reviews_service import reviews_service
    
    try:
        if not reviews_service.bot:
            reviews_service.set_bot(callback.bot)
        await reviews_service._send_single_request(db_user)
        await callback.answer('✅ Тестовый запрос отправлен вам в личные сообщения!', show_alert=True)
    except Exception as e:
        logger.error('Failed to send test review request', error=str(e), user_id=db_user.id)''' + handlers_code)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
