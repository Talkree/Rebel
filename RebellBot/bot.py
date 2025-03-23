import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from config import Config
from handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def main():
    bot = Bot(
        token=Config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь"),
    ])

    try:
        logger.info("Бот запущен")
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Получен сигнал остановки")
    finally:
        await bot.session.close()
        logger.info("Бот остановлен корректно")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)