"""Personal home and minimum request policy, with SQLite and mocked Telegram."""
import unittest
from contextlib import ExitStack
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from test_paypal_history import TelegramScreen
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db, handlers, keyboards, ui


class PersonalHomeMinimumTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(db, "SessionLocal", self.sessions))
        self.stack.enter_context(patch.object(handlers, "settings", SimpleNamespace(admin_ids=[])))
        self.stack.enter_context(patch.object(handlers, "is_admin", side_effect=lambda uid: uid == 999))
        self.storage = MemoryStorage()
        self.state = FSMContext(storage=self.storage, key=StorageKey(bot_id=99, chat_id=1, user_id=1))
        async with self.sessions() as session:
            session.add_all([
                db.User(id=1, username="member", status="approved"),
                db.User(id=2, username="other", status="approved"),
                db.PaypalTag(tag="@Available", status="available", gender="male"),
                db.RateRule(min_amount=50, percent=60), db.RateRule(min_amount=100, percent=70),
                db.AppSetting(key="content_home_text", value="Old welcome"),
                db.AppSetting(key="content_home_image", value="OLD_PHOTO_ID"),
                db.AppSetting(key="content_paypal_text", value="Old request prompt"),
                db.AppSetting(key="work_enabled", value="1"),
            ])
            await session.commit()
        async with self.engine.begin() as conn:
            await db._migrate_personal_home(conn)

    async def asyncTearDown(self):
        await self.storage.close()
        self.stack.close()
        await self.engine.dispose()

    def message(self, text="40", user_id=1):
        return SimpleNamespace(
            text=text, from_user=SimpleNamespace(id=user_id, username="member", full_name="Member"),
            photo=[SimpleNamespace(file_id="TEST_SCREENSHOT")], answer=AsyncMock(),
            answer_photo=AsyncMock(), bot=SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock()),
        )

    def callback(self, data, user_id=1):
        return SimpleNamespace(data=data, from_user=SimpleNamespace(id=user_id),
                               answer=AsyncMock(), message=self.message(user_id=user_id))

    async def request_count(self):
        async with self.sessions() as session:
            return await session.scalar(select(func.count()).select_from(db.Request))

    async def add_history(self):
        async with self.sessions() as session:
            session.add_all([
                db.Request(id=1, user_id=1, amount=40, status="paypal_issued", paypal_tag_id=1),
                db.Request(id=2, user_id=1, amount=50, status="waiting_check", paypal_tag_id=1),
                db.Request(id=3, user_id=1, amount=50, status="waiting_issue"),
                db.Request(id=4, user_id=1, amount=100, status="withdrawal_pending", paypal_tag_id=1),
                db.Request(id=5, user_id=1, amount=100, status="payout_pending", paypal_tag_id=1),
                db.Request(id=6, user_id=1, amount=100, status="paid_out", paypal_tag_id=1),
                db.Request(id=7, user_id=1, amount=100, status="payment_refunded", paypal_tag_id=1),
                db.Request(id=8, user_id=2, amount=100, status="paypal_issued", paypal_tag_id=1),
                db.Request(id=9, user_id=2, amount=100, status="payout_pending", paypal_tag_id=1),
            ])
            await session.flush()
            session.add_all([
                db.BalanceEntry(user_id=1, request_id=4, amount=Decimal("120.45"), status="held"),
                db.BalanceEntry(user_id=1, request_id=5, amount=Decimal("70.50"), status="available"),
                db.BalanceEntry(user_id=1, request_id=6, amount=500, status="paid"),
                db.BalanceEntry(user_id=1, request_id=7, amount=300, status="cancelled"),
                db.BalanceEntry(user_id=2, request_id=9, amount=900, status="available"),
            ])
            await session.commit()

    async def test_summary_separates_held_available_paid_and_other_users(self):
        await self.add_history()
        self.assertEqual(await db.get_user_home_summary(1), {
            "working": 1, "held": Decimal("120.45"), "available": Decimal("70.50"),
        })
        self.assertEqual(await db.get_user_home_summary(99), {"working": 0, "held": 0, "available": 0})

    async def test_home_renders_real_values_and_updates_when_reopened(self):
        await self.add_history()
        screen = TelegramScreen()
        callback = screen.callback("home")
        callback.from_user = SimpleNamespace(id=1, username="member", full_name="Member")
        await handlers.show_home(callback)
        caption, markup = screen.delivered[-1]
        for value in ("1 PayPal", "120.45 USDT", "70.50 USDT", "Работа открыта"):
            self.assertIn(value, caption)
        self.assertNotIn("%", caption)
        self.assertNotIn("900", caption)
        self.assertNotIn("{available}", caption)
        self.assertEqual([len(row) for row in markup.inline_keyboard], [1, 2, 2, 1])
        async with self.sessions() as session:
            entry = await session.scalar(select(db.BalanceEntry).where(db.BalanceEntry.request_id == 4))
            entry.status = "available"
            await session.commit()
        await db.set_work_enabled(False)
        await handlers.show_home(callback)
        caption = screen.delivered[-1][0]
        self.assertIn("190.95 USDT", caption)
        self.assertIn("0.00 USDT", caption)
        self.assertIn("Новые заявки временно закрыты", caption)

    async def test_unapproved_user_cannot_see_summary(self):
        async with self.sessions() as session:
            user = await session.get(db.User, 1)
            user.status = "pending"
            await session.commit()
        screen = TelegramScreen()
        callback = screen.callback("home")
        callback.from_user = SimpleNamespace(id=1, username="member", full_name="Member")
        with patch.object(handlers, "get_user_home_summary", new_callable=AsyncMock) as summary:
            await handlers.show_home(callback)
            summary.assert_not_awaited()
        self.assertIn("подать заявку на вступление", screen.delivered[-1][0])

    async def test_home_migration_backs_up_content_and_does_not_reset_later_edits(self):
        self.assertEqual(await db.get_app_setting("content_home_text_before_v2521"), "Old welcome")
        self.assertEqual(await db.get_app_setting("content_home_image_before_v2521"), "OLD_PHOTO_ID")
        self.assertEqual(await db.get_app_setting("content_home_image"), "")
        self.assertEqual(await db.get_app_setting("content_home_text"), ui.HOME_SUMMARY_TEMPLATE)
        await db.set_app_setting("content_home_text", "My text {available}")
        await db.set_app_setting("content_home_image", "NEW_PHOTO_ID")
        await db.upsert_rate_rule(40, 55)
        async with self.engine.begin() as conn:
            await db._migrate_personal_home(conn)
        self.assertEqual(await db.get_app_setting("content_home_text"), "My text {available}")
        self.assertEqual(await db.get_app_setting("content_home_image"), "NEW_PHOTO_ID")
        self.assertEqual((await db.get_rate_for_amount(40))[0], 55)

    async def test_rates_are_not_in_request_prompt_or_minimum_error(self):
        await db.upsert_rate_rule(40, 52)
        self.assertNotIn("%", await handlers._minimum_paypal_notice())
        self.assertIn("40 €", await handlers._minimum_paypal_notice())
        self.assertNotIn("Минимум", await handlers._paypal_amount_prompt())
        self.assertNotIn("%", await handlers._paypal_amount_prompt())
        await db.set_app_setting("content_paypal_text", "Custom instructions")
        self.assertEqual(await handlers._paypal_amount_prompt(), "Custom instructions")

    async def test_rate_boundaries_and_40_euro_real_accrual(self):
        for amount, percent in ((40, 50), (49, 50), (50, 60), (99, 60), (100, 70)):
            self.assertEqual((await db.get_rate_for_amount(amount))[0], percent)
        req = await db.create_request(1, 40)
        req, tag = await db.issue_paypal(req.id)
        self.assertIsNotNone(tag)
        self.assertTrue(await db.mark_paid_by_user(req.id, 1))
        req = await db.confirm_payment(req.id, 999)
        self.assertEqual((req.payout_percent, req.payout_amount), (50, Decimal("20.00")))
        summary = await db.get_user_home_summary(1)
        self.assertEqual((summary["working"], summary["held"], summary["available"]), (0, 20, 0))
        await db.mark_paypal_withdrawn(req.id, 999)
        summary = await db.get_user_home_summary(1)
        self.assertEqual((summary["held"], summary["available"]), (0, 20))

    async def test_under_minimum_input_keeps_amount_step_and_creates_nothing(self):
        for value in ("0", "1", "39", " 39 € ", "00000039", "-1"):
            with self.subTest(value=value):
                await self.state.set_state(handlers.PaypalRequestForm.amount)
                message = self.message(value)
                await handlers.paypal_amount_input(message, self.state)
                response = message.answer.await_args.args[0]
                self.assertIn("40 €", response)
                self.assertNotIn("%", response)
                self.assertEqual(await self.state.get_state(), handlers.PaypalRequestForm.amount.state)
                self.assertEqual(await self.request_count(), 0)
        self.assertEqual((await db.get_paypal_tag(1)).status, "available")

    async def test_valid_amounts_move_to_gender_without_creating_request(self):
        for amount in (40, 49, 50, 99, 100, 100000):
            await self.state.clear()
            await self.state.set_state(handlers.PaypalRequestForm.amount)
            await handlers.paypal_amount_input(self.message(str(amount)), self.state)
            self.assertEqual(await self.state.get_state(), handlers.PaypalRequestForm.gender.state)
            self.assertEqual((await self.state.get_data())["amount"], amount)
            self.assertEqual(await self.request_count(), 0)

    async def test_bad_numeric_input_cannot_crash_or_advance(self):
        for value in ("", "²", "40.5", "100001", "9" * 5000, "-1", "text"):
            await self.state.set_state(handlers.PaypalRequestForm.amount)
            message = self.message(value)
            await handlers.paypal_amount_input(message, self.state)
            message.answer.assert_awaited_once()
            self.assertEqual(await self.state.get_state(), handlers.PaypalRequestForm.amount.state)
        self.assertEqual(await self.request_count(), 0)

    async def test_stale_gender_step_below_40_returns_to_amount(self):
        await self.state.set_state(handlers.PaypalRequestForm.gender)
        await self.state.update_data(amount=39)
        callback = self.callback("request_gender:male")
        await handlers.paypal_gender_choice(callback, self.state)
        self.assertEqual(await self.state.get_state(), handlers.PaypalRequestForm.amount.state)
        self.assertIn("40 €", callback.message.answer.await_args.args[0])
        self.assertNotIn("%", callback.message.answer.await_args.args[0])
        self.assertEqual(await self.request_count(), 0)

    async def test_stale_screenshot_cannot_create_or_auto_issue_below_minimum(self):
        await db.set_auto_issue_enabled(True)
        for value in (39, None, "40", 40.5):
            await self.state.set_state(handlers.PaypalRequestForm.screenshot)
            await self.state.update_data(amount=value, paypal_gender="male")
            message = self.message()
            await handlers.paypal_screenshot_input(message, self.state)
            self.assertEqual(await self.state.get_state(), handlers.PaypalRequestForm.amount.state)
            self.assertIn("40 €", message.answer.await_args.args[0])
            message.bot.send_photo.assert_not_awaited()
            self.assertEqual(await self.request_count(), 0)
        self.assertEqual((await db.get_paypal_tag(1)).status, "available")

    async def test_40_euros_can_be_auto_issued_after_screenshot(self):
        await db.set_auto_issue_enabled(True)
        await self.state.set_state(handlers.PaypalRequestForm.screenshot)
        await self.state.update_data(amount=40, paypal_gender="male")
        message = self.message()
        with patch.object(handlers.asyncio, "sleep", new_callable=AsyncMock):
            await handlers.paypal_screenshot_input(message, self.state)
        self.assertEqual(await self.request_count(), 1)
        self.assertEqual((await db.get_request(1)).status, "paypal_issued")
        self.assertEqual((await db.get_paypal_tag(1)).issued_to_user_id, 1)
        message.bot.send_photo.assert_awaited_once()
        self.assertIsNone(await self.state.get_state())

    async def test_40_euros_enters_manual_queue_when_auto_is_off(self):
        await self.state.set_state(handlers.PaypalRequestForm.screenshot)
        await self.state.update_data(amount=40, paypal_gender="male")
        await handlers.paypal_screenshot_input(self.message(), self.state)
        self.assertEqual((await db.get_request(1)).status, "waiting_issue")
        self.assertEqual((await db.get_paypal_tag(1)).status, "available")

    async def test_database_entry_points_enforce_minimum(self):
        for amount in (0, 39, -1, 100001, 40.5, "40", None):
            req, result = await db.create_request_with_work_limit(1, amount)
            self.assertIsNone(req)
            self.assertEqual(result["reason"], "invalid_amount")
            with self.assertRaises(ValueError):
                await db.create_request(1, amount)
        self.assertEqual(await self.request_count(), 0)

    async def test_old_under_minimum_queue_cannot_be_issued_manually(self):
        async with self.sessions() as session:
            session.add(db.Request(id=1, user_id=1, amount=39, status="waiting_issue"))
            await session.commit()
        req, tag = await db.issue_paypal(1)
        self.assertEqual(req.status, "waiting_issue")
        self.assertIsNone(tag)
        callback = self.callback("admin_issue:1", user_id=999)
        await handlers.admin_issue(callback)
        self.assertIn("40", callback.answer.await_args.args[0])
        self.assertEqual((await db.get_paypal_tag(1)).status, "available")

    async def test_long_custom_home_uses_text_without_deleting_menu_first(self):
        screen = TelegramScreen()
        callback = screen.callback("home")
        callback.from_user = SimpleNamespace(id=1, username="member", full_name="Member")
        await db.set_app_setting("content_home_text", "Текст " * 200 + "{available}")
        await handlers.show_home(callback)
        self.assertIn("send_message", screen.events)
        self.assertLess(screen.events.index("send_message"), screen.events.index("delete"))
        self.assertIn("0.00", screen.delivered[-1][0])

    async def test_existing_75_percent_rule_changes_to_70_without_recalculating_accruals(self):
        await db.upsert_rate_rule(100, 75)
        async with self.sessions() as session:
            session.add(db.Request(id=100, user_id=1, amount=100, status="withdrawal_pending",
                                   payout_percent=75, payout_amount=75))
            await session.flush()
            session.add(db.BalanceEntry(user_id=1, request_id=100, amount=75, status="held"))
            await session.commit()
        async with self.engine.begin() as conn:
            await db._migrate_home_rates_v2522(conn)
        for amount, percent in ((40, 50), (49, 50), (50, 60), (99, 60), (100, 70), (200, 70)):
            self.assertEqual((await db.get_rate_for_amount(amount))[0], percent)
        self.assertEqual(await db.get_app_setting("rate_100_before_v2522"), "75")
        self.assertEqual((await db.get_request(100)).payout_percent, 75)
        self.assertEqual((await db.get_payment_balance_entry(100)).amount, 75)
        new = await db.create_request(1, 100)
        await db.issue_paypal(new.id)
        await db.mark_paid_by_user(new.id, 1)
        confirmed = await db.confirm_payment(new.id, 999)
        self.assertEqual((confirmed.payout_percent, confirmed.payout_amount), (70, Decimal("70.00")))

    async def test_rate_cleanup_preserves_custom_text_and_is_one_time(self):
        await db.upsert_rate_rule(100, 75)
        await db.set_app_setting("content_home_text", "Моя сводка\n{available}\n\n{rates}")
        await db.set_app_setting("content_paypal_text", "Введите сумму.\n\n{minimum}\n\nМой текст")
        async with self.engine.begin() as conn:
            await db._migrate_home_rates_v2522(conn)
        self.assertEqual(await db.get_app_setting("content_home_text"), "Моя сводка\n{available}")
        self.assertEqual(await handlers._paypal_amount_prompt(), "Введите сумму.\n\nМой текст")
        self.assertIn("{rates}", await db.get_app_setting("content_home_text_before_v2522"))
        await db.upsert_rate_rule(100, 72)
        await db.set_app_setting("content_home_text", "Поздняя правка")
        async with self.engine.begin() as conn:
            await db._migrate_home_rates_v2522(conn)
        self.assertEqual((await db.get_rate_for_amount(100))[0], 72)
        self.assertEqual(await db.get_app_setting("content_home_text"), "Поздняя правка")
        self.assertEqual(await db.get_app_setting("rate_100_before_v2522"), "75")

    async def test_legacy_placeholders_never_leak_into_user_screens(self):
        await db.set_app_setting("content_home_text", ui.HOME_SUMMARY_TEMPLATE + "\n\n{rates}")
        await db.set_app_setting("content_paypal_text", "Введите сумму\n\n{minimum}")
        self.assertEqual(await handlers._paypal_amount_prompt(), "Введите сумму")
        screen = TelegramScreen()
        callback = screen.callback("home")
        callback.from_user = SimpleNamespace(id=1, username="member", full_name="Member")
        with patch.object(handlers, "list_rate_rules", new_callable=AsyncMock) as rates:
            await handlers.show_home(callback)
            rates.assert_not_awaited()
        self.assertNotIn("%", screen.delivered[-1][0])
        self.assertNotIn("{rates}", screen.delivered[-1][0])


if __name__ == "__main__":
    unittest.main()
