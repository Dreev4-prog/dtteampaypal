"""Gestop deletion and admin-only GeS markers, with no live services."""
import os
import unittest
from contextlib import ExitStack
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NO_NETWORK"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1/test"
os.environ["ADMIN_IDS"] = ""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db, handlers, keyboards


class GestopGeSTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(db, "SessionLocal", self.sessions))
        self.stack.enter_context(patch.object(handlers, "is_admin", side_effect=lambda uid: uid == 999))
        self.stack.enter_context(patch.object(handlers, "settings", SimpleNamespace(admin_ids=[999])))
        self.render = self.stack.enter_context(patch.object(handlers, "render_screen", new_callable=AsyncMock))
        async with self.sessions() as session:
            session.add_all([db.User(id=1, username="member", status="approved"), db.RateRule(min_amount=1, percent=50)])
            await session.commit()

    async def asyncTearDown(self):
        self.stack.close()
        await self.engine.dispose()

    def callback(self, data, user_id=999):
        return SimpleNamespace(
            data=data, from_user=SimpleNamespace(id=user_id), answer=AsyncMock(),
            message=SimpleNamespace(photo=[], edit_text=AsyncMock(), edit_caption=AsyncMock(), answer=AsyncMock()),
            bot=SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock()),
        )

    async def add_tag(self, status="gestoppt", at=None):
        async with self.sessions() as session:
            tag = db.PaypalTag(tag="@Example<&>", status=status, gestop_at=at)
            session.add(tag)
            await session.commit()
            return tag

    async def reissued_request(self):
        tag = await self.add_tag()
        await db.set_paypal_tag_status(tag.id, "available", expected_status="gestoppt")
        req = await db.create_request(1, 100)
        req, tag = await db.issue_paypal(req.id)
        self.assertIsNotNone(tag)
        self.assertEqual(req.paypal_was_gestop, 1)
        return req, tag

    async def test_release_reissue_and_payment_keep_unknown_date_history(self):
        req, tag = await self.reissued_request()
        self.assertIsNone(tag.gestop_at)
        self.assertEqual(tag.had_gestop, 1)
        self.assertTrue(await db.mark_paid_by_user(req.id, 1))
        paid = await db.confirm_payment(req.id, 999)
        self.assertEqual(paid.paypal_was_gestop, 1)
        self.assertEqual(paid.payout_amount, 50)
        self.assertIsNone(await db.confirm_payment(req.id, 999))
        async with self.sessions() as session:
            entries = (await session.scalars(select(db.BalanceEntry))).all()
            self.assertEqual(len(entries), 1)

    async def test_later_gestop_does_not_relabel_earlier_payment(self):
        tag = await self.add_tag(status="available")
        req = await db.create_request(1, 100)
        req, _ = await db.issue_paypal(req.id)
        self.assertEqual(req.paypal_was_gestop, 0)
        await db.confirm_working_payment(req.id, 999)
        await db.set_paypal_tag_status(tag.id, "gestoppt")
        self.assertEqual((await db.get_paypal_tag(tag.id)).had_gestop, 1)
        await db._backfill_gestop_history()
        old = await db.get_request(req.id)
        self.assertEqual(old.paypal_was_gestop, 0)
        self.assertEqual(handlers._admin_ges_line(old), "")
        await db.set_paypal_tag_status(tag.id, "available", expected_status="gestoppt")
        new = await db.create_request(1, 100)
        new, _ = await db.issue_paypal(new.id)
        self.assertEqual(new.paypal_was_gestop, 1)

    async def test_delete_confirmation_restore_and_request_history(self):
        at = datetime(2026, 10, 1)
        tag = await self.add_tag(at=at)
        async with self.sessions() as session:
            session.add(db.Request(id=1, user_id=1, amount=100, paypal_tag_id=tag.id, status="returned_gestoppt"))
            await session.commit()
        card = keyboards.gestop_card_menu(tag.id, "all", 15, 30)
        delete_data = card.inline_keyboard[1][0].callback_data
        await handlers.gestop_delete_handler(self.callback(delete_data))
        self.assertEqual((await db.get_paypal_tag(tag.id)).status, "gestoppt")
        screen = self.render.await_args.args
        self.assertIn("@Example&lt;&amp;&gt;", screen[2])
        markup = screen[3]
        self.assertEqual(markup.inline_keyboard[1][0].callback_data, f"gestop_card:{tag.id}:all:15:30")
        confirm_data = markup.inline_keyboard[0][0].callback_data
        await handlers.gestop_delete_handler(self.callback(confirm_data))
        deleted = await db.get_paypal_tag(tag.id)
        self.assertEqual((deleted.status, deleted.had_gestop, deleted.gestop_at), ("deleted", 1, at))
        self.assertEqual((await db.get_request(1)).status, "returned_gestoppt")
        self.assertEqual((await db.list_gestop_tags())["total"], 0)
        self.assertEqual(await db.delete_gestop_paypal_tag(tag.id), (False, "not_gestop"))
        restored, _ = await db.restore_deleted_paypal_tag(tag.id)
        self.assertEqual((restored.status, restored.had_gestop), ("available", 1))
        req = await db.create_request(1, 100)
        req, _ = await db.issue_paypal(req.id)
        self.assertEqual(req.paypal_was_gestop, 1)

    async def test_stale_delete_cannot_delete_freed_or_reissued_paypal(self):
        tag = await self.add_tag()
        await db.set_paypal_tag_status(tag.id, "available", expected_status="gestoppt")
        for status in ("available", "issued", "used", "deleted"):
            async with self.sessions() as session:
                saved = await session.get(db.PaypalTag, tag.id)
                saved.status = status
                await session.commit()
            callback = self.callback(f"ges_del_yes:{tag.id}:all:0:0")
            await handlers.gestop_delete_handler(callback)
            callback.answer.assert_awaited_once_with("Этот PayPal уже не в Gestop", show_alert=True)
            self.assertEqual((await db.get_paypal_tag(tag.id)).status, status)

    async def test_delete_access_validation_and_callback_size(self):
        tag = await self.add_tag()
        for action in ("ges_del_ask", "ges_del_yes"):
            callback = self.callback(f"{action}:{tag.id}:all:0:0", user_id=1)
            await handlers.gestop_delete_handler(callback)
            callback.answer.assert_awaited_once_with("Нет доступа", show_alert=True)
        for data in ("ges_del_yes:1:2026-02-31:0:0", "ges_del_yes:x:all:0:0", "ges_del_yes:1"):
            callback = self.callback(data)
            await handlers.gestop_delete_handler(callback)
            callback.answer.assert_awaited_once_with("PayPal не найден", show_alert=True)
        self.assertEqual((await db.get_paypal_tag(tag.id)).status, "gestoppt")
        self.render.assert_not_awaited()
        for menu in (keyboards.gestop_card_menu, keyboards.gestop_delete_confirm_menu):
            for row in menu(2147483647, "2026-10-19", 2147483647, 2147483647).inline_keyboard:
                for button in row:
                    self.assertLessEqual(len(button.callback_data.encode()), 64)

    async def test_payment_notice_is_admin_only(self):
        req, _ = await self.reissued_request()
        callback = self.callback(f"user_paid_confirm:{req.id}", user_id=1)
        await handlers.user_paid_confirm(callback)
        args = callback.bot.send_message.await_args.args
        self.assertEqual(args[0], 999)
        self.assertIn("<b>GeS</b>", args[1])
        self.assertIn("@Example&lt;&amp;&gt;", args[1])
        self.assertNotIn("GeS", self.render.await_args.args[2])

    async def test_admin_payment_views_and_confirmation_preserve_marker(self):
        req, _ = await self.reissued_request()
        await db.mark_paid_by_user(req.id, 1)
        for filter_name in ("check", "payout", "paidout", "all"):
            markup = keyboards.payments_list_menu([req], filter_name, 0, 10, False)
            self.assertTrue(markup.inline_keyboard[0][0].text.startswith("♻️ GeS"))
        card = self.callback(f"payment_card:{req.id}:check:0")
        await handlers.payment_card_handler(card)
        self.assertIn("<b>GeS</b>", card.message.edit_text.await_args.args[0])
        confirm = self.callback(f"admin_confirm_same:{req.id}")
        await handlers.admin_confirm_same(confirm)
        self.assertIn("<b>GeS</b>", confirm.message.edit_text.await_args.args[0])
        sent = confirm.bot.send_photo.await_args
        self.assertEqual(sent.args[0], 1)
        self.assertNotIn("GeS", sent.kwargs["caption"])
        withdraw = self.callback(f"paypal_withdraw_done:{req.id}:payout:0")
        await handlers.paypal_withdraw_done_handler(withdraw)
        self.assertIn("<b>GeS</b>", withdraw.message.edit_text.await_args.args[0])

    async def test_direct_confirmation_hides_marker_from_member(self):
        req, _ = await self.reissued_request()
        callback = self.callback(f"working_money_received:{req.id}:search")
        await handlers.working_money_received_handler(callback)
        self.assertIn("<b>GeS</b>", callback.message.edit_caption.await_args.kwargs["caption"])
        sent = callback.bot.send_message.await_args.args
        self.assertEqual(sent[0], 1)
        self.assertNotIn("GeS", sent[1])
        self.assertEqual((await db.get_request(req.id)).paypal_was_gestop, 1)

    async def test_changed_amount_and_member_history_do_not_leak_marker(self):
        req, _ = await self.reissued_request()
        await db.mark_paid_by_user(req.id, 1)
        callback = self.callback("")
        message = SimpleNamespace(from_user=callback.from_user, bot=callback.bot, text="125", answer=AsyncMock())
        state = SimpleNamespace(get_data=AsyncMock(return_value={"payment_request_id": req.id}), clear=AsyncMock())
        await handlers.admin_paid_amount_input(message, state)
        self.assertIn("<b>GeS</b>", message.answer.await_args.args[0])
        self.assertNotIn("GeS", message.bot.send_photo.await_args.kwargs["caption"])
        self.assertEqual((await db.get_request(req.id)).payout_amount, 62.5)
        with patch.object(handlers, "has_access", new=AsyncMock(return_value=True)):
            await handlers.my_paypals_list(self.callback("my_paypals_list:payout:0", user_id=1))
        self.assertNotIn("GeS", self.render.await_args.args[2])

    async def test_restore_to_previous_user_preserves_marker(self):
        tag = await self.add_tag(status="deleted")
        async with self.sessions() as session:
            saved = await session.get(db.PaypalTag, tag.id)
            saved.had_gestop = 1
            session.add(db.Request(id=1, user_id=1, amount=100, paypal_tag_id=tag.id, status="admin_recalled_deleted"))
            await session.commit()
        req, _, reason = await db.restore_deleted_paypal_to_work(tag.id, 999)
        self.assertEqual(reason, "restored_to_work")
        self.assertEqual(req.paypal_was_gestop, 1)

    async def test_migration_recovers_evidence_once_without_relabeling_closed_payments(self):
        # Minimal old-schema fixture: newly added snapshot column is initially NULL.
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                for sql in (
                    "CREATE TABLE paypal_tags (id INTEGER PRIMARY KEY, status TEXT, gestop_at TIMESTAMP, had_gestop INTEGER DEFAULT 0)",
                    "CREATE TABLE requests (id INTEGER PRIMARY KEY, paypal_tag_id INTEGER, status TEXT, paypal_was_gestop INTEGER)",
                    "CREATE TABLE paypal_returns (paypal_tag_id INTEGER, status TEXT)",
                    "INSERT INTO paypal_tags (id, status, gestop_at) VALUES (1,'gestoppt',NULL),(2,'issued','2026-10-01'),(3,'issued',NULL),(4,'available',NULL),(5,'issued',NULL)",
                    "INSERT INTO requests VALUES (1,1,'returned_gestoppt',NULL),(2,2,'waiting_check',NULL),(3,2,'paid_out',NULL),(4,3,'paypal_issued',NULL),(5,5,'paypal_issued',NULL),(6,4,'paypal_limited',NULL)",
                    "INSERT INTO paypal_returns VALUES (5,'gestoppt')",
                ):
                    await conn.execute(text(sql))
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            with patch.object(db, "SessionLocal", sessions):
                await db._backfill_gestop_history()
                async with sessions() as session:
                    tags = dict((await session.execute(text("SELECT id, had_gestop FROM paypal_tags"))).all())
                    requests = dict((await session.execute(text("SELECT id, paypal_was_gestop FROM requests"))).all())
                    self.assertEqual(tags, {1: 1, 2: 1, 3: 0, 4: 1, 5: 1})
                    self.assertEqual(requests, {1: 0, 2: 1, 3: 0, 4: 0, 5: 1, 6: 0})
                    await session.execute(text("UPDATE paypal_tags SET status='gestoppt' WHERE id=3"))
                    await session.commit()
                await db._backfill_gestop_history()
                async with sessions() as session:
                    again = dict((await session.execute(text("SELECT id, paypal_was_gestop FROM requests"))).all())
                    self.assertEqual(again, requests)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
