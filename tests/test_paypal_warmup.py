"""24-hour stock availability using a real local DB and mocked Telegram only."""
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from test_paypal_restore import RestoreScreen
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db, handlers, keyboards, stock_warmup


class PayPalWarmupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.url = 'sqlite+aiosqlite:///' + str(Path(self.temp.name) / 'warmup.db')
        self.engine = create_async_engine(self.url)
        async with self.engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.now = datetime(2026, 11, 2, 20, 30, 15)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(db, 'SessionLocal', self.sessions))
        self.stack.enter_context(patch.object(db, 'paypal_stock_now', side_effect=lambda: self.now))
        self.stack.enter_context(patch.object(handlers, 'is_admin', side_effect=lambda uid: uid == 999))
        self.storage = MemoryStorage()
        self.state = FSMContext(self.storage, StorageKey(bot_id=1, chat_id=999, user_id=999))
        async with self.sessions() as session:
            session.add_all([db.User(id=1, status='approved'), db.User(id=2, status='approved')])
            await session.commit()

    async def asyncTearDown(self):
        await self.storage.close()
        self.stack.close()
        await self.engine.dispose()
        self.temp.cleanup()

    def message(self, value='@Example', uid=999):
        return SimpleNamespace(text=value, from_user=SimpleNamespace(id=uid),
            answer=AsyncMock(), answer_photo=AsyncMock(),
            photo=[SimpleNamespace(file_id='PHOTO')],
            bot=SimpleNamespace(send_message=AsyncMock()))

    def callback(self, value, uid=999):
        message = self.message(uid=uid)
        return SimpleNamespace(data=value, from_user=message.from_user, message=message,
                               bot=message.bot, answer=AsyncMock())

    async def all_tags(self):
        async with self.sessions() as session:
            return list(await session.scalars(select(db.PaypalTag).order_by(db.PaypalTag.id)))

    async def test_exact_deadline_gates_all_stock_counts_and_authoritative_issuance(self):
        tag, duplicate = await db.add_paypal_tag('@Delayed', 'PHOTO', 'female', delay_hours=24)
        self.assertFalse(duplicate)
        self.assertEqual(tag.available_from, self.now + timedelta(hours=24))
        self.assertEqual(tag.available_from - tag.created_at, timedelta(hours=24))
        self.assertEqual(tag.photo_file_id, 'PHOTO')
        deadline = tag.available_from
        for moment in (self.now, deadline - timedelta(microseconds=1)):
            self.now = moment
            self.assertEqual(await db.count_available_tags(), 0)
            self.assertEqual((await db.get_requestable_paypal_gender_counts())['total'], 0)
            self.assertEqual((await db.get_paypal_gender_counts())['total'], 0)
            self.assertEqual((await db.get_paypal_database_counts())['warming'], 1)
            self.assertEqual(await db.list_paypal_tags('available'), [])
            self.assertEqual((await db.get_dashboard_summary())['available'], 0)
        req = await db.create_request(1, 100, paypal_gender='female')
        self.assertIsNone((await db.issue_paypal(req.id))[1])
        self.assertEqual((await db.get_request(req.id)).status, 'waiting_issue')
        self.now = deadline
        self.assertEqual(await db.count_available_tags(), 1)
        self.assertEqual((await db.get_paypal_database_counts())['warming'], 0)
        self.assertEqual((await db.get_paypal_gender_counts())['female'], 1)
        self.assertEqual((await db.get_warming_paypal_page())['total'], 0)
        issued, actual = await db.issue_paypal(req.id)
        self.assertEqual(actual.id, tag.id)
        self.assertEqual(issued.status, 'paypal_issued')

    async def test_immediate_and_legacy_stock_stay_available_and_duplicates_keep_deadlines(self):
        immediate, _ = await db.add_paypal_tag('@Immediate')
        delayed, _ = await db.add_paypal_tag('@Delayed', delay_hours=24)
        self.now += timedelta(hours=2)
        duplicate, exists = await db.add_paypal_tag('@Delayed', delay_hours=0)
        self.assertTrue(exists)
        self.assertEqual(duplicate.available_from, delayed.available_from)
        unchanged, exists = await db.add_paypal_tag('@Immediate', delay_hours=24)
        self.assertTrue(exists)
        self.assertIsNone(unchanged.available_from)
        self.assertIsNone(immediate.available_from)
        self.assertEqual(await db.count_available_tags(), 1)
        counts = await db.get_paypal_database_counts()
        self.assertEqual((counts['available'], counts['warming'], counts['all']), (1, 1, 2))

    async def test_pending_reservations_and_personal_exclusions_still_apply(self):
        ready, _ = await db.add_paypal_tag('@Ready')
        await db.add_paypal_tag('@Warming', delay_hours=24)
        async with self.sessions() as session:
            session.add(db.UserPaypalExclusion(user_id=1, paypal_tag_id=ready.id))
            await session.commit()
        self.assertEqual((await db.get_requestable_paypal_gender_counts(1))['male'], 0)
        self.assertEqual((await db.get_requestable_paypal_gender_counts(2))['male'], 1)
        req = await db.create_request(1, 100)
        self.assertIsNone((await db.issue_paypal(req.id))[1])
        self.assertEqual((await db.get_requestable_paypal_gender_counts(2))['male'], 0)

    async def test_bulk_200_is_fully_paginated_and_no_deadline_reset_on_duplicate(self):
        tags = [f'@Bulk{i:03}' for i in range(200)]
        self.assertEqual(await db.add_paypal_tags(tags, 'female', delay_hours=24), (200, 0))
        deadline = self.now + timedelta(hours=24)
        self.now += timedelta(hours=3)
        self.assertEqual(await db.add_paypal_tags(tags, delay_hours=0), (0, 200))
        seen = []
        offset = 0
        while True:
            page = await db.get_warming_paypal_page(offset)
            self.assertEqual(page['total'], 200)
            self.assertLessEqual(len(page['rows']), 15)
            for tag in page['rows']:
                seen.append(tag.tag)
                self.assertEqual(tag.available_from, deadline)
                self.assertEqual(tag.gender, 'female')
            if not page['has_next']:
                break
            offset += page['page_size']
        self.assertEqual(seen, tags)
        self.assertEqual((await db.get_warming_paypal_page(9999))['offset'], 195)
        screen = RestoreScreen()
        await handlers.paypal_db_list_handler(screen.callback('paypal_db_list:warming:195'))
        caption, menu = screen.delivered[-1]
        self.assertIn('200', caption)
        self.assertIn('196–200', caption)
        for row in menu.inline_keyboard:
            for button in row:
                self.assertLessEqual(len(button.callback_data.encode()), 64)

    async def test_restart_preserves_deadline_and_requires_no_release_worker(self):
        tag, _ = await db.add_paypal_tag('@SurviveRestart', delay_hours=24)
        await self.engine.dispose()
        restarted = create_async_engine(self.url)
        try:
            sessions = async_sessionmaker(restarted, expire_on_commit=False)
            with patch.object(db, 'SessionLocal', sessions):
                async with restarted.begin() as conn:
                    await db._migrate_paypal_warmup(conn)
                    await db._migrate_paypal_warmup(conn)
                self.now += timedelta(hours=25)
                restored = await db.get_paypal_tag(tag.id)
                self.assertEqual(restored.available_from, tag.available_from)
                self.assertIsNone(restored.stock_announced_at)
                self.assertEqual(await db.count_available_tags(), 1)
                req = await db.create_request(1, 100)
                self.assertEqual((await db.issue_paypal(req.id))[1].id, tag.id)
        finally:
            await restarted.dispose()

    async def test_delete_restore_and_status_change_cannot_bypass_warmup(self):
        tag, _ = await db.add_paypal_tag('@Restore', delay_hours=24)
        self.assertEqual(await db.delete_free_paypal_tag(tag.id), (True, 'deleted'))
        req, actual, reason = await db.restore_deleted_paypal_to_work(tag.id, 999)
        self.assertIsNone(req)
        self.assertEqual(reason, 'warming')
        restored, _ = await db.restore_deleted_paypal_tag(tag.id)
        self.assertEqual(restored.available_from, tag.available_from)
        await db.set_paypal_tag_status(tag.id, 'gestoppt')
        await db.set_paypal_tag_status(tag.id, 'available')
        changed, reason = await db.set_paypal_tag_gender(tag.id, 'female')
        self.assertEqual(reason, 'updated')
        self.assertEqual(changed.available_from, tag.available_from)
        self.assertEqual(await db.count_available_tags(), 0)
        self.assertEqual((await db.get_warming_paypal_page())['total'], 1)

    async def test_deleted_and_gestop_stock_do_not_reappear_at_deadline(self):
        deleted, _ = await db.add_paypal_tag('@Deleted', delay_hours=24)
        gestop, _ = await db.add_paypal_tag('@Gestop', delay_hours=24)
        await db.delete_free_paypal_tag(deleted.id)
        await db.set_paypal_tag_status(gestop.id, 'gestoppt')
        self.now += timedelta(days=2)
        self.assertEqual(await db.claim_matured_paypal_stock(), set())
        self.assertEqual(await db.count_available_tags(), 0)
        self.assertEqual((await db.get_paypal_tag(deleted.id)).status, 'deleted')
        self.assertEqual((await db.get_paypal_tag(gestop.id)).status, 'gestoppt')

    async def test_subscribers_not_notified_early_then_once_after_maturity(self):
        await db.add_paypal_tag('@Delayed', delay_hours=24)
        await db.subscribe_paypal_stock_waitlist(1, 'male')
        bot = SimpleNamespace(send_message=AsyncMock())
        await stock_warmup.announce_matured_stock(bot, handlers._notify_stock_after_replenishment)
        bot.send_message.assert_not_awaited()
        self.now += timedelta(hours=24)
        await stock_warmup.announce_matured_stock(bot, handlers._notify_stock_after_replenishment)
        bot.send_message.assert_awaited_once()
        self.assertEqual(await db.list_paypal_stock_waiters('male'), [])
        await stock_warmup.announce_matured_stock(bot, handlers._notify_stock_after_replenishment)
        bot.send_message.assert_awaited_once()
        self.assertEqual(await db.count_available_tags(), 1)

    async def test_notice_failure_does_not_block_or_reset_ready_stock(self):
        tag, _ = await db.add_paypal_tag('@ReadyDespiteFailure', delay_hours=24)
        self.now += timedelta(hours=24)
        with self.assertRaises(RuntimeError):
            await stock_warmup.announce_matured_stock(None, AsyncMock(side_effect=RuntimeError('offline')))
        self.assertEqual(await db.count_available_tags(), 1)
        self.assertEqual(await db.claim_matured_paypal_stock(), set())
        self.assertEqual((await db.get_paypal_tag(tag.id)).available_from, tag.available_from)

    async def test_single_form_keeps_mode_gender_and_photo_when_reentering(self):
        await handlers.paypal_add_single_start(self.callback('paypal_add_single'), self.state)
        self.assertEqual(await self.state.get_state(), handlers.PaypalAddForm.timing.state)
        await handlers.paypal_add_timing_choice(self.callback('paypal_add_timing:24'), self.state)
        await handlers.paypal_add_gender_choice(self.callback('paypal_add_gender:female'), self.state)
        await handlers.paypal_add_tag_input(self.message('@First'), self.state)
        await handlers.paypal_add_restart(self.callback('paypal_add_restart'), self.state)
        await handlers.paypal_add_tag_input(self.message('@Final'), self.state)
        photo = self.message()
        await handlers.paypal_add_photo_input(photo, self.state)
        self.assertIn('24 часа', photo.answer_photo.await_args.kwargs['caption'])
        with patch.object(handlers, '_notify_stock_after_replenishment', new_callable=AsyncMock) as notify:
            callback = self.callback('paypal_add_save')
            await handlers.paypal_add_save(callback, self.state)
            notify.assert_not_awaited()
        tags = await self.all_tags()
        self.assertEqual(len(tags), 1)
        self.assertEqual((tags[0].tag, tags[0].gender, tags[0].photo_file_id), ('@Final', 'female', 'PHOTO'))
        self.assertEqual(tags[0].available_from, self.now + timedelta(hours=24))
        self.assertIn('03.11.2026 23:30 МСК', callback.message.answer.await_args.args[0])
        self.assertIsNone(await self.state.get_state())

    async def test_bulk_form_and_immediate_form_keep_notification_behavior(self):
        with patch.object(handlers, '_notify_stock_after_replenishment', AsyncMock(return_value=0)) as notify:
            for delay in (24, 0):
                await handlers.paypal_add_bulk_start(self.callback('paypal_add_bulk'), self.state)
                await handlers.paypal_add_timing_choice(self.callback(f'paypal_add_timing:{delay}'), self.state)
                await handlers.paypal_bulk_gender_choice(self.callback('paypal_bulk_gender:male'), self.state)
                message = self.message(f'@Batch{delay}a\n@Batch{delay}b\n@Batch{delay}a')
                await handlers.paypal_add_bulk_input(message, self.state)
                self.assertIn('Добавлено: <b>2</b>', message.answer.await_args.args[0])
                if delay == 24:
                    notify.assert_not_awaited()
            notify.assert_awaited_once()
        self.assertEqual(len(await self.all_tags()), 4)
        self.assertEqual(await db.count_available_tags(), 2)

    async def test_admin_card_delete_restore_and_gender_edit_keep_deadline_visible(self):
        tag, _ = await db.add_paypal_tag('@Card', delay_hours=24)
        screen = RestoreScreen(photo=False)
        await handlers.paypal_card_admin_handler(screen.callback(f'paypal_card:{tag.id}:warming'))
        caption, markup = screen.delivered[-1]
        self.assertIn('На выдержке', caption)
        self.assertIn('03.11.2026 23:30 МСК', caption)
        self.assertFalse(any(b.callback_data.startswith('paypal_mark_available') for row in markup.inline_keyboard for b in row))
        await handlers.paypal_gender_set_handler(screen.callback(f'paypal_gender_set:{tag.id}:female:warming'))
        caption, markup = screen.delivered[-1]
        self.assertIn('На выдержке до', caption)
        self.assertFalse(any(b.callback_data.startswith('paypal_mark_available') for row in markup.inline_keyboard for b in row))
        await handlers.paypal_delete_ask_handler(screen.callback(f'paypal_delete_ask:{tag.id}:warming'))
        await handlers.paypal_delete_confirm_handler(screen.callback(f'paypal_delete_confirm:{tag.id}:warming'))
        self.assertEqual((await db.get_paypal_tag(tag.id)).status, 'deleted')
        await handlers.paypal_restore_confirm_handler(screen.callback(f'paypal_restore_confirm:{tag.id}'))
        self.assertIn('На выдержке до', screen.delivered[-1][0])
        self.assertEqual(await db.count_available_tags(), 0)

    async def test_immediate_single_and_legacy_addtags_command_are_still_immediate(self):
        with patch.object(handlers, '_notify_stock_after_replenishment', AsyncMock(return_value=0)) as notify:
            await handlers.paypal_add_single_start(self.callback('paypal_add_single'), self.state)
            await handlers.paypal_add_timing_choice(self.callback('paypal_add_timing:0'), self.state)
            await handlers.paypal_add_gender_choice(self.callback('paypal_add_gender:male'), self.state)
            await handlers.paypal_add_tag_input(self.message('@SingleNow'), self.state)
            await handlers.paypal_add_skip_photo(self.callback('paypal_add_skip_photo'), self.state)
            callback = self.callback('paypal_add_save')
            await handlers.paypal_add_save(callback, self.state)
            self.assertIn('добавлен в свободную базу', callback.message.answer.await_args.args[0])
            await handlers.add_tags_handler(self.message('/addtags @CommandNow'))
            self.assertEqual(notify.await_count, 2)
        self.assertEqual(await db.count_available_tags(), 2)
        self.assertTrue(all(tag.available_from is None for tag in await self.all_tags()))

    async def test_nonadmin_cannot_start_or_change_addition_mode(self):
        for handler, value in [(handlers.paypal_add_single_start, 'paypal_add_single'),
                               (handlers.paypal_add_bulk_start, 'paypal_add_bulk'),
                               (handlers.paypal_add_timing_choice, 'paypal_add_timing:24')]:
            callback = self.callback(value, uid=1)
            await handler(callback, self.state)
            callback.message.answer.assert_not_awaited()
            self.assertEqual(await self.state.get_data(), {})
        self.assertEqual(await self.all_tags(), [])

    async def test_invalid_delay_does_not_insert_stock(self):
        for delay in (-24, 1, 48, '24', True):
            with self.assertRaises(ValueError):
                await db.add_paypal_tag('@Invalid', delay_hours=delay)
            with self.assertRaises(ValueError):
                await db.add_paypal_tags(['@Invalid'], delay_hours=delay)
        self.assertEqual(await self.all_tags(), [])

    async def test_migration_upgrades_old_table_without_imposing_new_wait(self):
        legacy = create_async_engine('sqlite+aiosqlite:///:memory:')
        try:
            async with legacy.begin() as conn:
                await conn.execute(text("CREATE TABLE paypal_tags (id INTEGER PRIMARY KEY, tag TEXT, status TEXT)"))
                await conn.execute(text("INSERT INTO paypal_tags VALUES (1, '@Old', 'available')"))
                await db._migrate_paypal_warmup(conn)
                row = (await conn.execute(text('SELECT available_from, stock_announced_at FROM paypal_tags'))).one()
                self.assertEqual(tuple(row), (None, None))
                await conn.execute(text("UPDATE paypal_tags SET available_from = '2026-11-04 12:00:00'"))
                await db._migrate_paypal_warmup(conn)
                self.assertEqual(await conn.scalar(text('SELECT available_from FROM paypal_tags')), '2026-11-04 12:00:00')
        finally:
            await legacy.dispose()
