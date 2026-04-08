import json
import os
import re

# Регулярное выражение для поиска эмодзи (упрощенное, но широкое)
# Ищем символы в диапазонах эмодзи
emoji_pattern = re.compile(r'[\U00010000-\U0010ffff]', flags=re.UNICODE)

emojis = set()

locales_dir = r'c:\Users\Keystone-Tech\Desktop\сервис рекламы с впн\bot\locales'

for filename in os.listdir(locales_dir):
    if filename.endswith('.json'):
        with open(os.path.join(locales_dir, filename), 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Рекурсивно ищем строки и извлекаем эмодзи
            def find_emojis(obj):
                if isinstance(obj, str):
                    found = emoji_pattern.findall(obj)
                    for e in found:
                        emojis.add(e)
                elif isinstance(obj, dict):
                    for v in obj.values():
                        find_emojis(v)
                elif isinstance(obj, list):
                    for item in obj:
                        find_emojis(item)
            
            find_emojis(data)

# Также проверим texts.py
texts_path = r'c:\Users\Keystone-Tech\Desktop\сервис рекламы с впн\bot\app\localization\texts.py'
with open(texts_path, 'r', encoding='utf-8') as f:
    find_emojis(f.read())

with open('emojis_found.json', 'w', encoding='utf-8') as f:
    json.dump(sorted(list(emojis)), f, ensure_ascii=False, indent=2)

print(f"Готово! Найдено {len(emojis)} уникальных эмодзи. Результаты в emojis_found.json")
