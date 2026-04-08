import os
import re
import json

files = ['locales/ru.json', 'locales/en.json', 'locales/ua.json', 'locales/fa.json', 'locales/zh.json']

def migrate(text):
    if not isinstance(text, str):
        return text
    # Fix bold: **text** -> <b>text</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # Fix italic: __text__ -> <i>text</i>
    text = re.sub(r'__(.*?)__', r'<i>\1</i>', text)
    return text

def process_file(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
    
    print(f"Processing {file_path}...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        new_data = {}
        for k, v in data.items():
            new_data[k] = migrate(v)
            
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        print(f"Successfully processed {file_path}")
    except Exception as e:
        print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    for f in files:
        process_file(f)
