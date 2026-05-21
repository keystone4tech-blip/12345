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


# =====================================================================
'''

content = content.replace('# =====================================================================\n# ОБРАБОТКА КНОПОК ИЗ ЧАТА УВЕДОМЛЕНИЙ АДМИНОВ', handlers_code + '# ОБРАБОТКА КНОПОК ИЗ ЧАТА УВЕДОМЛЕНИЙ АДМИНОВ')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
