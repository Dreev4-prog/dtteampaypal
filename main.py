import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat

from app.config import settings
from app.db import init_db
from app.handlers import router


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # Постоянная кнопка «Меню» рядом с полем ввода Telegram.
    user_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="menu", description="Открыть меню"),
        BotCommand(command="paypal", description="Запросить PayPal"),
        BotCommand(command="support", description="Поддержка"),
    ]
    await bot.set_my_commands(user_commands)

    # В личном меню каждого администратора дополнительно показываем /admin.
    admin_commands = [
        *user_commands,
        BotCommand(command="admin", description="Админ-панель"),
    ]
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:
            logging.exception("Не удалось установить меню команд для администратора %s", admin_id)

    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
