"""Модуль для управления соответствием стандартных эмодзи и их Premium ID.

Этот модуль позволяет централизованно управлять заменой стандартных UTF-8 эмодзи
на кастомные Premium эмодзи через тег <tg-emoji> и параметр icon_custom_emoji_id.
"""

import re
import json
from typing import Any, Dict, Optional, TypeVar, Callable, Awaitable

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import (
    SendMessage, EditMessageText, EditMessageCaption, EditMessageReplyMarkup,
    SendPhoto, SendVideo, SendDocument, SendAnimation, SendVoice, SendVideoNote,
    AnswerCallbackQuery, Response,
)
from aiogram.methods.base import TelegramMethod

from app.config import settings

T = TypeVar("T")

# Базовый список эмодзи, которые используются в боте.
# Этот список используется для отображения в админ-панели.
BASE_EMOJIS = [
    # Статус и Навигация
    "✅", "❌", "⚠️", "➕", "🗑️", "✏️", "🔄", "🔍", "▶️", "⏸️", "⏹️", "🟢", "🟡", "🟠", "🔴", 
    "💤", "⏰", "⏳", "🚦", "🏠", "⬅️", "➡️", "🔙", "🔝", "⏭️", "🔚", "🔁", "🆔", "🆕", "🆘", "🚫", "🛑", "🔔", "🔗", "👇",
    
    # Финансы и Магазин
    "💰", "🪙", "💳", "💸", "🛒", "🏷", "📦", "📥", "📤", "📨", "📬", "🧾", "💎", "🎫", "🏦", "🏬", "🍎",
    
    # Система и Инструменты
    "⚙️", "🛠️", "🛠", "🔧", "🔩", "🖥", "💻", "📱", "📶", "📡", "🔑", "🔐", "🔒", "🔓", "🛡️", "🛡",
    "📊", "📈", "📉", "📋", "📅", "📆", "🗓", "📄", "📜", "📝", "📌", "📍", "📎", "🗳", "🗄", "🗑",
    
    # Пользователи и Связь
    "👤", "👥", "🤝", "🧑", "👋", "🙏", "💬", "📢", "📣", "📞", "🌐", "🌍", "🗺️", "ℹ️", "❓", "⭐", "🎨", "💡", "👀", "👁", "💪",
    
    # Разное и Эффекты
    "🚀", "⚡", "🔥", "🎁", "🎉", "🏆", "🏅", "🎖️", "🧪", "🧩", "🎲", "🎯", "🎭", "🎥", "📷", "📺", "🖼", 
    "🤖", "🥶", "🧊", "🧹", "🚚", "🛟"
]


# Кеширование регулярного выражения для оптимизации
_cached_emoji_pattern = None
_cached_map_hash = None

def get_premium_emoji_map() -> Dict[str, Optional[str]]:
    """Возвращает маппинг эмодзи из настроек, объединяя базовый список и пользовательские данные."""
    try:
        data_raw = settings.PREMIUM_EMOJIS_DATA
        data = json.loads(data_raw) if data_raw else {}
        
        # Объединяем базовый список и кастомные данные из БД
        full_map = {e: None for e in BASE_EMOJIS}
        if isinstance(data, dict):
            full_map.update(data)
        return full_map
    except Exception:
        return {e: None for e in BASE_EMOJIS}

def get_emoji_pattern():
    """Возвращает скомпилированное регулярное выражение для поиска эмодзи, подлежащих замене.
    
    Паттерн кешируется и пересобирается только при изменении состава ключей в маппинге.
    """
    global _cached_emoji_pattern, _cached_map_hash
    
    emoji_map = get_premium_emoji_map()
    # Создаем хеш состава ключей для проверки необходимости пересборки паттерна
    current_hash = hash(frozenset(emoji_map.keys()))
    
    if _cached_emoji_pattern is None or current_hash != _cached_map_hash:
        # Сортируем эмодзи по длине (дескрипторы из нескольких символов должны идти первыми)
        all_emojis = sorted(emoji_map.keys(), key=len, reverse=True)
        # Регулярка для поиска любого эмодзи из списка
        _cached_emoji_pattern = re.compile("|".join(re.escape(e) for e in all_emojis))
        _cached_map_hash = current_hash
        
    return _cached_emoji_pattern


def get_premium_emoji_id(emoji: str) -> Optional[str]:
    """Возвращает ID премиум-эмодзи для заданного стандартного эмодзи."""
    emoji_map = get_premium_emoji_map()
    return emoji_map.get(emoji)


# Регулярка для снятия существующих тегов <tg-emoji> (защита от двойного применения)
_TG_EMOJI_TAG_RE = re.compile(r'<tg-emoji[^>]*>(.*?)</tg-emoji>')


def replace_with_premium_emojis(text: str) -> str:
    """Заменяет все стандартные эмодзи в тексте на теги <tg-emoji>.
    
    Функция идемпотентна: если текст уже содержит теги <tg-emoji>,
    они сначала снимаются, а затем замена применяется заново.
    Это позволяет безопасно вызывать функцию повторно.
    """
    if not text:
        return text

    # Шаг 1: Снимаем существующие теги <tg-emoji> чтобы избежать двойной замены
    if '<tg-emoji' in text:
        text = _TG_EMOJI_TAG_RE.sub(r'\1', text)

    emoji_map = get_premium_emoji_map()
    pattern = get_emoji_pattern()

    def _replace(match):
        emoji = match.group(0)
        emoji_id = emoji_map.get(emoji)
        if emoji_id:
            return f'<tg-emoji emoji-id="{emoji_id}">{emoji}</tg-emoji>'
        return emoji

    return pattern.sub(_replace, text)


def extract_first_emoji(text: str) -> Optional[str]:
    """Извлекает первый эмодзи из строки, если он есть в нашем маппинге."""
    if not text:
        return None
        
    pattern = get_emoji_pattern()
    match = pattern.search(text)
    if match:
        return match.group(0)
    return None


def get_custom_emoji_id(message: Any) -> Optional[str]:
    """Извлекает ID премиум-эмодзи из сообщения, если он есть."""
    if not hasattr(message, "entities") or not message.entities:
        return None
        
    for entity in message.entities:
        if entity.type == "custom_emoji" and hasattr(entity, "custom_emoji_id"):
            return str(entity.custom_emoji_id)
    return None


def apply_premium_to_button(button: T) -> T:
    """Применяет Premium-эмодзи к кнопке (InlineKeyboardButton или KeyboardButton)."""
    # Проверяем, не помечена ли кнопка как "сохранить оригинал" (для админ-панели)
    keep_original = getattr(button, "_keep_emoji", False)

    if not settings.USE_PREMIUM_EMOJIS:
        # Даже если выключено, на всякий случай чистим от тегов, если они туда попали
        text = getattr(button, "text", None)
        if text and "<tg-emoji" in text:
            # Очищаем теги, оставляя только содержимое
            clean_text = re.sub(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', r'\1', text)
            setattr(button, "text", clean_text)
        return button

    text = getattr(button, "text", None)
    if not text:
        return button

    # Если в тексте есть HTML теги (из-за Texts), очищаем их
    if "<tg-emoji" in text:
        text = re.sub(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', r'\1', text)
        setattr(button, "text", text)

    # Проверяем существующий ID, если он установлен
    existing_id = getattr(button, "icon_custom_emoji_id", None)
    if existing_id:
        if str(existing_id).isdigit():
            return button
        else:
            # Сбрасываем некорректный ID
            setattr(button, "icon_custom_emoji_id", None)

    emoji = extract_first_emoji(text)
    if emoji:
        emoji_id = get_premium_emoji_id(emoji)
        if emoji_id and str(emoji_id).isdigit():
            try:
                setattr(button, "icon_custom_emoji_id", str(emoji_id))
                
                # Если не режим сохранения оригинала, удаляем эмодзи из текста
                if not keep_original:
                    # Удаляем только первое вхождение этого эмодзи
                    new_text = text.replace(emoji, "", 1).strip()
                    # Telegram не позволяет пустые кнопки, подставляем пробел если текста не осталось
                    if not new_text:
                        new_text = " "
                    setattr(button, "text", new_text)
            except Exception:
                # Если объект заморожен или не поддерживает установку атрибутов
                pass

    return button


# Типы методов, у которых нужно обрабатывать поле 'text'
_TEXT_METHODS = (SendMessage, EditMessageText)
# Типы методов, у которых нужно обрабатывать поле 'caption'
_CAPTION_METHODS = (SendPhoto, SendVideo, SendDocument, SendAnimation, SendVoice, EditMessageCaption)


class PremiumEmojiMiddleware(BaseRequestMiddleware):
    """Middleware для автоматического применения Premium-эмодзи.
    
    Обрабатывает:
    - text / caption — все исходящие сообщения, включая edit-запросы
    - reply_markup — inline- и reply-кнопки (icon_custom_emoji_id)
    - AnswerCallbackQuery.text — текст всплывающего уведомления
    """

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType,
        bot: Bot,
        method: TelegramMethod[Response[T]],
    ) -> Response[T]:
        if not settings.USE_PREMIUM_EMOJIS:
            return await make_request(bot, method)

        # ── 1. Обработка текста сообщений ──
        # SendMessage, EditMessageText → поле 'text'
        if isinstance(method, _TEXT_METHODS):
            raw_text = getattr(method, 'text', None)
            if raw_text and isinstance(raw_text, str):
                method.text = replace_with_premium_emojis(raw_text)

        # SendPhoto, SendVideo, SendVoice, EditMessageCaption и т.д. → поле 'caption'
        if isinstance(method, _CAPTION_METHODS):
            raw_caption = getattr(method, 'caption', None)
            if raw_caption and isinstance(raw_caption, str):
                method.caption = replace_with_premium_emojis(raw_caption)

        # AnswerCallbackQuery → поле 'text' (popup-уведомление, но tg-emoji там не работают — пропускаем)

        # ── 2. Обработка кнопок (reply_markup) ──
        if hasattr(method, "reply_markup") and method.reply_markup:
            markup = method.reply_markup
            if hasattr(markup, "inline_keyboard"):
                for row in markup.inline_keyboard:
                    for i, button in enumerate(row):
                        apply_premium_to_button(button)
            elif hasattr(markup, "keyboard"):
                for row in markup.keyboard:
                    for i, button in enumerate(row):
                        apply_premium_to_button(button)

        return await make_request(bot, method)
