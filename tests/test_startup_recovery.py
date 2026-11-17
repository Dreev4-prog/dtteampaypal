"""Offline regressions for Telegram outages during startup and menu setup."""
import asyncio
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NO_NETWORK"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1/test"
os.environ["ADMIN_IDS"] = ""

from aiogram import Dispatcher
from aiogram.exceptions import (
    TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter,
    TelegramServerError, TelegramUnauthorizedError,
)
from aiogram.methods import GetMe
from aiogram.types import User

import main as app_main


def unavailable(kind=TelegramServerError):
    return kind(method=GetMe(), message="Bad Gateway")


class StartupRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_errors_retry_then_return_result(self):
        operation = AsyncMock(side_effect=[
            unavailable(), unavailable(TelegramNetworkError), TimeoutError(), "ready",
        ])
        with patch.object(app_main.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            result = await app_main.retry_telegram_startup(operation, "test")
        self.assertEqual(result, "ready")
        self.assertEqual([c.args[0] for c in sleep.await_args_list], [1, 2, 4])

    async def test_long_outage_does_not_exhaust_restart_budget(self):
        operation = AsyncMock(side_effect=[unavailable() for _ in range(15)] + [True])
        with patch.object(app_main.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            self.assertTrue(await app_main.retry_telegram_startup(operation, "test"))
        delays = [c.args[0] for c in sleep.await_args_list]
        self.assertEqual(delays[:6], [1, 2, 4, 8, 16, 30])
        self.assertEqual(delays[6:], [30] * 9)

    async def test_telegram_retry_after_is_respected(self):
        rate_limit = TelegramRetryAfter(method=GetMe(), message="slow down", retry_after=47)
        with patch.object(app_main.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            await app_main.retry_telegram_startup(AsyncMock(side_effect=[rate_limit, True]), "test")
        sleep.assert_awaited_once_with(47)

    async def test_invalid_token_is_not_hidden_by_retry(self):
        operation = AsyncMock(side_effect=unavailable(TelegramUnauthorizedError))
        with patch.object(app_main.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            with self.assertRaises(TelegramUnauthorizedError):
                await app_main.retry_telegram_startup(operation, "test")
        operation.assert_awaited_once()
        sleep.assert_not_awaited()

    async def test_programming_error_is_not_retried(self):
        operation = AsyncMock(side_effect=ValueError("bad input"))
        with self.assertRaises(ValueError):
            await app_main.retry_telegram_startup(operation, "test")
        operation.assert_awaited_once()

    async def test_cancellation_interrupts_backoff(self):
        entered = asyncio.Event()

        async def sleep(_):
            entered.set()
            await asyncio.Event().wait()

        with patch.object(app_main.asyncio, "sleep", side_effect=sleep):
            task = asyncio.create_task(app_main.retry_telegram_startup(
                AsyncMock(side_effect=unavailable()), "test"))
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_get_me_recovers_and_keeps_aiogram_cache(self):
        bot = app_main.StartupRetryBot(os.environ["BOT_TOKEN"])
        user = User(id=123456, is_bot=True, first_name="Offline", username="offline_bot")
        try:
            with patch.object(bot, "get_me", new_callable=AsyncMock) as get_me:
                get_me.side_effect = [unavailable(), user]
                with patch.object(app_main.asyncio, "sleep", new_callable=AsyncMock):
                    self.assertEqual(await bot.me(), user)
                    self.assertEqual(await bot.me(), user)
                self.assertEqual(get_me.await_count, 2)
        finally:
            await bot.session.close()

    async def test_real_dispatcher_reaches_polling_after_failed_get_me(self):
        bot = app_main.StartupRetryBot(os.environ["BOT_TOKEN"])
        dp = Dispatcher()
        listening = asyncio.Event()
        user = User(id=123456, is_bot=True, first_name="Offline")

        async def listen(*args, **kwargs):
            listening.set()
            await asyncio.Event().wait()
            yield  # An async generator matching aiogram's updates iterator.

        try:
            with patch.object(bot, "get_me", new_callable=AsyncMock) as get_me, \
                 patch.object(dp, "_listen_updates", side_effect=listen), \
                 patch.object(app_main.asyncio, "sleep", new_callable=AsyncMock):
                get_me.side_effect = [unavailable(), user]
                task = asyncio.create_task(dp.start_polling(
                    bot, handle_signals=False, close_bot_session=False))
                try:
                    await asyncio.wait_for(listening.wait(), 1)
                    self.assertFalse(task.done())
                    await dp.stop_polling()
                    await asyncio.wait_for(task, 1)
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        finally:
            await bot.session.close()

    async def test_bad_command_scope_does_not_skip_other_admins(self):
        bot = SimpleNamespace(set_my_commands=AsyncMock(side_effect=[
            TelegramBadRequest(method=GetMe(), message="chat not found"), True, True,
        ]))
        with patch.object(app_main, "settings", SimpleNamespace(admin_ids={22, 11})):
            await app_main.configure_bot_commands(bot)
        calls = bot.set_my_commands.await_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual([c.kwargs["scope"].chat_id for c in calls[1:]], [11, 22])

    async def test_real_dispatcher_stops_while_initial_get_me_is_retrying(self):
        bot = app_main.StartupRetryBot(os.environ["BOT_TOKEN"])
        dp = Dispatcher()
        retrying = asyncio.Event()

        async def sleep(_):
            retrying.set()
            await asyncio.Event().wait()

        try:
            with patch.object(bot, "get_me", new_callable=AsyncMock, side_effect=unavailable()), \
                 patch.object(app_main.asyncio, "sleep", side_effect=sleep):
                task = asyncio.create_task(dp.start_polling(
                    bot, handle_signals=False, close_bot_session=False))
                try:
                    await asyncio.wait_for(retrying.wait(), 1)
                    await asyncio.wait_for(dp.stop_polling(), 1)
                    await asyncio.wait_for(task, 1)
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        finally:
            await bot.session.close()

    async def test_menu_outage_does_not_block_polling_and_cleanup_runs(self):
        menu_started = asyncio.Event()
        menu_cancelled = asyncio.Event()
        other_cancelled = set()

        async def menu(bot):
            menu_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                menu_cancelled.set()

        async def worker(name):
            try:
                await asyncio.Event().wait()
            finally:
                other_cancelled.add(name)

        async def poll(*args, **kwargs):
            await asyncio.wait_for(menu_started.wait(), 1)
            self.assertFalse(menu_cancelled.is_set())

        bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock(), middleware=Mock()))
        dispatcher = SimpleNamespace(include_router=Mock(), start_polling=AsyncMock(side_effect=poll))
        with ExitStack() as stack:
            stack.enter_context(patch.object(app_main, "init_db", new_callable=AsyncMock))
            stack.enter_context(patch.object(app_main, "seed_auto_posts", new_callable=AsyncMock))
            stack.enter_context(patch.object(app_main, "StartupRetryBot", return_value=bot))
            stack.enter_context(patch.object(app_main, "Dispatcher", return_value=dispatcher))
            stack.enter_context(patch.object(app_main, "start_web_server", new=AsyncMock(return_value=SimpleNamespace(cleanup=AsyncMock()))))
            stack.enter_context(patch.object(app_main, "configure_bot_commands", side_effect=menu))
            stack.enter_context(patch.object(app_main, "auto_post_loop", new=lambda _: worker("posts")))
            stack.enter_context(patch.object(app_main, "stock_warmup_loop", new=lambda *_: worker("stock")))
            await app_main.main()
        self.assertTrue(menu_cancelled.is_set())
        self.assertEqual(other_cancelled, {"posts", "stock"})
        dispatcher.start_polling.assert_awaited_once_with(bot, close_bot_session=False)
        bot.session.close.assert_awaited_once()

    async def test_session_closes_when_polling_startup_fails(self):
        bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock(), middleware=Mock()))
        dispatcher = SimpleNamespace(include_router=Mock(), start_polling=AsyncMock(
            side_effect=unavailable(TelegramUnauthorizedError)))
        with ExitStack() as stack:
            for name in ("init_db", "seed_auto_posts", "configure_bot_commands", "auto_post_loop", "stock_warmup_loop"):
                stack.enter_context(patch.object(app_main, name, new_callable=AsyncMock))
            stack.enter_context(patch.object(app_main, "StartupRetryBot", return_value=bot))
            stack.enter_context(patch.object(app_main, "Dispatcher", return_value=dispatcher))
            stack.enter_context(patch.object(app_main, "start_web_server", new=AsyncMock(return_value=SimpleNamespace(cleanup=AsyncMock()))))
            with self.assertRaises(TelegramUnauthorizedError):
                await app_main.main()
        bot.session.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
