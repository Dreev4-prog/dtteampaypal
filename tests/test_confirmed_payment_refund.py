"""Offline regression tests for cancelling a confirmed but unpaid payment."""
import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NO_NETWORK"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1/test"
os.environ["ADMIN_IDS"] = ""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db, handlers, keyboards


class ConfirmedRefundTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(db, "SessionLocal", self.sessions))
        self.stack.enter_context(patch.object(handlers, "is_admin", side_effect=lambda uid: uid == 999))
        self.render = self.stack.enter_context(patch.object(handlers, "render_screen", new_callable=AsyncMock))
        self.replace = self.stack.enter_context(patch.object(handlers, "replace_photo_with_text", new_callable=AsyncMock))
        async with self.sessions() as session:
            session.add_all([
                db.User(id=1, username="first", payout_method="cryptobot"),
                db.User(id=2, username="second", payout_method="xrocket"),
                db.RateRule(min_amount=1, percent=50),
            ])
            await session.commit()

    async def asyncTearDown(self):
        self.stack.close()
        await self.engine.dispose()

    async def payment(self, user_id=1, amount=100, direct=False):
        async with self.sessions() as session:
            req = db.Request(user_id=user_id, amount=amount, status="paypal_issued" if direct else "waiting_check")
            session.add(req)
            await session.flush()
            tag = db.PaypalTag(tag=f"@PayPal{req.id}<&>", status="issued", issued_to_user_id=user_id)
            session.add(tag)
            await session.flush()
            req.paypal_tag_id = tag.id
            await session.commit()
        if direct:
            return await db.confirm_working_payment(req.id, 999)
        return await db.confirm_payment(req.id, 999)

    def callback(self, data, user_id=999):
        return SimpleNamespace(
            data=data, from_user=SimpleNamespace(id=user_id), answer=AsyncMock(),
            message=SimpleNamespace(photo=[], edit_text=AsyncMock()),
            bot=SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock()),
        )

    def state(self, data=None):
        values = dict(data or {})

        async def update(**kwargs):
            values.update(kwargs)

        return SimpleNamespace(
            get_data=AsyncMock(side_effect=lambda: dict(values)), update_data=AsyncMock(side_effect=update),
            set_state=AsyncMock(), clear=AsyncMock(),
        )

    def check_message(self):
        return SimpleNamespace(
            from_user=SimpleNamespace(id=999), message_id=123, send_copy=AsyncMock(),
            answer=AsyncMock(), bot=SimpleNamespace(send_message=AsyncMock()),
        )

    async def test_refund_removes_only_target_accrual_and_updates_provider_totals(self):
        first = await self.payment(1, 150)  # 75
        second = await self.payment(1, 100)  # 50
        rocket = await self.payment(2, 80)  # 40
        refunded, result = await db.refund_confirmed_payment(first.id, 999)
        self.assertEqual(result, "refunded")
        self.assertEqual((refunded.status, refunded.payment_refunded_by), ("payment_refunded", 999))
        self.assertIsNotNone(refunded.payment_refunded_at)
        self.assertEqual(refunded.payment_confirmed_at, first.payment_confirmed_at)
        self.assertEqual((await db.get_payment_balance_entry(first.id)).status, "cancelled")
        self.assertEqual((await db.get_user_balance(1))["available"], 50)
        details = await db.get_payout_user_details(1)
        self.assertEqual([e.request_id for e in details["entries"]], [second.id])
        totals = await db.get_payout_dashboard_counts()
        self.assertEqual((totals["cryptobot_total"], totals["xrocket_total"], totals["total"]), (50, 40, 90))
        await db.refund_confirmed_payment(rocket.id, 999)
        totals = await db.get_payout_dashboard_counts()
        self.assertEqual((totals["xrocket_total"], totals["users"]), (0, 1))

    async def test_history_retains_return_and_excludes_it_from_success_and_pending(self):
        req = await self.payment()
        self.assertIn(req.id, [row["request_id"] for row in await db.get_dt_payments_feed()])
        await db.refund_confirmed_payment(req.id, 999)
        self.assertEqual((await db.list_payment_requests("payout"))[0], [])
        self.assertEqual([r.id for r in (await db.list_payment_requests("refunded"))[0]], [req.id])
        self.assertEqual([r.id for r in (await db.list_payment_requests("all"))[0]], [req.id])
        counts = await db.get_payment_counts()
        self.assertEqual((counts["payout"], counts["refunded"], counts["all"]), (0, 1, 1))
        self.assertEqual((await db.get_user_profit_summary(1))["pending"], 0)
        self.assertEqual((await db.get_paypal_withdrawal_counts())["total"], 0)
        self.assertEqual(await db.get_dt_payments_feed(), [])
        rows, _ = await db.list_users_with_available_balance()
        self.assertEqual(rows, [])

    async def test_repeated_click_does_not_change_balance_or_audit(self):
        req = await self.payment()
        first, _ = await db.refund_confirmed_payment(req.id, 999)
        again, result = await db.refund_confirmed_payment(req.id, 888)
        self.assertEqual(result, "already_refunded")
        self.assertEqual((again.payment_refunded_at, again.payment_refunded_by), (first.payment_refunded_at, 999))
        self.assertEqual((await db.get_user_balance(1))["available"], 0)
        self.assertIsNone(await db.confirm_payment(req.id, 999))
        self.assertIsNone(await db.confirm_working_payment(req.id, 999))

    async def test_paid_or_linked_to_payout_cannot_be_cancelled(self):
        req = await self.payment()
        payout = await db.complete_manual_payout(1, 999)
        _, reason = await db.refund_confirmed_payment(req.id, 999)
        self.assertEqual(reason, "already_paid")
        entry = await db.get_payment_balance_entry(req.id)
        self.assertEqual((entry.status, entry.payout_id), ("paid", payout.id))
        self.assertEqual((await db.get_user_balance(1))["paid"], 50)
        # Also reject an inconsistent legacy request with a paid accrual.
        async with self.sessions() as session:
            saved = await session.get(db.Request, req.id)
            saved.status, saved.payout_at = "payout_pending", None
            await session.commit()
        self.assertEqual((await db.refund_confirmed_payment(req.id, 999))[1], "already_paid")

    async def test_missing_balance_wrong_status_and_missing_request_are_safe(self):
        req = await self.payment()
        async with self.sessions() as session:
            entry = await session.scalar(select(db.BalanceEntry).where(db.BalanceEntry.request_id == req.id))
            await session.delete(entry)
            await session.commit()
        self.assertEqual((await db.refund_confirmed_payment(req.id, 999))[1], "no_available_entry")
        self.assertEqual((await db.get_request(req.id)).status, "payout_pending")
        waiting = await db.create_request(1, 100)
        self.assertEqual((await db.refund_confirmed_payment(waiting.id, 999))[1], "not_pending")
        self.assertEqual(await db.refund_confirmed_payment(999999, 999), (None, "not_found"))

    async def test_withdrawn_payment_and_direct_confirmation_can_be_refunded_without_changing_paypal(self):
        req = await self.payment(direct=True)
        await db.mark_paypal_withdrawn(req.id, 999)
        tag_before = await db.get_paypal_tag(req.paypal_tag_id)
        refunded, reason = await db.refund_confirmed_payment(req.id, 999)
        self.assertEqual(reason, "refunded")
        self.assertIsNotNone(refunded.paypal_withdrawn_at)
        await db._backfill_gestop_history()
        tag_after = await db.get_paypal_tag(req.paypal_tag_id)
        self.assertEqual((tag_after.status, tag_after.had_gestop), (tag_before.status, 0))

    async def test_happy_hours_turnover_excludes_return_but_keeps_payment_audit(self):
        req = await self.payment()
        async with self.sessions() as session:
            saved = await session.get(db.Request, req.id)
            saved.happy_hours_campaign_id = 10
            saved.happy_hours_applied = 1
            await session.commit()
        self.assertEqual((await db.get_happy_hours_stats(10))["turnover"], 100)
        await db.refund_confirmed_payment(req.id, 999)
        stats = await db.get_happy_hours_stats(10)
        self.assertEqual((stats["issued"], stats["applied"], stats["turnover"]), (1, 0, 0))
        self.assertEqual((await db.get_request(req.id)).happy_hours_applied, 1)

    async def test_confirmation_is_read_only_and_cancel_returns_to_original_card(self):
        req = await self.payment()
        markup = keyboards.payment_card_menu(req.id, 1, req.status, "payout", 20)
        data = next(b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data and b.callback_data.startswith("payment_refund_ask:"))
        await handlers.payment_refund_handler(self.callback(data))
        text, confirm = self.render.await_args.args[2:4]
        self.assertIn("50.00 USDT", text)
        self.assertIn("&lt;&amp;&gt;", text)
        self.assertEqual(confirm.inline_keyboard[-1][0].callback_data, f"payment_card:{req.id}:payout:20")
        self.assertEqual((await db.get_request(req.id)).status, "payout_pending")
        await handlers.payment_refund_handler(self.callback(confirm.inline_keyboard[0][0].callback_data))
        self.assertEqual((await db.get_user_balance(1))["available"], 0)
        self.assertIn("Отменено начисление", self.render.await_args.args[2])
        card = self.callback(f"payment_card:{req.id}:refunded:0")
        await handlers.payment_card_handler(card)
        text = card.message.edit_text.await_args.args[0]
        self.assertIn("Возврат отмечен", text)
        self.assertIn("<code>999</code>", text)
        self.assertNotIn("💰 Начислено пользователю", text)

    async def test_access_and_malformed_callbacks_do_not_mutate(self):
        req = await self.payment()
        for action in ("ask", "yes"):
            callback = self.callback(f"payment_refund_{action}:{req.id}:payout:0", user_id=1)
            await handlers.payment_refund_handler(callback)
            callback.answer.assert_awaited_once_with("Нет доступа", show_alert=True)
        for data in ("payment_refund_yes:bad:payout:0", "payment_refund_yes:1", "payment_refund_yes:1:bad:0"):
            await handlers.payment_refund_handler(self.callback(data))
        self.assertEqual((await db.get_request(req.id)).status, "payout_pending")
        self.render.assert_not_awaited()

    async def test_user_history_shows_cancelled_accrual_without_ges_or_amount_due(self):
        req = await self.payment()
        async with self.sessions() as session:
            saved = await session.get(db.Request, req.id)
            saved.paypal_was_gestop = 1
            await session.commit()
        await db.refund_confirmed_payment(req.id, 999)
        with patch.object(handlers, "has_access", new=AsyncMock(return_value=True)):
            await handlers.my_paypals_list(self.callback("my_paypals_list:closed:0", user_id=1))
        text = self.render.await_args.args[2]
        self.assertIn(f"Заявка #{req.id}", text)
        self.assertIn("Начисление отменено", text)
        self.assertNotIn("К выплате:", text)
        self.assertNotIn("GeS", text)

    async def test_refund_invalidates_prepared_check_before_delivery(self):
        req = await self.payment()
        await self.payment(amount=200)
        state = self.state()
        await handlers.manual_payout_start_handler(self.callback("manual_payout_start:1"), state)
        await db.refund_confirmed_payment(req.id, 999)
        message = self.check_message()
        await handlers.manual_payout_check_handler(message, state)
        message.send_copy.assert_not_awaited()
        self.assertIn("Чек не отправлен", message.answer.await_args.args[0])
        self.assertEqual((await db.get_user_balance(1))["available"], 100)
        self.assertEqual(await db.list_manual_payouts(1), [])

    async def test_updated_check_pays_only_remaining_entries_and_blocks_late_refund(self):
        cancelled = await self.payment()
        remaining = await self.payment(amount=200)
        await db.refund_confirmed_payment(cancelled.id, 999)
        state = self.state()
        await handlers.manual_payout_start_handler(self.callback("manual_payout_start:1"), state)
        message = self.check_message()
        await handlers.manual_payout_check_handler(message, state)
        message.send_copy.assert_awaited_once_with(chat_id=1)
        payouts = await db.list_manual_payouts(1)
        self.assertEqual(len(payouts), 1)
        self.assertEqual(payouts[0].total_amount, 100)
        self.assertEqual((await db.get_request(cancelled.id)).status, "payment_refunded")
        self.assertEqual((await db.get_request(remaining.id)).status, "paid_out")
        self.assertEqual((await db.refund_confirmed_payment(remaining.id, 999))[1], "already_paid")

    async def test_delivery_failure_rolls_back_payout_and_allows_refund(self):
        req = await self.payment()
        details = await db.get_payout_user_details(1)
        send = AsyncMock(side_effect=RuntimeError("simulated network failure"))
        with self.assertRaises(RuntimeError):
            await db.complete_manual_payout(
                1, 999, expected_entries=db.payout_entries_snapshot(details["entries"]),
                expected_provider="cryptobot", deliver_check=send,
            )
        self.assertEqual(await db.list_manual_payouts(1), [])
        self.assertEqual((await db.get_payment_balance_entry(req.id)).status, "available")
        self.assertEqual((await db.refund_confirmed_payment(req.id, 999))[1], "refunded")

    async def test_equal_total_with_different_entries_and_changed_provider_invalidate_check(self):
        req = await self.payment()
        details = await db.get_payout_user_details(1)
        snapshot = db.payout_entries_snapshot(details["entries"])
        await db.refund_confirmed_payment(req.id, 999)
        await self.payment()  # Same total, different payment: do not use stale check.
        send = AsyncMock()
        self.assertIsNone(await db.complete_manual_payout(1, 999, expected_entries=snapshot, deliver_check=send))
        send.assert_not_awaited()
        details = await db.get_payout_user_details(1)
        await db.set_user_payout_method(1, "xrocket")
        self.assertIsNone(await db.complete_manual_payout(
            1, 999, expected_entries=db.payout_entries_snapshot(details["entries"]),
            expected_provider="cryptobot", deliver_check=send,
        ))
        send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
