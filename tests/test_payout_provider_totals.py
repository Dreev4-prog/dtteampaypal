"""Offline payout summary checks using an isolated in-memory database."""
import os
import unittest
from decimal import Decimal
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NO_NETWORK"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1/test"
os.environ["ADMIN_IDS"] = ""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db, handlers


class PayoutProviderTotalsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(db.Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.session_patch = patch.object(db, "SessionLocal", self.sessions)
        self.session_patch.start()
        self.next_entry_id = 0
        async with self.sessions() as session:
            session.add_all([
                db.User(id=1, payout_method="cryptobot"),
                db.User(id=2, payout_method="xrocket"),
                db.User(id=3, payout_method="cryptobot"),
                db.User(id=4, payout_method=""),
                db.User(id=5, payout_method="xrocket"),
            ])
            await session.commit()

    async def asyncTearDown(self):
        self.session_patch.stop()
        await self.engine.dispose()

    def add_entry(self, session, user_id, amount, status="available"):
        self.next_entry_id += 1
        entry_id = self.next_entry_id
        session.add(db.Request(
            id=entry_id, user_id=user_id, amount=100,
            status="paid_out" if status == "paid" else "payout_pending",
            paypal_withdrawn_at=datetime(2026, 10, 1),
        ))
        session.add(db.BalanceEntry(
            id=entry_id, request_id=entry_id, user_id=user_id,
            amount=Decimal(amount), status=status,
        ))

    async def screen_text(self, offset=0):
        callback = SimpleNamespace(
            data=f"payouts_v22:{offset}", from_user=SimpleNamespace(id=999),
            answer=AsyncMock(),
        )
        with patch.object(handlers, "is_admin", return_value=True), patch.object(
            handlers, "replace_photo_with_text", new_callable=AsyncMock,
        ) as render:
            await handlers.payouts_v22_handler(callback)
        callback.answer.assert_awaited_once()
        return render.await_args.args[1], render.await_args.args[2]

    async def test_empty_center_displays_both_zero_balances(self):
        totals = await db.get_payout_dashboard_counts()
        self.assertEqual(totals["users"], 0)
        self.assertEqual(totals["total"], Decimal("0.00"))
        self.assertEqual(totals["cryptobot_total"], Decimal("0.00"))
        self.assertEqual(totals["xrocket_total"], Decimal("0.00"))
        text, _ = await self.screen_text()
        self.assertIn("CryptoBot: <b>0.00 USDT</b>", text)
        self.assertIn("xRocket: <b>0.00 USDT</b>", text)

    async def test_only_available_entries_follow_current_user_preference(self):
        async with self.sessions() as session:
            self.add_entry(session, 1, "100.10")
            self.add_entry(session, 1, "0.20")
            self.add_entry(session, 1, "300.00", status="reserved")
            self.add_entry(session, 2, "42.55")
            self.add_entry(session, 2, "7.45")
            self.add_entry(session, 3, "99.00", status="paid")
            self.add_entry(session, 4, "1.00")  # Existing default: CryptoBot.
            session.add(db.ManualPayout(
                user_id=3, total_amount=Decimal("99.00"),
                provider="cryptobot", admin_id=999,
            ))
            await session.commit()

        totals = await db.get_payout_dashboard_counts()
        self.assertEqual(totals["users"], 3)
        self.assertEqual(totals["total"], Decimal("151.30"))
        self.assertEqual(totals["cryptobot_total"], Decimal("101.30"))
        self.assertEqual(totals["xrocket_total"], Decimal("50.00"))
        self.assertEqual(totals["paid_total"], 99)
        self.assertEqual(totals["paid_count"], 1)

        self.assertTrue(await db.set_user_payout_method(1, "xrocket"))
        totals = await db.get_payout_dashboard_counts()
        self.assertEqual(totals["cryptobot_total"], Decimal("1.00"))
        self.assertEqual(totals["xrocket_total"], Decimal("150.30"))
        self.assertEqual(totals["total"], Decimal("151.30"))

    async def test_completed_payout_is_removed_from_provider_total(self):
        async with self.sessions() as session:
            self.add_entry(session, 1, "5.25")
            self.add_entry(session, 1, "4.75")
            self.add_entry(session, 2, "7.20")
            await session.commit()
        # This only updates the isolated DB; it sends no checks or payments.
        await db.complete_manual_payout(1, admin_id=999)
        totals = await db.get_payout_dashboard_counts()
        self.assertEqual(totals["users"], 1)
        self.assertEqual(totals["cryptobot_total"], Decimal("0.00"))
        self.assertEqual(totals["xrocket_total"], Decimal("7.20"))
        self.assertEqual(totals["total"], Decimal("7.20"))
        self.assertEqual(totals["paid_total"], 10)
        self.assertEqual(totals["paid_count"], 1)

    async def test_200_users_are_counted_on_every_dashboard_page(self):
        async with self.sessions() as session:
            for user_id in range(10, 210):
                session.add(db.User(
                    id=user_id,
                    payout_method="cryptobot" if user_id % 2 == 0 else "xrocket",
                ))
                self.add_entry(session, user_id, "1.11")
            await session.commit()
        for offset in (0, 20, 190):
            with self.subTest(offset=offset):
                text, markup = await self.screen_text(offset)
                self.assertIn("Нужно выплатить: <b>200</b>", text)
                self.assertIn("Общий баланс: <b>222.00 USDT</b>", text)
                self.assertIn("CryptoBot: <b>111.00 USDT</b>", text)
                self.assertIn("xRocket: <b>111.00 USDT</b>", text)
                users_on_page = [
                    button for row in markup.inline_keyboard for button in row
                    if button.callback_data.startswith("payout_user:")
                ]
                self.assertEqual(len(users_on_page), 10)


if __name__ == "__main__":
    unittest.main()
