import sys, re
path = 'bot/app/handlers/reviews.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the broken multiline f-strings with proper single-line ones with \\n
content = re.sub(r'review_text = f"рџ‘¤ <b>\{user_name\}</b>\n"', 'review_text = f"👤 <b>{user_name}</b>\\\\n"', content)
content = re.sub(r'review_text \+= f"РћС†РµРЅРєР°: \{\'в­ђ\' \* review_obj\.rating\}\n"', 'review_text += f"Оценка: {\\'⭐\\' * review_obj.rating}\\\\n"', content)
content = re.sub(r'review_text \+= f"рџ“… \{review_obj\.created_at\.strftime\(\'%d\.%m\.%Y\'\)\}"', 'review_text += f"📅 {review_obj.created_at.strftime(\'%d.%m.%Y\')}"', content)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
