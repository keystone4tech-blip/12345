from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault
import logging

logger = logging.getLogger(__name__)

async def set_bot_commands(bot: Bot):
    try:
        commands = [
            BotCommand(command="start", description="🏠 Главное меню / Main menu"),
            BotCommand(command="support", description="🛠 Техподдержка / Support"),
        ]
        # Регистрация стандартных команд
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        
        # Регистрация команд специально для русского языка
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault(), language_code="ru")
        
        logger.info("✅ Команды бота успешно зарегистрированы в Telegram")
        print("✅ Команды бота успешно зарегистрированы в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка при регистрации команд: {e}")
        print(f"❌ Ошибка при регистрации команд: {e}")
