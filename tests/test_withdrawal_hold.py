"""Withdrawal gating and all three notices, using SQLite and mocked Telegram."""
import os
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NO_NETWORK"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1/test"
os.environ["ADMIN_IDS"] = ""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db, handlers, keyboards, ui


class WithdrawalHoldTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tag_counter = 0
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(db, "SessionLocal", self.sessions))
        self.stack.enter_context(patch.object(handlers, "is_admin", side_effect=lambda uid: uid == 999))
        self.stack.enter_context(patch.object(handlers, "has_access", new=AsyncMock(return_value=True)))
        self.render = self.stack.enter_context(patch.object(handlers, "render_screen", new_callable=AsyncMock))
        self.replace = self.stack.enter_context(patch.object(handlers, "replace_photo_with_text", new_callable=AsyncMock))
        async with self.sessions() as session:
            session.add_all([
                db.User(id=1, username="member", payout_method="cryptobot"),
                db.User(id=2, username="rocket", payout_method="xrocket"),
                db.RateRule(min_amount=1, percent=50),
            ])
            await session.commit()

    async def asyncTearDown(self):
        self.stack.close()
        await self.engine.dispose()

    async def request(self, user_id=1, amount=100, direct=False, **extra):
        self.tag_counter += 1
        async with self.sessions() as session:
            tag = db.PaypalTag(tag=f"@PayPal{self.tag_counter}<&>", status="issued", issued_to_user_id=user_id, had_gestop=1)
            session.add(tag)
            await session.flush()
            req = db.Request(user_id=user_id, amount=amount, paypal_tag_id=tag.id,
                             status="paypal_issued" if direct else "waiting_check", paypal_was_gestop=1, **extra)
            session.add(req)
            await session.commit()
            return req

    async def held(self, user_id=1, amount=100, **extra):
        req = await self.request(user_id=user_id, amount=amount, **extra)
        return await db.confirm_payment(req.id, 999)

    async def release(self, user_id=1, amount=100):
        req = await self.held(user_id, amount)
        released, reason = await db.mark_paypal_withdrawn(req.id, 999)
        self.assertEqual(reason, "done")
        return released

    def callback(self, data, user_id=999):
        return SimpleNamespace(
            data=data, from_user=SimpleNamespace(id=user_id), answer=AsyncMock(),
            message=SimpleNamespace(photo=[], edit_text=AsyncMock(), edit_caption=AsyncMock(), answer=AsyncMock()),
            bot=SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock()),
        )

    async def expire(self, request_id):
        async with self.sessions() as session:
            req = await session.get(db.Request, request_id)
            req.withdrawal_retry_at = datetime.utcnow() - timedelta(seconds=1)
            await session.commit()
            return req.withdrawal_retry_at

    async def test_confirmation_notifies_once_and_holds_accrual_outside_all_payouts(self):
        req = await self.request()
        callback = self.callback(f"admin_confirm_same:{req.id}")
        await handlers.admin_confirm_same(callback)
        await handlers.admin_confirm_same(callback)
        callback.bot.send_photo.assert_awaited_once()
        notice = callback.bot.send_photo.await_args.kwargs["caption"]
        self.assertIn("Оплата подтверждена", notice)
        self.assertIn("50.00 USDT", notice)
        self.assertIn("ожидают вывода с PayPal", notice)
        self.assertIn("&lt;&amp;&gt;", notice)
        self.assertNotIn("GeS", notice)
        self.assertEqual((await db.get_request(req.id)).status, "withdrawal_pending")
        self.assertEqual((await db.get_payment_balance_entry(req.id)).status, "held")
        balance = await db.get_user_balance(1)
        self.assertEqual((balance["available"], balance["held"], balance["count_available"]), (0, 50, 0))
        self.assertEqual((await db.get_payout_user_details(1))["entries"], [])
        self.assertEqual((await db.list_users_with_available_balance())[0], [])
        totals = await db.get_payout_dashboard_counts()
        self.assertEqual((totals["total"], totals["cryptobot_total"], totals["xrocket_total"]), (0, 0, 0))
        deliver = AsyncMock()
        self.assertIsNone(await db.complete_manual_payout(1, 999, deliver_check=deliver))
        deliver.assert_not_awaited()
        self.assertIsNone(await db.mark_payout_done(req.id, 999))

    async def test_direct_confirmation_uses_same_hold_and_user_notice(self):
        req = await self.request(direct=True)
        callback = self.callback(f"working_money_received:{req.id}:search")
        await handlers.working_money_received_handler(callback)
        await handlers.working_money_received_handler(callback)
        callback.bot.send_message.assert_awaited_once()
        notice = callback.bot.send_message.await_args.args[1]
        self.assertIn("Оплата подтверждена", notice)
        self.assertIn("50.00 USDT", notice)
        self.assertNotIn("GeS", notice)
        self.assertEqual((await db.get_user_balance(1))["available"], 0)
        self.assertEqual((await db.get_payment_balance_entry(req.id)).status, "held")

    async def test_withdrawal_releases_only_target_once_and_sends_current_total_and_provider(self):
        await self.release(2, 80)  # 40 already available
        req = await self.held(2, 140)  # 70 held
        await self.held(2, 20)  # 10 stays held
        callback = self.callback(f"paypal_withdraw_done:{req.id}:payout:0")
        await handlers.paypal_withdraw_done_handler(callback)
        await handlers.paypal_withdraw_done_handler(callback)
        callback.bot.send_message.assert_awaited_once()
        notice = callback.bot.send_message.await_args.args[1]
        for part in ("успешно выведены", "70.00 USDT", "110.00 USDT", "xRocket", "&lt;&amp;&gt;"):
            self.assertIn(part, notice)
        self.assertNotIn("GeS", notice)
        self.assertIn("GeS", self.replace.await_args.args[1])
        saved = await db.get_request(req.id)
        self.assertEqual((saved.status, saved.paypal_withdrawn_by), ("payout_pending", 999))
        self.assertIsNotNone(saved.paypal_withdrawn_at)
        balance = await db.get_user_balance(2)
        self.assertEqual((balance["available"], balance["held"]), (110, 10))
        self.assertEqual((await db.get_payout_dashboard_counts())["xrocket_total"], 110)
        self.assertEqual([r.id for r in (await db.list_payment_requests("ready"))[0]][0], req.id)

    async def test_wait_notifies_once_persists_24_hours_and_does_not_release_money(self):
        req = await self.held()
        started = datetime(2026, 10, 25, 12, 30)
        callback = self.callback(f"wd_wait:{req.id}:0:payout:0")
        with patch.object(db, "datetime", wraps=datetime) as clock:
            clock.utcnow.return_value = started
            await handlers.withdrawal_wait_handler(callback)
            await handlers.withdrawal_wait_handler(callback)
        callback.bot.send_message.assert_awaited_once()
        notice = callback.bot.send_message.await_args.args[1]
        for part in ("вывести средства не удалось", "26.10.2026 15:30 МСК", "50.00 USDT", "остаётся в ожидании"):
            self.assertIn(part, notice)
        self.assertNotIn("GeS", notice)
        saved = await db.get_request(req.id)
        self.assertEqual(saved.withdrawal_retry_at, started + timedelta(hours=24))
        self.assertEqual(saved.withdrawal_wait_count, 1)
        self.assertEqual((await db.get_user_balance(1))["available"], 0)
        # Restart migration preserves an active deadline and the button revision.
        await db._backfill_withdrawal_holds()
        after = await db.get_request(req.id)
        self.assertEqual((after.withdrawal_retry_at, after.withdrawal_wait_count), (saved.withdrawal_retry_at, 1))
        self.assertEqual((await db.list_payment_requests("payout"))[0], [])
        self.assertEqual([r.id for r in (await db.list_payment_requests("withdraw_wait"))[0]], [req.id])

    async def test_expiry_only_allows_retry_and_new_wait_notifies_once(self):
        req = await self.held()
        await db.wait_paypal_withdrawal(req.id, 0)
        deadline = await self.expire(req.id)
        counts = await db.get_paypal_withdrawal_counts()
        self.assertEqual((counts["waiting_24"], counts["retry_ready"]), (1, 1))
        self.assertEqual((await db.get_user_balance(1))["available"], 0)
        self.assertIsNone(await db.complete_manual_payout(1, 999))
        stale = self.callback(f"wd_wait:{req.id}:0:withdraw_wait:0")
        await handlers.withdrawal_wait_handler(stale)
        stale.bot.send_message.assert_not_awaited()
        self.assertEqual((await db.get_request(req.id)).withdrawal_retry_at, deadline)
        callback = self.callback(f"wd_wait:{req.id}:1:withdraw_wait:0")
        before = datetime.utcnow()
        await handlers.withdrawal_wait_handler(callback)
        await handlers.withdrawal_wait_handler(callback)
        callback.bot.send_message.assert_awaited_once()
        saved = await db.get_request(req.id)
        self.assertGreaterEqual(saved.withdrawal_retry_at, before + timedelta(hours=24))
        self.assertEqual(saved.withdrawal_wait_count, 2)
        self.assertEqual((await db.get_user_balance(1))["held"], 50)
        self.assertEqual((await db.get_paypal_withdrawal_counts())["retry_ready"], 0)

    async def test_active_wait_cannot_be_extended_even_with_current_count(self):
        req = await self.held()
        first, _ = await db.wait_paypal_withdrawal(req.id, 0)
        current, reason = await db.wait_paypal_withdrawal(req.id, 1)
        self.assertEqual(reason, "already_waiting")
        self.assertEqual((current.withdrawal_retry_at, current.withdrawal_wait_count), (first.withdrawal_retry_at, 1))

    async def test_success_during_wait_removes_queue_and_stale_wait_cannot_rehold(self):
        req = await self.held()
        await db.wait_paypal_withdrawal(req.id, 0)
        self.assertEqual((await db.mark_paypal_withdrawn(req.id, 999))[1], "done")
        callback = self.callback(f"wd_wait:{req.id}:1:withdraw_wait:0")
        await handlers.withdrawal_wait_handler(callback)
        callback.bot.send_message.assert_not_awaited()
        self.assertEqual((await db.list_payment_requests("withdraw_wait"))[0], [])
        self.assertEqual((await db.get_user_balance(1))["available"], 50)

    async def test_refund_of_held_payment_cancels_only_it_and_blocks_late_success(self):
        await self.release(amount=80)
        req = await self.held()
        await db.wait_paypal_withdrawal(req.id, 0)
        callback = self.callback(f"payment_refund_yes:{req.id}:withdraw_wait:0")
        await handlers.payment_refund_handler(callback)
        self.assertEqual((await db.get_request(req.id)).status, "payment_refunded")
        self.assertEqual((await db.get_payment_balance_entry(req.id)).status, "cancelled")
        balance = await db.get_user_balance(1)
        self.assertEqual((balance["available"], balance["held"]), (40, 0))
        late = self.callback(f"paypal_withdraw_done:{req.id}:withdraw_wait:0")
        await handlers.paypal_withdraw_done_handler(late)
        late.bot.send_message.assert_not_awaited()
        self.assertEqual((await db.list_payment_requests("withdraw_wait"))[0], [])

    async def test_200_waiting_requests_are_reachable_in_deadline_order(self):
        now = datetime.utcnow()
        async with self.sessions() as session:
            for i in range(200):
                session.add(db.Request(id=1000+i, user_id=1, amount=100, status="withdrawal_pending",
                                       withdrawal_retry_at=now + timedelta(hours=100-i), withdrawal_wait_count=1))
            session.add(db.Request(id=2000, user_id=1, amount=100, status="withdrawal_pending"))
            await session.commit()
        seen = []
        for offset in range(0, 200, 10):
            rows, more = await db.list_payment_requests("withdraw_wait", offset, 10)
            self.assertEqual(more, offset < 190)
            seen.extend(r.id for r in rows)
        self.assertEqual(seen, list(range(1199, 999, -1)))
        self.assertEqual([r.id for r in (await db.list_payment_requests("payout"))[0]], [2000])
        counts = await db.get_payment_counts()
        self.assertEqual((counts["payout"], counts["withdraw_wait"], counts["retry_ready"], counts["ready"]), (1, 200, 100, 0))

    async def test_user_wallet_and_history_separate_held_and_hide_admin_marker(self):
        await self.release(amount=80)
        req = await self.held(amount=140)
        await db.wait_paypal_withdrawal(req.id, 0)
        await handlers.wallet_handler(self.callback("wallet", user_id=1))
        wallet = self.render.await_args.args[2]
        self.assertIn("Доступно к выплате: <b>40.00 USDT", wallet)
        self.assertIn("Ожидает вывода с PayPal: <b>70.00 USDT", wallet)
        await handlers.my_paypals_list(self.callback("my_paypals_list:withdrawal:0", user_id=1))
        history = self.render.await_args.args[2]
        self.assertIn("До повторной попытки:", history)
        self.assertIn("МСК", history)
        self.assertIn("Начисление в ожидании: <b>70.00 USDT", history)
        self.assertNotIn("GeS", wallet + history)
        await self.expire(req.id)
        await handlers.my_paypals_list(self.callback("my_paypals_list:withdrawal:0", user_id=1))
        self.assertIn("Ожидает повторной попытки вывода", self.render.await_args.args[2])

    async def test_migration_only_holds_unwithdrawn_unpaid_legacy_rows_and_is_idempotent(self):
        stamp = datetime(2026, 10, 20)
        cases = [
            ("payout_pending", "available", None, None, None, None),
            ("payout_pending", "available", stamp, None, None, None),
            ("paid_out", "paid", None, stamp, stamp, 10),
            ("payment_refunded", "cancelled", None, None, None, None),
            ("payout_pending", "paid", None, None, stamp, 11),
            ("payout_pending", "available", None, stamp, None, None),
            ("payout_pending", "available", None, None, None, 12),
            ("withdrawal_pending", "held", None, None, None, None),
        ]
        async with self.sessions() as session:
            for i, (status, entry_status, withdrawn, paid, entry_paid, payout_id) in enumerate(cases, 1):
                session.add(db.Request(id=i, user_id=1, amount=100, payout_amount=50, status=status,
                                       paypal_withdrawn_at=withdrawn, payout_at=paid,
                                       withdrawal_retry_at=stamp if i == 8 else None,
                                       withdrawal_wait_count=2 if i == 8 else 0))
                session.add(db.BalanceEntry(user_id=1, request_id=i, amount=50, status=entry_status,
                                            paid_at=entry_paid, payout_id=payout_id))
            await session.commit()
        for _ in range(2):
            await db._backfill_withdrawal_holds()
            for i, expected in enumerate(cases, 1):
                req = await db.get_request(i)
                entry = await db.get_payment_balance_entry(i)
                self.assertEqual(req.status, "withdrawal_pending" if i == 1 else expected[0])
                self.assertEqual(entry.status, "held" if i == 1 else expected[1])
                self.assertEqual((req.paypal_withdrawn_at, req.payout_at, entry.paid_at, entry.payout_id), expected[2:])
                self.assertEqual(req.withdrawal_retry_at, stamp if i == 8 else None)
                self.assertEqual(req.withdrawal_wait_count, 2 if i == 8 else 0)

    async def test_amount_and_happy_hours_rate_are_frozen_before_release(self):
        async with self.sessions() as session:
            session.add(db.HappyHoursCampaign(id=1, start_at=datetime(2026, 1, 1), end_at=datetime(2026, 1, 2),
                                               min_amount=1, percent=80, broadcast_text="test", activated_by=999))
            await session.commit()
        req = await self.held(happy_hours_percent=80, happy_hours_locked_at=datetime.utcnow(), happy_hours_campaign_id=1)
        self.assertEqual((req.payout_percent, req.payout_amount, req.happy_hours_applied), (80, 80, 1))
        async with self.sessions() as session:
            rule = await session.scalar(select(db.RateRule))
            rule.percent = 30
            await session.commit()
        self.assertIsNone(await db.update_request_amount(req.id, 300))
        await db.wait_paypal_withdrawal(req.id, 0)
        saved, result = await db.mark_paypal_withdrawn(req.id, 999)
        self.assertEqual(result, "done")
        self.assertEqual((saved.amount, saved.payout_amount), (100, 80))
        self.assertEqual((await db.get_payment_balance_entry(req.id)).amount, 80)
        self.assertIsNone(await db.update_request_amount(req.id, 200))

    async def test_payout_pays_only_released_entries_and_legacy_button_cannot_pay_twice(self):
        released = await self.release(amount=80)
        held = await self.held(amount=140)
        details = await db.get_payout_user_details(1)
        deliver = AsyncMock()
        payout = await db.complete_manual_payout(1, 999, expected_entries=db.payout_entries_snapshot(details["entries"]), deliver_check=deliver)
        deliver.assert_awaited_once()
        self.assertEqual(payout.total_amount, 40)
        self.assertEqual((await db.get_request(held.id)).status, "withdrawal_pending")
        self.assertIsNone(await db.mark_payout_done(released.id, 999))
        self.assertIsNone(await db.mark_payout_done(held.id, 999))
        balance = await db.get_user_balance(1)
        self.assertEqual((balance["available"], balance["held"], balance["paid"]), (0, 70, 40))
        await db.mark_paypal_withdrawn(held.id, 999)
        self.assertIsNotNone(await db.mark_payout_done(held.id, 999))
        self.assertIsNone(await db.mark_payout_done(held.id, 999))
        self.assertEqual((await db.get_user_balance(1))["paid"], 110)
        self.assertEqual(len(await db.list_manual_payouts(1)), 2)

    async def test_new_release_invalidates_prepared_aggregate_check_before_sending(self):
        await self.release(amount=80)
        held = await self.held()
        details = await db.get_payout_user_details(1)
        snapshot = db.payout_entries_snapshot(details["entries"])
        await db.mark_paypal_withdrawn(held.id, 999)
        deliver = AsyncMock()
        self.assertIsNone(await db.complete_manual_payout(1, 999, expected_entries=snapshot, deliver_check=deliver))
        deliver.assert_not_awaited()
        self.assertEqual((await db.get_user_balance(1))["available"], 90)

    async def test_inconsistent_available_entry_without_withdrawal_cannot_deliver_check(self):
        req = await self.held()
        async with self.sessions() as session:
            entry = await session.scalar(select(db.BalanceEntry).where(db.BalanceEntry.request_id == req.id))
            entry.status = "available"
            saved = await session.get(db.Request, req.id)
            saved.status = "payout_pending"
            await session.commit()
        deliver = AsyncMock()
        self.assertIsNone(await db.complete_manual_payout(1, 999, deliver_check=deliver))
        deliver.assert_not_awaited()
        self.assertIsNone(await db.mark_payout_done(req.id, 999))

    async def test_unauthorized_or_malformed_wait_and_success_do_not_change_state(self):
        req = await self.held()
        for data, handler in [(f"wd_wait:{req.id}:0:payout:0", handlers.withdrawal_wait_handler),
                              (f"paypal_withdraw_done:{req.id}:payout:0", handlers.paypal_withdraw_done_handler)]:
            callback = self.callback(data, user_id=1)
            await handler(callback)
            callback.answer.assert_awaited_once_with("Нет доступа", show_alert=True)
            callback.bot.send_message.assert_not_awaited()
        for data in ("wd_wait:bad:0:payout:0", "wd_wait:1", "wd_wait:1:-1:payout:0", "wd_wait:1:0:unknown:0"):
            await handlers.withdrawal_wait_handler(self.callback(data))
        saved = await db.get_request(req.id)
        self.assertIsNone(saved.withdrawal_retry_at)
        self.assertIsNone(saved.paypal_withdrawn_at)

    async def test_notification_failures_are_visible_to_admin_without_reverting_state(self):
        req = await self.request()
        confirm = self.callback(f"admin_confirm_same:{req.id}")
        confirm.bot.send_photo.side_effect = RuntimeError("offline")
        await handlers.admin_confirm_same(confirm)
        self.assertIn("Не удалось подтвердить доставку", confirm.message.edit_text.await_args.args[0])
        wait = self.callback(f"wd_wait:{req.id}:0:payout:0")
        wait.bot.send_message.side_effect = RuntimeError("offline")
        await handlers.withdrawal_wait_handler(wait)
        self.assertIn("Не удалось подтвердить доставку", self.replace.await_args.args[1])
        self.assertIsNotNone((await db.get_request(req.id)).withdrawal_retry_at)
        success = self.callback(f"paypal_withdraw_done:{req.id}:withdraw_wait:0")
        success.bot.send_message.side_effect = RuntimeError("offline")
        await handlers.paypal_withdraw_done_handler(success)
        self.assertIn("Не удалось подтвердить доставку", self.replace.await_args.args[1])
        self.assertEqual((await db.get_user_balance(1))["available"], 50)

    async def test_card_hides_wait_until_expiry_and_new_buttons_fit_telegram_limit(self):
        req = await self.held()
        first = keyboards.payment_card_menu(req.id, 1, req.status)
        self.assertTrue(any(b.callback_data.startswith("wd_wait:") for row in first.inline_keyboard for b in row if b.callback_data))
        waiting, _ = await db.wait_paypal_withdrawal(req.id, 0)
        active = keyboards.payment_card_menu(req.id, 1, req.status, "withdraw_wait", 190,
                                             withdrawal_retry_at=waiting.withdrawal_retry_at, withdrawal_wait_count=1)
        self.assertFalse(any(b.callback_data.startswith("wd_wait:") for row in active.inline_keyboard for b in row if b.callback_data))
        deadline = await self.expire(req.id)
        expired = keyboards.payment_card_menu(2147483647, 1, req.status, "withdraw_wait", 2147483647,
                                              withdrawal_retry_at=deadline, withdrawal_wait_count=2147483647)
        for row in expired.inline_keyboard:
            for b in row:
                if b.callback_data:
                    self.assertLessEqual(len(b.callback_data.encode()), 64)
        self.assertTrue(any(b.text == "⏳ Ещё 24 часа" for row in expired.inline_keyboard for b in row))
        self.assertEqual(ui.withdrawal_wait_text(SimpleNamespace(withdrawal_retry_at=None)), "⏳ Ожидает вывода с PayPal")


if __name__ == "__main__":
    unittest.main()
