import structlog
from aiogram import Router, F, types

from app.database.models import User
from app.keyboards.admin import get_admin_traffic_help_keyboard
from app.localization.texts import get_texts
from app.services.traffic_help_service import traffic_help_service

logger = structlog.get_logger(__name__)
router = Router(name='admin_traffic_help')

@router.callback_query(F.data == 'admin_traffic_help')
async def handle_admin_traffic_help_main(callback: types.CallbackQuery, db_user: User):
    """Главное меню помощи по трафику."""
    texts = get_texts(db_user.language)
    
    status_text = "Включена" if traffic_help_service.is_enabled() else "Отключена"
    running_text = "Работает" if traffic_help_service.is_running() else "Остановлен"

    text = (
        "🔧 <b>Помощь с настройкой (отсутствие трафика)</b>\n\n"
        f"Статус системы: <b>{status_text}</b>\n"
        f"Фоновый процесс: <b>{running_text}</b>\n\n"
        "Эта система автоматически находит пользователей с активной подпиской, "
        "которые не потратили трафик за отведенное время, и отправляет им "
        "сообщение с предложением помощи."
    )
    
    markup = get_admin_traffic_help_keyboard(language=db_user.language)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data == 'admin_traffic_help_test')
async def handle_admin_traffic_help_test(callback: types.CallbackQuery, db_user: User):
    """Отправить тестовое сообщение себе."""
    if not traffic_help_service.bot:
        traffic_help_service.set_bot(callback.bot)
        
    await traffic_help_service._send_single_request(db_user)
    await callback.answer('✅ Тестовое сообщение отправлено!', show_alert=True)

@router.callback_query(F.data == 'admin_traffic_help_trigger')
async def handle_admin_traffic_help_trigger(callback: types.CallbackQuery, db_user: User):
    """Принудительный запуск рассылки."""
    if not traffic_help_service.bot:
        traffic_help_service.set_bot(callback.bot)
        
    import asyncio
    
    # Run the background task without awaiting here so the callback responds quickly
    asyncio.create_task(traffic_help_service.run_manual())
    await callback.answer('🚀 Рассылка запущена в фоновом режиме', show_alert=True)

def register_handlers(dp: Router):
    dp.include_router(router)