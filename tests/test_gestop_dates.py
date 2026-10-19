"""Gestop archive regression tests; no Telegram or production DB connection."""
import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NO_NETWORK"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1/test"
os.environ["ADMIN_IDS"] = ""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db, handlers


class GestopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.session_patch = patch.object(db, "SessionLocal", self.sessions)
        self.session_patch.start()
        self.admin_patch = patch.object(handlers, "is_admin", return_value=True)
        self.admin_patch.start()
        self.render_patch = patch.object(handlers, "render_screen", new_callable=AsyncMock)
        self.render = self.render_patch.start()
        async with self.sessions() as session:
            session.add(db.User(id=1))
            await session.commit()

    async def asyncTearDown(self):
        self.render_patch.stop()
        self.admin_patch.stop()
        self.session_patch.stop()
        await self.engine.dispose()

    def add_tag(self, session, tag_id, at=None, status="gestoppt", source=None):
        tag = db.PaypalTag(
            id=tag_id, tag=f"@Test{tag_id}", status=status,
            gestop_at=at, gestop_date_source=source,
            created_at=datetime(2020, 1, 1),
        )
        session.add(tag)
        return tag

    def add_request(self, session, tag_id, status, at=None, updated=None):
        session.add(db.Request(
            id=tag_id, user_id=1, paypal_tag_id=tag_id, amount=100,
            status=status, processed_at=at,
            updated_at=updated or at or datetime(2026, 10, 1),
        ))

    def callback(self, data):
        return SimpleNamespace(data=data, from_user=SimpleNamespace(id=999), answer=AsyncMock())

    def last_screen(self):
        return self.render.await_args.args[2:4]

    async def test_full_current_archive_over_50_and_card_returns_to_same_page(self):
        base = datetime(2026, 10, 1, 12)
        async with self.sessions() as session:
            for tag_id in range(1, 201):
                self.add_tag(session, tag_id, base + timedelta(seconds=201 - tag_id), source="exact")
            self.add_tag(session, 201)
            self.add_tag(session, 202)
            for tag_id, status in enumerate(("available", "deleted", "gs", "issued", "return_pending"), 203):
                self.add_tag(session, tag_id, base - timedelta(days=30), status=status)
            await session.commit()

        await handlers.paypal_db_list_handler(self.callback("paypal_db_list:gestoppt:0"))
        text, _ = self.last_screen()
        self.assertIn("Всего текущих Gestop: <b>202</b>", text)
        self.assertIn("Без сохранённой даты: <b>2</b>", text)

        seen = []
        data = "gestop_list:all:0:0"
        saved_card = None
        while True:
            callback = self.callback(data)
            await handlers.gestop_list_handler(callback)
            callback.answer.assert_awaited_once()
            text, markup = self.last_screen()
            buttons = [button for row in markup.inline_keyboard for button in row]
            for button in buttons:
                self.assertLessEqual(len(button.callback_data.encode()), 64)
            cards = [button for button in buttons if button.callback_data.startswith("gestop_card:")]
            seen.extend(int(button.callback_data.split(":")[1]) for button in cards)
            if data == "gestop_list:all:60:0":
                saved_card = cards[0].callback_data
            next_buttons = [button for button in buttons if button.text == "Далее ➡️"]
            if not next_buttons:
                break
            data = next_buttons[0].callback_data
            self.assertLess(len(seen), 203)
        self.assertEqual(seen, list(range(200, 0, -1)) + [201, 202])
        self.assertIn("из 202", text)
        await handlers.gestop_card_handler(self.callback(saved_card))
        _, markup = self.last_screen()
        self.assertEqual(markup.inline_keyboard[-1][0].callback_data, "gestop_list:all:60:0")

    async def test_date_groups_are_paginated_oldest_first_unknown_last(self):
        base = datetime(2026, 9, 1)
        async with self.sessions() as session:
            for tag_id in range(1, 34):
                self.add_tag(session, tag_id, base + timedelta(days=33 - tag_id))
            self.add_tag(session, 34)
            await session.commit()
        seen = []
        offset = 0
        while True:
            data = await db.get_gestop_date_groups(offset)
            self.assertEqual(data["total"], 34)
            seen.extend(day for day, _ in data["rows"])
            if not data["has_next"]:
                break
            offset += data["page_size"]
        expected = [(base + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(33)]
        self.assertEqual(seen, expected + ["unknown"])
        stale = await db.get_gestop_date_groups(9999)
        self.assertEqual(stale["offset"], 30)
        self.assertEqual(stale["rows"][-1], ("unknown", 1))

    async def test_moscow_midnight_and_unknown_day_filters(self):
        async with self.sessions() as session:
            for tag_id, at in enumerate((
                datetime(2026, 10, 18, 20, 59, 59),
                datetime(2026, 10, 18, 21),
                datetime(2026, 10, 19, 20, 59, 59),
                datetime(2026, 10, 19, 21),
                None,
            ), 1):
                self.add_tag(session, tag_id, at)
            await session.commit()
        groups = await db.get_gestop_date_groups()
        self.assertEqual(groups["rows"], [("2026-10-18", 1), ("2026-10-19", 2), ("2026-10-20", 1), ("unknown", 1)])
        page = await db.list_gestop_tags("2026-10-19")
        self.assertEqual([tag.id for tag in page["rows"]], [2, 3])
        unknown = await db.list_gestop_tags("unknown")
        self.assertEqual([tag.id for tag in unknown["rows"]], [5])

    async def test_old_dates_are_backfilled_once_only_with_evidence(self):
        base = datetime(2026, 9, 1)
        async with self.sessions() as session:
            for tag_id in range(1, 8):
                self.add_tag(session, tag_id)
            self.add_tag(session, 8, status="available")
            self.add_tag(session, 9, base, source="exact")
            self.add_request(session, 1, "paypal_limited", base + timedelta(days=1), base + timedelta(days=10))
            self.add_request(session, 2, "admin_recalled_gestoppt", base + timedelta(days=2))
            self.add_request(session, 3, "payment_returned", base + timedelta(days=3))
            self.add_request(session, 4, "returned_gestoppt", updated=base + timedelta(days=20))
            session.add(db.PaypalReturn(
                request_id=4, user_id=1, paypal_tag_id=4, reason_code="gestop", reason_text="test",
                status="gestoppt", resolved_at=base + timedelta(days=4),
            ))
            self.add_request(session, 5, "returned_gestoppt", updated=base + timedelta(days=5))
            self.add_request(session, 6, "paid_out", base + timedelta(days=6))
            self.add_request(session, 8, "paypal_limited", base + timedelta(days=8))
            self.add_request(session, 9, "paypal_limited", base + timedelta(days=9))
            await session.commit()
        await db._backfill_gestop_dates()
        for tag_id in range(1, 6):
            tag = await db.get_paypal_tag(tag_id)
            self.assertEqual(tag.gestop_at, base + timedelta(days=tag_id))
            self.assertEqual(tag.gestop_date_source, "history")
            self.assertEqual(tag.status, "gestoppt")
        for tag_id in (6, 7, 8):
            self.assertIsNone((await db.get_paypal_tag(tag_id)).gestop_at)
        known = await db.get_paypal_tag(9)
        self.assertEqual((known.gestop_at, known.gestop_date_source), (base, "exact"))
        await db._backfill_gestop_dates()
        self.assertEqual((await db.get_paypal_tag(4)).gestop_at, base + timedelta(days=4))
        self.assertEqual((await db.get_paypal_tag(8)).status, "available")

    async def test_every_gestop_entry_path_records_date_without_resetting_it(self):
        now = datetime(2026, 10, 19, 12)
        async with self.sessions() as session:
            self.add_tag(session, 1, status="available")
            self.add_tag(session, 2, status="issued")
            self.add_tag(session, 3, status="return_pending")
            self.add_tag(session, 4, status="issued")
            self.add_tag(session, 5)  # Old Gestop with no known date.
            self.add_request(session, 2, "waiting_check")
            self.add_request(session, 3, "return_pending")
            self.add_request(session, 4, "paypal_issued")
            session.add(db.PaypalReturn(
                id=3, request_id=3, user_id=1, paypal_tag_id=3,
                reason_code="gestop", reason_text="test", status="pending",
            ))
            await session.commit()
        with patch.object(db, "datetime") as clock:
            clock.utcnow.return_value = now
            await db.set_paypal_tag_status(1, "gestoppt")
            await db.mark_payment_problem(2, 999, "dead", "test-photo")
            await db.resolve_paypal_return(3, "gestoppt", 999, "test")
            await db.admin_recall_working_request(4, "gestoppt", 999)
            for tag_id in range(1, 5):
                tag = await db.get_paypal_tag(tag_id)
                self.assertEqual((tag.status, tag.gestop_at, tag.gestop_date_source), ("gestoppt", now, "exact"))
                self.assertEqual(tag.had_gestop, 1)
            clock.utcnow.return_value = now + timedelta(days=1)
            await db.set_paypal_tag_status(1, "gestoppt")
            self.assertEqual((await db.get_paypal_tag(1)).gestop_at, now)
            await db.set_paypal_tag_status(5, "gestoppt")
            self.assertIsNone((await db.get_paypal_tag(5)).gestop_at)
            await db.set_paypal_tag_status(1, "available", expected_status="gestoppt")
            self.assertIsNone(await db.set_paypal_tag_status(1, "available", expected_status="gestoppt"))
            self.assertNotIn(1, [tag.id for tag in (await db.list_gestop_tags())["rows"]])
            await db.set_paypal_tag_status(1, "gestoppt")
            self.assertEqual((await db.get_paypal_tag(1)).gestop_at, now + timedelta(days=1))

    async def test_card_distinguishes_unknown_and_recovered_dates(self):
        async with self.sessions() as session:
            self.add_tag(session, 1)
            tag = self.add_tag(session, 2, datetime(2026, 10, 1), source="history")
            tag.tag = "@Test<&>"
            await session.commit()
        await handlers.gestop_card_handler(self.callback("gestop_card:1:unknown:0:15"))
        text, markup = self.last_screen()
        self.assertIn("Дата Gestop: <b>Дата неизвестна</b>", text)
        self.assertEqual(markup.inline_keyboard[-1][0].callback_data, "gestop_list:unknown:0:15")
        await handlers.gestop_card_handler(self.callback("gestop_card:2:all:0:0"))
        text, _ = self.last_screen()
        self.assertIn("≈ 01.10.2026 03:00 МСК", text)
        self.assertIn("@Test&lt;&amp;&gt;", text)

    async def test_empty_archive_and_stale_card_are_safe(self):
        await handlers.paypal_db_list_handler(self.callback("paypal_db_list:gestoppt:0"))
        self.assertIn("Сейчас в Gestop нет PayPal", self.last_screen()[0])
        callback = self.callback("gestop_card:999:all:195:0")
        await handlers.gestop_card_handler(callback)
        callback.answer.assert_awaited_once_with("Этот PayPal уже не в Gestop", show_alert=True)
        self.assertIn("В этом разделе сейчас нет Gestop", self.last_screen()[0])

    async def test_admin_access_and_invalid_date_validation(self):
        callback = self.callback("gestop_list:2026-02-31:0:0")
        await handlers.gestop_list_handler(callback)
        callback.answer.assert_awaited_once_with("Страница не найдена", show_alert=True)
        self.render.assert_not_awaited()
        with patch.object(handlers, "is_admin", return_value=False):
            for handler, data in (
                (handlers.gestop_dates_handler, "gestop_dates:0"),
                (handlers.gestop_list_handler, "gestop_list:all:0:0"),
                (handlers.gestop_card_handler, "gestop_card:1:all:0:0"),
            ):
                callback = self.callback(data)
                await handler(callback)
                callback.answer.assert_awaited_once_with("Нет доступа", show_alert=True)
        self.render.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
