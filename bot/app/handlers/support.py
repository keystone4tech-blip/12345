import structlog
from aiogram import Dispatcher, F, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.keyboards.inline import get_support_keyboard
from app.localization.texts import get_texts
from app.services.support_settings_service import SupportSettingsService
from app.utils.photo_message import edit_or_answer_photo


logger = structlog.get_logger(__name__)


async def show_support_info(callback: types.CallbackQuery, db_user: User, db: AsyncSession = None):
    await edit_or_answer_photo(
        callback=callback,
        caption=SupportSettingsService.get_support_info_text(db_user.language),
        keyboard=get_support_keyboard(db_user.language),
        parse_mode='HTML',
    )
    await callback.answer()


async def _handle_support_command(message: types.Message, db_user: User, db: AsyncSession = None):
    """Обработчик текстовой команды /support"""
    from app.handlers.menu import DummyCallbackQuery, delayed_delete
    import asyncio
    
    # Удаляем команду пользователя для чистоты чата
    asyncio.create_task(delayed_delete(message))
    
    # Имитируем колбэк для совместимости с edit_or_answer_photo
    pseudo_callback = DummyCallbackQuery(
        id=str(message.message_id),
        from_user=message.from_user,
        chat_instance="chat",
        message=message,
        data='menu_support'
    )
    if hasattr(message, 'bot') and message.bot:
        pseudo_callback = pseudo_callback.as_(message.bot)

    await edit_or_answer_photo(
        callback=pseudo_callback,
        caption=SupportSettingsService.get_support_info_text(db_user.language),
        keyboard=get_support_keyboard(db_user.language),
        parse_mode='HTML',
    )




def register_handlers(dp: Dispatcher):
    dp.callback_query.register(show_support_info, F.data == 'menu_support')
    dp.message.register(_handle_support_command, Command("support"))
