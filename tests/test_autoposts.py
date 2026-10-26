"""Offline scheduling, admin CRUD and delivery tests; no live Telegram or PostgreSQL."""
import asyncio
import os
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NO_NETWORK"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1/test"
os.environ["ADMIN_IDS"] = ""

from aiogram.exceptions import TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendPhoto
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db, autoposts as posts, autopost_handlers as ui


class AutoPostTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(db.Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(db, "SessionLocal", self.sessions))
        self.stack.enter_context(patch.object(ui, "is_admin", side_effect=lambda uid: uid == 999))
        self.before = datetime(2026, 10, 26, 9, 0)
        self.now = datetime(2026, 10, 26, 10, 0, 5)  # 13:00 Moscow, not host-local time.
        self.clock = self.stack.enter_context(patch.object(posts, "utc_now", return_value=self.before))
        self.bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock())
        self.sleep = AsyncMock()
        self.state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=777, chat_id=999, user_id=999))
        async with self.sessions() as session:
            session.add_all([db.User(id=1, status="approved"), db.User(id=2, status="approved"),
                             db.User(id=3, status="blocked"), db.User(id=4, status="pending"),
                             db.AppSetting(key="work_enabled", value="1", updated_at=self.before)])
            await session.commit()

    async def asyncTearDown(self):
        self.stack.close()
        await self.engine.dispose()

    async def add(self, minute=780, photo="asset:day", **extra):
        return await posts.create_post(dict(name="Тест <пост>", body=posts.DEFAULT_BODY,
                                           photo=photo, minute=minute, **extra))

    async def work(self, value, at=None):
        async with self.sessions() as session:
            row = await session.get(db.AppSetting, "work_enabled")
            row.value, row.updated_at = str(value), at or self.before
            await session.commit()

    def message(self, text="", user_id=999, photo=None):
        return SimpleNamespace(text=text, from_user=SimpleNamespace(id=user_id), bot=self.bot,
                               photo=photo or [], answer=AsyncMock(), edit_text=AsyncMock())

    def callback(self, data, user_id=999):
        return SimpleNamespace(data=data, from_user=SimpleNamespace(id=user_id), bot=self.bot,
                               message=self.message(user_id=777), answer=AsyncMock())

    async def test_seed_uses_approved_artwork_caption_and_13_18_schedule(self):
        await posts.seed_auto_posts()
        rows = (await posts.list_posts())["rows"]
        self.assertEqual([p.minute for p in rows], [780, 1080])
        self.assertEqual([p.photo for p in rows], ["asset:day", "asset:evening"])
        self.assertEqual([p.body for p in rows], [posts.DEFAULT_BODY] * 2)
        for name in ("@profitgeld", "@workzin", "7️⃣0️⃣% от 1️⃣0️⃣0️⃣€", "6️⃣0️⃣% от 5️⃣0️⃣ €"):
            self.assertIn(name, posts.DEFAULT_BODY)
        for path in posts.BUILTIN_PHOTOS.values():
            self.assertTrue(path.is_file())
            self.assertLess(path.stat().st_size, 10 * 1024 * 1024)

    async def test_restart_seed_does_not_undo_edits_or_restore_deleted_post(self):
        await posts.seed_auto_posts()
        first, second = (await posts.list_posts())["rows"]
        first = await posts.edit_post(first.id, first.revision, "minute", 840)
        await posts.delete_post(second.id, second.revision)
        await posts.seed_auto_posts()
        data = await posts.list_posts()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["rows"][0].minute, 840)

    async def test_delivers_once_per_moscow_day_to_approved_users_with_caption_and_button(self):
        post = await self.add()
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 2)
        self.assertEqual([c.kwargs["chat_id"] for c in self.bot.send_photo.await_args_list], [1, 2])
        call = self.bot.send_photo.await_args.kwargs
        self.assertEqual(call["caption"], posts.DEFAULT_BODY)
        self.assertEqual(Path(call["photo"].path), posts.BUILTIN_PHOTOS["asset:day"])
        self.assertEqual(call["reply_markup"].inline_keyboard[0][0].callback_data, "paypal_request")
        await posts.tick(self.bot, now=self.now + timedelta(seconds=20), sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 2)
        result = await posts.last_run(post.id)
        self.assertEqual((result.status, result.sent, result.total, result.day), ("complete", 2, 2, "2026-10-26"))
        await posts.tick(self.bot, now=self.now + timedelta(days=1), sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 4)

    async def test_bundled_banner_is_uploaded_once_then_reused_without_changing_saved_image(self):
        post = await self.add()
        self.bot.send_photo.return_value = SimpleNamespace(photo=[SimpleNamespace(file_id="cached-telegram-photo")])
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        calls = self.bot.send_photo.await_args_list
        self.assertEqual(Path(calls[0].kwargs["photo"].path), posts.BUILTIN_PHOTOS["asset:day"])
        self.assertEqual(calls[1].kwargs["photo"], "cached-telegram-photo")
        self.assertEqual((await posts.get_post(post.id)).photo, "asset:day")

    async def test_stop_work_skips_without_catchup_even_when_started_in_same_minute(self):
        post = await self.add()
        await self.work(0)
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.assertEqual((await posts.last_run(post.id)).status, "skipped")
        await self.work(1, self.now)
        await posts.tick(self.bot, now=self.now + timedelta(seconds=10), sleep=self.sleep)
        self.bot.send_photo.assert_not_awaited()

    async def test_late_start_without_an_earlier_tick_does_not_catch_up(self):
        post = await self.add()
        await self.work(1, self.now - timedelta(seconds=1))
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.bot.send_photo.assert_not_awaited()
        self.assertIn("после времени", (await posts.last_run(post.id)).reason)

    async def test_no_early_or_overdue_send_and_evening_uses_moscow_time(self):
        await posts.seed_auto_posts()
        for now in (self.now - timedelta(minutes=1), self.now + timedelta(minutes=1),
                    datetime(2026, 10, 26, 13, 0)):
            await posts.tick(self.bot, now=now, sleep=self.sleep)
        self.bot.send_photo.assert_not_awaited()
        await posts.tick(self.bot, now=datetime(2026, 10, 26, 15, 0), sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 2)
        self.assertEqual(Path(self.bot.send_photo.await_args.kwargs["photo"].path), posts.BUILTIN_PHOTOS["asset:evening"])
        self.assertEqual(posts.local_slot(datetime(2026, 10, 26, 21, 0))[:2], ("2026-10-27", 0))
        self.assertEqual(posts.local_slot(datetime(2026, 10, 26, 17, 0, tzinfo=ZoneInfo("Asia/Jakarta")))[:2], ("2026-10-26", 780))

    async def test_repeat_start_preserves_session_timestamp(self):
        await self.add()
        await db.set_work_enabled(True)
        async with self.sessions() as session:
            self.assertEqual((await session.get(db.AppSetting, "work_enabled")).updated_at, self.before)
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 2)

    async def test_stop_mid_broadcast_stops_remaining_users_and_never_resumes(self):
        post = await self.add()
        async def stop(**kwargs):
            await self.work(0, self.now)
        self.bot.send_photo.side_effect = stop
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 1)
        result = await posts.last_run(post.id)
        self.assertEqual((result.status, result.sent, result.total), ("stopped", 1, 2))
        await self.work(1, self.now + timedelta(seconds=1))
        await posts.tick(self.bot, now=self.now + timedelta(seconds=10), sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 1)

    async def test_edit_disable_or_delete_mid_broadcast_stops_old_content(self):
        for action in ("edit", "disable", "delete"):
            with self.subTest(action=action):
                post = await self.add()
                run = await posts.claim_due_post(post.id, self.now)
                async def change(**kwargs):
                    if action == "delete":
                        await posts.delete_post(post.id, post.revision)
                    else:
                        await posts.edit_post(post.id, post.revision, "body" if action == "edit" else "enabled",
                                              "Другой текст" if action == "edit" else 0)
                self.bot.send_photo.reset_mock()
                self.bot.send_photo.side_effect = change
                await posts.deliver_run(self.bot, run, sleep=self.sleep)
                self.assertEqual(self.bot.send_photo.await_count, 1)
                self.assertEqual((await posts.last_run(post.id)).status, "stopped")

    async def test_recipient_blocked_after_audience_snapshot_is_not_messaged(self):
        await self.add()
        async def block(**kwargs):
            async with self.sessions() as session:
                user = await session.get(db.User, 2)
                user.status = "blocked"
                await session.commit()
        self.bot.send_photo.side_effect = block
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 1)

    async def test_network_error_is_recorded_and_not_retried(self):
        post = await self.add()
        self.bot.send_photo.side_effect = RuntimeError("network outcome unknown")
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 2)
        run = await posts.last_run(post.id)
        self.assertEqual((run.status, run.sent, run.failed), ("partial", 0, 2))

    async def test_explicit_rate_limit_is_retried_once_and_work_is_rechecked(self):
        post = await self.add()
        retry = TelegramRetryAfter(method=SendPhoto(chat_id=1, photo="test"), message="wait", retry_after=1)
        self.bot.send_photo.side_effect = [retry, None, None]
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 3)
        self.assertEqual((await posts.last_run(post.id)).sent, 2)

    async def test_stop_during_retry_delay_prevents_retry(self):
        post = await self.add()
        self.bot.send_photo.side_effect = TelegramRetryAfter(method=SendPhoto(chat_id=1, photo="test"), message="wait", retry_after=1)
        async def sleep(delay):
            if delay > 1:
                await self.work(0, self.now)
        await posts.tick(self.bot, now=self.now, sleep=sleep)
        self.assertEqual(self.bot.send_photo.await_count, 1)
        self.assertEqual((await posts.last_run(post.id)).status, "stopped")

    async def test_cancelled_broadcast_keeps_daily_claim(self):
        post = await self.add()
        self.bot.send_photo.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.assertEqual((await posts.last_run(post.id)).status, "interrupted")
        self.bot.send_photo.side_effect = None
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 1)

    async def test_editing_time_after_send_does_not_create_another_daily_send(self):
        post = await self.add()
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.clock.return_value = self.now
        await posts.edit_post(post.id, post.revision, "minute", 1080)
        await posts.tick(self.bot, now=datetime(2026, 10, 26, 15, 0), sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 2)
        await posts.tick(self.bot, now=datetime(2026, 10, 27, 15, 0), sleep=self.sleep)
        self.assertEqual(self.bot.send_photo.await_count, 4)

    async def test_disabled_and_late_enabled_post_do_not_send(self):
        post = await self.add()
        post = await posts.edit_post(post.id, post.revision, "enabled", 0)
        await posts.tick(self.bot, now=self.now, sleep=self.sleep)
        self.assertIsNone(await posts.last_run(post.id))
        self.clock.return_value = self.now
        await posts.edit_post(post.id, post.revision, "enabled", 1)
        await posts.tick(self.bot, now=self.now + timedelta(seconds=10), sleep=self.sleep)
        self.bot.send_photo.assert_not_awaited()
        self.assertEqual((await posts.last_run(post.id)).status, "skipped")

    async def test_create_is_idempotent_and_stale_changes_are_rejected(self):
        draft = dict(name="Один", body="текст", minute=780, photo="")
        one = await posts.create_post(draft, "same-draft")
        two = await posts.create_post(draft, "same-draft")
        self.assertEqual(one.id, two.id)
        changed = await posts.edit_post(one.id, one.revision, "minute", 840)
        self.assertIsNone(await posts.edit_post(one.id, one.revision, "body", "устаревший"))
        self.assertFalse(await posts.delete_post(one.id, one.revision))
        self.assertEqual((await posts.get_post(one.id)).minute, 840)
        self.assertTrue(await posts.delete_post(one.id, changed.revision))
        self.assertIsNone(await posts.get_post(one.id))

    async def test_plain_text_is_escaped_and_caption_limits_count_emoji(self):
        self.assertEqual(posts.validate_field("body", "😀" * 512), "😀" * 512)
        with self.assertRaises(ValueError):
            posts.validate_field("body", "😀" * 513)
        for value in ("24:00", "13:60", "13 00", "-1:00", "x"):
            with self.assertRaises(ValueError):
                posts.parse_time(value)
        self.assertEqual(posts.parse_time(" 18:00 "), 1080)
        post = await posts.create_post(dict(name="HTML", body="<b>буквально</b> & текст", minute=780, photo=""))
        await posts.send_post(self.bot, 999, post)
        self.assertIn("&lt;b&gt;буквально&lt;/b&gt; &amp; текст", self.bot.send_message.await_args.kwargs["text"])

    async def test_all_105_posts_are_reachable_and_stale_page_clamps(self):
        async with self.sessions() as session:
            session.add_all(db.AutoPost(name=f"Post {i}", creation_key=f"key{i}", body="x", photo="", minute=i)
                            for i in range(105))
            await session.commit()
        ids = []
        for page in range(11):
            data = await posts.list_posts(page)
            self.assertEqual(data["total"], 105)
            ids.extend(p.id for p in data["rows"])
        self.assertEqual(len(set(ids)), 105)
        self.assertEqual((await posts.list_posts(999))["page"], 10)

    async def test_admin_wizard_without_photo_previews_only_admin_and_saves_once(self):
        await ui.auto_post_callback(self.callback("ap:new"), self.state)
        for value in ("Новый пост", "13:30", posts.DEFAULT_BODY):
            await ui.auto_post_value(self.message(value), self.state)
        callback = self.callback("ap:nophoto")  # callback.message.from_user is the BOT, not the admin.
        await ui.auto_post_callback(callback, self.state)
        self.bot.send_message.assert_awaited_once()
        self.assertEqual(self.bot.send_message.await_args.kwargs["chat_id"], 999)
        self.assertEqual((await posts.list_posts())["total"], 0)
        await ui.auto_post_callback(self.callback("ap:save"), self.state)
        await ui.auto_post_callback(self.callback("ap:save"), self.state)
        data = await posts.list_posts()
        self.assertEqual(data["total"], 1)
        self.assertEqual((data["rows"][0].minute, data["rows"][0].body, data["rows"][0].photo), (810, posts.DEFAULT_BODY, ""))

    async def test_admin_wizard_with_photo_and_cancel(self):
        await ui.auto_post_callback(self.callback("ap:new"), self.state)
        for value in ("Фото", "18:00", "подпись"):
            await ui.auto_post_value(self.message(value), self.state)
        await ui.auto_post_value(self.message(photo=[SimpleNamespace(file_id="telegram-photo-id")]), self.state)
        call = self.bot.send_photo.await_args.kwargs
        self.assertEqual((call["chat_id"], call["photo"], call["caption"]), (999, "telegram-photo-id", "подпись"))
        await ui.auto_post_callback(self.callback("ap:list:0"), self.state)
        await ui.auto_post_callback(self.callback("ap:save"), self.state)
        self.assertEqual((await posts.list_posts())["total"], 0)

    async def test_admin_time_edit_validation_and_private_preview_during_stop_work(self):
        post = await self.add()
        await self.work(0)
        await ui.auto_post_callback(self.callback(f"ap:preview:{post.id}:{post.revision}:0"), self.state)
        self.assertEqual(self.bot.send_photo.await_args.kwargs["chat_id"], 999)
        self.assertIsNone(await posts.last_run(post.id))
        await ui.auto_post_callback(self.callback(f"ap:edit:{post.id}:{post.revision}:minute:0"), self.state)
        await ui.auto_post_value(self.message("25:10"), self.state)
        self.assertEqual((await posts.get_post(post.id)).minute, 780)
        await ui.auto_post_value(self.message("19:15"), self.state)
        self.assertEqual((await posts.get_post(post.id)).minute, 1155)
        self.assertIsNone(await self.state.get_state())

    async def test_admin_delete_requires_confirmation_and_stale_button_cannot_delete_updated_post(self):
        post = await self.add()
        ask = self.callback(f"ap:delete:{post.id}:{post.revision}:0")
        await ui.auto_post_callback(ask, self.state)
        self.assertIsNotNone(await posts.get_post(post.id))
        self.assertIn("Удалить", ask.message.edit_text.await_args.args[0])
        changed = await posts.edit_post(post.id, post.revision, "name", "Новое название")
        await ui.auto_post_callback(self.callback(f"ap:remove:{post.id}:{post.revision}:0"), self.state)
        self.assertIsNotNone(await posts.get_post(post.id))
        await ui.auto_post_callback(self.callback(f"ap:remove:{post.id}:{changed.revision}:0"), self.state)
        self.assertIsNone(await posts.get_post(post.id))

    async def test_non_admin_and_malformed_callbacks_cannot_mutate_or_broadcast(self):
        post = await self.add()
        for data in ("ap:new", "ap:save", "ap:list:0", f"ap:preview:{post.id}:1:0", f"ap:remove:{post.id}:1:0"):
            callback = self.callback(data, user_id=1)
            await ui.auto_post_callback(callback, self.state)
            callback.answer.assert_awaited_once_with("Нет доступа", show_alert=True)
        for data in ("ap:", "ap:edit:x", "ap:toggle:bad:1:0", "ap:unknown:1:1:0"):
            await ui.auto_post_callback(self.callback(data), self.state)
        self.bot.send_photo.assert_not_awaited()
        self.assertEqual((await posts.list_posts())["total"], 1)

    async def test_scheduler_keeps_noticing_slots_while_previous_delivery_is_slow(self):
        started, cancelled = [], []
        second_started = asyncio.Event()
        blocker = asyncio.Event()
        async def deliver(bot, run, **kwargs):
            started.append(run)
            if len(started) == 2:
                second_started.set()
            try:
                await blocker.wait()
            finally:
                cancelled.append(run)
        calls = 0
        async def claim():
            nonlocal calls
            calls += 1
            return [calls] if calls <= 2 else []
        async def fast_sleep(seconds):
            await asyncio.sleep(0)
        fake_asyncio = SimpleNamespace(Lock=asyncio.Lock, create_task=asyncio.create_task,
                                       sleep=fast_sleep, CancelledError=asyncio.CancelledError, gather=asyncio.gather)
        with patch.object(posts, "asyncio", fake_asyncio), patch.object(posts, "claim_due_runs", claim), patch.object(posts, "deliver_with_timeout", deliver):
            worker = asyncio.create_task(posts.auto_post_loop(self.bot))
            await asyncio.wait_for(second_started.wait(), timeout=1)
            self.assertEqual(started, [1, 2])
            worker.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await worker
            self.assertEqual(sorted(cancelled), [1, 2])


if __name__ == "__main__":
    unittest.main()
