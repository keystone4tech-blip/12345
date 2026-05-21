import sys, re
path = 'bot/app/keyboards/admin.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add the new button to get_admin_reviews_keyboard
new_button = '''            [
                InlineKeyboardButton(
                    text='⚙️ Настройки системы отзывов',
                    callback_data='botcfg_cat:other:REVIEWS:1:1'
                )
            ],
            [
                InlineKeyboardButton(
                    text='🚀 Принудительно отправить отзывы',
                    callback_data='admin_review_force_broadcast'
                )
            ],'''

content = content.replace('''            [
                InlineKeyboardButton(
                    text='⚙️ Настройки системы отзывов',
                    callback_data='botcfg_cat:other:REVIEWS:1:1'
                )
            ],''', new_button)

# Add get_admin_review_broadcast_confirm_keyboard before get_admin_review_viewer_keyboard
confirm_keyboard = '''def get_admin_review_broadcast_confirm_keyboard(language: str = 'ru') -> InlineKeyboardMarkup:
    texts = get_texts(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='✅ Да', callback_data='admin_review_broadcast_yes'),
                InlineKeyboardButton(text='❌ Нет', callback_data='admin_reviews')
            ]
        ]
    )

def get_admin_review_viewer_keyboard('''

content = content.replace('def get_admin_review_viewer_keyboard(', confirm_keyboard)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
