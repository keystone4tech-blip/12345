"""Модуль для управления соответствием стандартных эмодзи и их Premium ID.

Этот модуль позволяет централизованно управлять заменой стандартных UTF-8 эмодзи
на кастомные Premium эмодзи через тег <tg-emoji> и параметр icon_custom_emoji_id.
"""

import re
import json
from typing import Any, Dict, Optional, TypeVar, Callable, Awaitable

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import SendMessage, EditMessageText, EditMessageCaption, EditMessageReplyMarkup, SendPhoto, Response
from aiogram.methods.base import TelegramMethod

from app.config import settings

T = TypeVar("T")

# Базовый список эмодзи, которые используются в боте.
# Этот список используется для отображения в админ-панели.
BASE_EMOJIS = [
    "✅", "❌", "⚠️", "➕", "🗑️", "✏️", "🔄", "🔍", "▶️", "⏸️", "⏹️",
    "🟢", "🔴", "💤", "⏰", "⏳", "🚦", "🏠", "⬅️", "➡️", "🔙", "🔝", "⏭️",
    "💰", "🔗", "🎫", "🤝", "📱", "🛠️", "📊", "🏆", "🌍", "🛟", "⚙️",
    "🎁", "🧪", "🏅", "🎲", "⚡", "🎉", "📢", "👋", "❓", "📝", "🛡️", "📦",
    "ℹ️", "🆔", "⭐", "👤", "📶", "🎨", "🚀"
]

def get_premium_emoji_map() -> Dict[str, Optional[str]]:
    """Возвращает маппинг эмодзи из настроек."""
    try:
        data = json.loads(settings.PREMIUM_EMOJIS_DATA)
        # Объединяем базовый список и кастомные данные из БД
        full_map = {e: None for e in BASE_EMOJIS}
        if isinstance(data, dict):
            full_map.update(data)
        return full_map
    except Exception:
        return {e: None for e in BASE_EMOJIS}

# Регулярное выражение для поиска любого эмодзи из базового списка
_EMOJI_PATTERN = re.compile("|".join(re.escape(e) for e in BASE_EMOJIS))


def get_premium_emoji_id(emoji: str) -> Optional[str]:
    """Возвращает ID премиум-эмодзи для заданного стандартного эмодзи."""
    emoji_map = get_premium_emoji_map()
    return emoji_map.get(emoji)


def replace_with_premium_emojis(text: str) -> str:
    """Заменяет все стандартные эмодзи в тексте на теги <tg-emoji>."""
    # print(f"DEBUG: replace_with_premium_emojis input: {text}")
    emoji_map = get_premium_emoji_map()

    def _replace(match):
        emoji = match.group(0)
        emoji_id = emoji_map.get(emoji)
        if emoji_id:
            # print(f"DEBUG: Found binding for {emoji} -> {emoji_id}")
            return f'<tg-emoji emoji-id="{emoji_id}">{emoji}</tg-emoji>'
        return emoji

    result = _EMOJI_PATTERN.sub(_replace, text)
    # if result != text:
    #     print(f"DEBUG: replace_with_premium_emojis output: {result}")
    return result


def extract_first_emoji(text: str) -> Optional[str]:
    """Извлекает первый эмодзи из строки, если он есть в нашем маппинге."""
    match = _EMOJI_PATTERN.search(text)
    if match:
        return match.group(0)
    return None


def apply_premium_to_button(button: T) -> T:
    """Применяет Premium-эмодзи к кнопке (InlineKeyboardButton или KeyboardButton)."""
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

    # Если ID уже установлен — ничего не делаем
    if getattr(button, "icon_custom_emoji_id", None):
        return button

    emoji = extract_first_emoji(text)
    if emoji:
        emoji_id = get_premium_emoji_id(emoji)
        if emoji_id:
            try:
                setattr(button, "icon_custom_emoji_id", emoji_id)
            except Exception:
                # Если объект заморожен или не поддерживает установку атрибутов
                pass

    return button


class PremiumEmojiMiddleware(BaseRequestMiddleware):
    """Middleware для автоматического применения Premium-эмодзи ко всем исходящим кнопкам."""

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType,
        bot: Bot,
        method: TelegramMethod[Response[T]],
    ) -> Response[T]:
        if not settings.USE_PREMIUM_EMOJIS:
            return await make_request(bot, method)

        # logger.debug("PremiumEmojiMiddleware: processing method", method=type(method).__name__)

        # Проверяем методы, которые могут содержать reply_markup
        if hasattr(method, "reply_markup") and method.reply_markup:
            markup = method.reply_markup
            if hasattr(markup, "inline_keyboard"):
                # Работаем с копией, чтобы не менять оригинальный объект, если он где-то кешируется
                # Но так как aiogram 3 использует Pydantic, кнопки внутри – ссылки.
                for row in markup.inline_keyboard:
                    for i, button in enumerate(row):
                        apply_premium_to_button(button)
            elif hasattr(markup, "keyboard"):
                for row in markup.keyboard:
                    for i, button in enumerate(row):
                        apply_premium_to_button(button)

        return await make_request(bot, method)
