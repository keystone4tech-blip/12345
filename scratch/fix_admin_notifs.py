import sys, re
path = 'bot/app/handlers/admin/admin_reviews.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

def replace_notif_approve(m):
    return '''@router.callback_query(F.data.startswith('notif_review_approve:'))
async def handle_notif_review_approve(callback: types.CallbackQuery, db: AsyncSession):
    parts = callback.data.split(':')
    review_id = int(parts[1])
    
    result = await db.execute(select(UserReview).where(UserReview.id == review_id))
    review = result.scalar_one_or_none()
    
    if review:
        review.status = 'APPROVED'
        await db.commit()
    
    # Отмечаем в чате, что отзыв проверен
    text = callback.message.html_text or callback.message.caption
    if not text:
        text = "Отзыв"
        
    text += "\\n\\n✅ <b>Одобрено</b>"
    
    try:
        if callback.message.text:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id, text=text, reply_markup=None, parse_mode='HTML')
        elif callback.message.caption:
            await callback.bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=callback.message.message_id, caption=text, reply_markup=None, parse_mode='HTML')
        else:
            await callback.bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
            
        await callback.answer('✅ Отзыв одобрен', show_alert=False)
    except Exception as e:
        import structlog
        logger = structlog.get_logger(__name__)
        logger.error('Failed to update notif approve message', error=str(e))
        await callback.answer('Уже обработано или ошибка', show_alert=False)'''

def replace_notif_del_conf(m):
    return '''@router.callback_query(F.data.startswith('notif_review_del_conf:'))
async def handle_notif_review_del_conf(callback: types.CallbackQuery):
    parts = callback.data.split(':')
    review_id = int(parts[1])
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='Да, удалить', callback_data=f'notif_review_del_yes:{review_id}'),
            InlineKeyboardButton(text='Отмена', callback_data=f'notif_review_cancel:{review_id}')
        ]
    ])
    
    try:
        await callback.bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=markup)
        await callback.answer('Подтвердите удаление', show_alert=False)
    except Exception:
        await callback.answer('Ошибка обновления', show_alert=False)'''

def replace_notif_cancel(m):
    return '''@router.callback_query(F.data.startswith('notif_review_cancel:'))
async def handle_notif_review_cancel(callback: types.CallbackQuery):
    parts = callback.data.split(':')
    review_id = int(parts[1])
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='✅ Одобрить', callback_data=f'notif_review_approve:{review_id}'),
            InlineKeyboardButton(text='🗑 Удалить', callback_data=f'notif_review_del_conf:{review_id}')
        ]
    ])
    
    try:
        await callback.bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=markup)
        await callback.answer()
    except Exception:
        pass'''

def replace_notif_del_yes(m):
    return '''@router.callback_query(F.data.startswith('notif_review_del_yes:'))
async def handle_notif_review_del_yes(callback: types.CallbackQuery, db: AsyncSession):
    parts = callback.data.split(':')
    review_id = int(parts[1])
    
    result = await db.execute(select(UserReview).where(UserReview.id == review_id))
    review = result.scalar_one_or_none()
    
    if review:
        if review.review_content_id and ':' in review.review_content_id:
            try:
                chat_id_str, msg_id_str = review.review_content_id.split(':')
                await callback.bot.delete_message(chat_id=int(chat_id_str), message_id=int(msg_id_str))
            except Exception:
                pass
                
        await db.delete(review)
        await db.commit()
        await callback.answer('🗑 Отзыв удалён!', show_alert=False)
    else:
        await callback.answer('❌ Отзыв не найден!', show_alert=True)
        
    text = callback.message.html_text or callback.message.caption
    if not text:
        text = "Отзыв"
        
    text += "\\n\\n🗑 <b>Удалено из базы</b>"
    
    try:
        if callback.message.text:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id, text=text, reply_markup=None, parse_mode='HTML')
        elif callback.message.caption:
            await callback.bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=callback.message.message_id, caption=text, reply_markup=None, parse_mode='HTML')
        else:
            await callback.bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id, reply_markup=None)
    except Exception:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        except Exception:
            pass'''


content = re.sub(
    r'@router\.callback_query\(F\.data\.startswith\(\'notif_review_approve:\'\)\).*?(?=@router\.callback_query\(F\.data\.startswith\(\'notif_review_del_conf:\'\)\))',
    lambda m: replace_notif_approve(m) + '\n\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'@router\.callback_query\(F\.data\.startswith\(\'notif_review_del_conf:\'\)\).*?(?=@router\.callback_query\(F\.data\.startswith\(\'notif_review_cancel:\'\)\))',
    lambda m: replace_notif_del_conf(m) + '\n\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'@router\.callback_query\(F\.data\.startswith\(\'notif_review_cancel:\'\)\).*?(?=@router\.callback_query\(F\.data\.startswith\(\'notif_review_del_yes:\'\)\))',
    lambda m: replace_notif_cancel(m) + '\n\n',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'@router\.callback_query\(F\.data\.startswith\(\'notif_review_del_yes:\'\)\).*?(?=def register_handlers\(dp: Dispatcher\):)',
    lambda m: replace_notif_del_yes(m) + '\n\n\n',
    content,
    flags=re.DOTALL
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
