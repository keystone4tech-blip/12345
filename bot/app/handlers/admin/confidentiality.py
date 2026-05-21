import structlog
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import User, SystemSetting
from app.database.crud.system_setting import upsert_system_setting
from app.keyboards.admin import get_admin_confidentiality_keyboard
from app.localization.texts import get_texts
from app.utils.decorators import admin_required, error_handler

logger = structlog.get_logger(__name__)

async def _get_confidentiality_state(db: AsyncSession) -> bool:
    stmt = select(SystemSetting).where(SystemSetting.key == 'bot_confidentiality')
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()
    if setting and setting.value == 'true':
        return True
    return False


@admin_required
@error_handler
async def show_confidentiality(
    callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext
):
    await state.clear()
    texts = get_texts(db_user.language)
    is_enabled = await _get_confidentiality_state(db)

    text = (
        "<b>🛡️ Настройки конфиденциальности бота</b>\n\n"
        "Эта функция позволяет включить или отключить запрет на пересылку и сохранение сообщений от бота.\n"
        "Если функция <b>включена</b>, пользователи не смогут пересылать сообщения, копировать текст или сохранять медиа.\n\n"
        f"Текущее состояние: <b>{'Включена 🟢' if is_enabled else 'Выключена 🔴'}</b>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_confidentiality_keyboard(is_enabled, db_user.language),
        parse_mode="HTML"
    )
    await callback.answer()


@admin_required
@error_handler
async def toggle_confidentiality(
    callback: types.CallbackQuery, db_user: User, db: AsyncSession, state: FSMContext
):
    is_enabled = await _get_confidentiality_state(db)
    new_state = not is_enabled
    
    await upsert_system_setting(
        db,
        key='bot_confidentiality',
        value='true' if new_state else 'false',
        description='Bot confidentiality (protect_content)'
    )
    
    # Apply to bot immediately
    callback.bot.default.protect_content = new_state
    
    await show_confidentiality(callback, db_user, db, state)


def register_handlers(dp: Dispatcher):
    dp.callback_query.register(show_confidentiality, F.data == 'admin_confidentiality')
    dp.callback_query.register(toggle_confidentiality, F.data == 'admin_confidentiality_toggle')
