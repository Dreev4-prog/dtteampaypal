import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat

from app.config import settings
from app.db import init_db
from app.handlers import router
from app.autopost_handlers import router as auto_post_router
from app.autoposts import seed_auto_posts, auto_post_loop


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await seed_auto_posts()

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
    dp.include_router(auto_post_router)
    worker = asyncio.create_task(auto_post_loop(bot), name="daily-auto-posts")
    try:
        await dp.start_polling(bot, close_bot_session=False)
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
