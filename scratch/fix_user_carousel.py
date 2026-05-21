import sys

path = 'bot/app/handlers/reviews.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update handle_dismiss
target_dismiss = '''@router.callback_query(F.data == 'review_dismiss')
async def handle_dismiss(
    callback: types.CallbackQuery,
    state: FSMContext,
):
    """Пользователь отказался оставлять отзыв (нажал «Не сейчас»)."""
    await state.clear()

    try:
        await callback.message.edit_text(
            '👋 Хорошо! Мы спросим вас позже.\\n\\n'
            '💙 Спасибо, что пользуетесь нашим сервисом!',
            parse_mode='HTML',
        )
    except Exception:
        pass

    await callback.answer()'''

replacement_dismiss = '''@router.callback_query(F.data == 'review_dismiss')
async def handle_dismiss(
    callback: types.CallbackQuery,
    state: FSMContext,
):
    """Пользователь отказался оставлять отзыв (нажал «Не сейчас»)."""
    await state.clear()

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🏠 В главное меню', callback_data='back_to_menu')]
    ])

    try:
        await callback.message.edit_text(
            '👋 Хорошо! Мы спросим вас позже.\\n\\n'
            '💙 Спасибо, что пользуетесь нашим сервисом!',
            parse_mode='HTML',
            reply_markup=keyboard
        )
    except Exception:
        pass

    await callback.answer()'''

if target_dismiss in content:
    content = content.replace(target_dismiss, replacement_dismiss)
else:
    print("Could not find target_dismiss")


# 2. Update handle_user_reviews_carousel text formatting
target_text = '''        user_name = html.escape(review_user.full_name) if review_user and review_user.full_name else 'Без имени'
        
        review_text = ""
        if review_obj.rating:
            review_text += f"Оценка: {'⭐' * review_obj.rating}\\n"
        
        review_text += f"👤 <b>{user_name}</b>\\n"
        review_text += f"📅 {review_obj.created_at.strftime('%d.%m.%Y')}"
        
        # Если текст в новой колонке
        if review_obj.review_type == 'text' and review_obj.review_text:
            review_text += f"\\n\\n{review_obj.review_text}"
            
        has_review = False'''

replacement_text = '''        user_name = html.escape(review_user.full_name) if review_user and review_user.full_name else 'Без имени'
        
        review_text = ""
        if review_obj.rating:
            review_text += f"Оценка: {'⭐' * review_obj.rating}\\n"
        
        # Форматирование текстового отзыва
        if review_obj.review_type == 'text' and review_obj.review_text:
            text_content = review_obj.review_text.strip()
            # Если текст слишком большой, отправляем его отдельным сообщением сверху
            if len(text_content) > 3000:
                try:
                    sent_msg = await bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=text_content,
                        parse_mode="HTML"
                    )
                    new_media_msg_id = sent_msg.message_id
                except Exception:
                    pass
            else:
                review_text += f"Отзыв:\\n{text_content}\\n\\n"
                
        review_text += f"👤 <b>{user_name}</b>\\n"
        review_text += f"📅 {review_obj.created_at.strftime('%d.%m.%Y')}"
            
        has_review = False'''

if target_text in content:
    content = content.replace(target_text, replacement_text)
else:
    print("Could not find target_text")


with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated successfully")
