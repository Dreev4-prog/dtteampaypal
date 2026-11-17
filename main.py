import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import BotCommand, BotCommandScopeChat

from app.config import settings
from app.db import init_db
from app.handlers import router, _notify_stock_after_replenishment
from app.autopost_handlers import router as auto_post_router
from app.user_messages import router as user_message_router
from app.autoposts import seed_auto_posts, auto_post_loop
from app.stock_warmup import stock_warmup_loop
from app.miniapp import start_web_server
from app.miniapp_transport import SurfaceStorage, WebTransport


async def retry_telegram_startup(operation, label: str):
    """Retry only idempotent startup calls; never replay user/payment actions."""
    delay = 1
    failures = 0
    while True:
        try:
            result = await operation()
        except TelegramRetryAfter as exc:
            wait = max(1, exc.retry_after)
            error_name = type(exc).__name__
        except (TelegramNetworkError, TelegramServerError, TimeoutError) as exc:
            wait = delay
            delay = min(delay * 2, 30)
            error_name = type(exc).__name__
        else:
            if failures:
                logging.info("Telegram %s recovered after %s retries", label, failures)
            return result
        failures += 1
        logging.warning("Telegram %s unavailable (%s); retry in %ss", label, error_name, wait)
        await asyncio.sleep(wait)


class StartupRetryBot(Bot):
    async def me(self):
        # aiogram retries getUpdates, but its initial getMe is outside that loop.
        # Keeping this retry inside polling also preserves SIGTERM cancellation.
        return await retry_telegram_startup(super().me, "getMe")


async def configure_bot_commands(bot: Bot) -> None:
    # Постоянная кнопка «Меню» рядом с полем ввода Telegram.
    user_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="menu", description="Открыть меню"),
        BotCommand(command="paypal", description="Запросить PayPal"),
        BotCommand(command="support", description="Поддержка"),
    ]
    # В личном меню каждого администратора дополнительно показываем /admin.
    admin_commands = [
        *user_commands,
        BotCommand(command="admin", description="Админ-панель"),
        BotCommand(command="user", description="Найти пользователя по ID или @username"),
    ]
    scopes = [("default", {})]
    scopes.extend(
        (str(admin_id), {"scope": BotCommandScopeChat(chat_id=admin_id)})
        for admin_id in sorted(settings.admin_ids)
    )
    for label, kwargs in scopes:
        commands = user_commands if label == "default" else admin_commands
        try:
            await retry_telegram_startup(
                lambda: bot.set_my_commands(commands, request_timeout=20, **kwargs),
                f"setMyCommands/{label}",
            )
        except TelegramAPIError as exc:
            # Invalid/inaccessible command scopes must not stop message processing.
            logging.error("Could not configure Telegram menu %s (%s)", label, type(exc).__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await seed_auto_posts()

    bot = StartupRetryBot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    workers = []
    web_runner = None
    try:
        bot.session.middleware(WebTransport())
        dp = Dispatcher(storage=SurfaceStorage())
        dp.include_router(router)
        dp.include_router(user_message_router)
        dp.include_router(auto_post_router)
        web_runner = await start_web_server(bot, dp)
        # Updating the menu is optional and must never gate receiving updates.
        workers.append(asyncio.create_task(configure_bot_commands(bot), name="telegram-menu"))
        workers.append(asyncio.create_task(auto_post_loop(bot), name="daily-auto-posts"))
        workers.append(asyncio.create_task(
            stock_warmup_loop(bot, _notify_stock_after_replenishment), name="paypal-stock-warmup"
        ))
        await dp.start_polling(bot, close_bot_session=False)
    finally:
        if web_runner is not None:
            await web_runner.cleanup()
        for worker in workers:
            worker.cancel()
        results = await asyncio.gather(*workers, return_exceptions=True)
        for worker, result in zip(workers, results):
            if isinstance(result, Exception):
                logging.error("Background task %s failed (%s)", worker.get_name(), type(result).__name__)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
