"""Offline regression tests: python -m unittest discover -s tests -v."""
import os
import re
import unittest
from contextlib import ExitStack
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Import the application with dummy settings; no real services are contacted.
os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NO_NETWORK"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1/test"
os.environ["ADMIN_IDS"] = ""

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db, handlers


def rendered_length(text):
    class TextParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    parser = TextParser()
    parser.feed(text)
    return len("".join(parser.parts).encode("utf-16-le")) // 2


def request(request_id, status="paid_out", **overrides):
    values = dict(
        id=request_id, user_id=42, amount=150, status=status,
        paypal_tag_id=request_id, payout_amount=Decimal("75.00"),
        updated_at=datetime(2026, 10, 13),
        admin_result_screenshot_file_id=None, happy_hours_applied=0,
        happy_hours_percent=None, happy_hours_campaign_id=None,
        payout_percent=50,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class TelegramScreen:
    """Emulates Telegram length limits and records destructive UI actions."""
    def __init__(self, photo=True):
        self.events = []
        self.delivered = []
        self.fail_edit = None
        self.fail_send = False
        self.message = SimpleNamespace(
            photo=[1] if photo else [], chat=SimpleNamespace(id=42),
            edit_media=self.edit_media, edit_text=self.edit_text,
            delete=self.delete,
        )
        self.bot = SimpleNamespace(
            send_message=self.send_message, send_photo=self.send_photo,
        )

    def error(self, text):
        return TelegramBadRequest(
            method=SendMessage(chat_id=42, text="test"), message=text,
        )

    def record(self, action, text, markup, photo):
        self.events.append(action)
        if action.startswith("edit") and self.fail_edit:
            raise self.error(self.fail_edit)
        if action.startswith("send") and self.fail_send:
            raise self.error("simulated send failure")
        maximum = 1024 if photo else 4096
        if rendered_length(text) > maximum:
            raise self.error("message caption is too long" if photo else "message is too long")
        self.delivered.append((text, markup))
        self.message.photo = [1] if photo else []
        return self.message

    async def edit_media(self, media, reply_markup=None):
        return self.record("edit_media", media.caption, reply_markup, True)

    async def edit_text(self, text, reply_markup=None):
        return self.record("edit_text", text, reply_markup, False)

    async def send_message(self, chat_id, text, reply_markup=None):
        return self.record("send_message", text, reply_markup, False)

    async def send_photo(self, chat_id, photo, caption, reply_markup=None):
        return self.record("send_photo", caption, reply_markup, True)

    async def delete(self):
        self.events.append("delete")

    def callback(self, data="my_paypals_list:paid"):
        return SimpleNamespace(
            data=data, from_user=SimpleNamespace(id=42), message=self.message,
            bot=self.bot, answer=AsyncMock(),
        )


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rows = [request(i) for i in range(33, 0, -1)]
        self.tag = "@ExamplePayPal123"
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

        async def count(user_id, statuses):
            return len([r for r in self.rows if r.user_id == user_id and r.status in statuses])

        async def fetch(user_id, statuses, limit=50, offset=0):
            rows = [r for r in self.rows if r.user_id == user_id and r.status in statuses]
            return rows[offset:offset + limit]

        async def tag(tag_id):
            return SimpleNamespace(tag=self.tag)

        for name, replacement in {
            "has_access": AsyncMock(return_value=True),
            "count_user_requests_by_statuses": count,
            "get_user_requests_by_statuses": fetch,
            "get_paypal_tag": tag,
            "get_happy_hours_campaign": AsyncMock(return_value=None),
        }.items():
            self.stack.enter_context(patch.object(handlers, name, replacement))

    async def test_all_records_are_reachable_for_33_100_200_and_1001_requests(self):
        for total in (33, 100, 200, 1001):
            with self.subTest(total=total):
                self.rows = [request(i) for i in range(total, 0, -1)]
                screen = TelegramScreen()
                data = "my_paypals_list:paid"  # Existing buttons must still work.
                seen = []
                pages = []
                while True:
                    callback = screen.callback(data)
                    await handlers.my_paypals_list(callback)
                    callback.answer.assert_awaited_once()
                    text, markup = screen.delivered[-1]
                    ids = list(map(int, re.findall(r"Заявка #(\d+)", text)))
                    seen.extend(ids)
                    pages.append(ids)
                    next_buttons = [b for row in markup.inline_keyboard for b in row if b.text == "Далее ➡️"]
                    if not next_buttons:
                        break
                    data = next_buttons[0].callback_data
                    self.assertLess(len(seen), total + 1)
                self.assertEqual(seen, list(range(total, 0, -1)))
                self.assertIn(f"–{total} из {total}", text)
                for expected in reversed(pages[:-1]):
                    back = next(b for row in markup.inline_keyboard for b in row if b.text == "⬅️ Назад")
                    await handlers.my_paypals_list(screen.callback(back.callback_data))
                    text, markup = screen.delivered[-1]
                    self.assertEqual(list(map(int, re.findall(r"Заявка #(\d+)", text))), expected)
                self.assertFalse(any(b.text == "⬅️ Назад" for row in markup.inline_keyboard for b in row))

    async def test_category_count_is_not_capped_at_1000(self):
        self.rows = [request(i) for i in range(1, 1002)]
        screen = TelegramScreen()
        with patch.object(handlers, "get_user_profit_summary", AsyncMock(return_value={"pending": 0})):
            await handlers.my_paypals(screen.callback("my_paypals"))
        _, markup = screen.delivered[-1]
        self.assertIn("✅ Выплаченные (1001)", [b.text for row in markup.inline_keyboard for b in row])

    async def test_long_unicode_tags_and_payment_details_fit_text_page(self):
        self.tag = "😀" * 250 + "<&>ab"  # Maximum DB tag length: 255.
        self.rows = [request(
            i, amount=2147483647, payout_amount=Decimal("9999999999.99"),
            admin_result_screenshot_file_id="test", happy_hours_applied=1,
        ) for i in range(2147483647, 2147483642, -1)]
        screen = TelegramScreen()
        await handlers.my_paypals_list(screen.callback())
        text, _ = screen.delivered[-1]
        self.assertLessEqual(rendered_length(text), 4096)
        self.assertIn("&lt;&amp;&gt;ab", text)
        self.assertIn("Happy Hours применён", text)
        self.assertEqual(screen.events, ["send_message", "delete"])

    async def test_empty_history_and_stale_page_remain_navigable(self):
        self.rows = []
        screen = TelegramScreen()
        await handlers.my_paypals_list(screen.callback("my_paypals_list:paid:9999"))
        text, markup = screen.delivered[-1]
        self.assertIn("пока нет заявок", text)
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "my_paypals")
        self.rows = [request(1)]
        await handlers.my_paypals_list(screen.callback("my_paypals_list:paid:9999"))
        self.assertIn("Показаны 1–1 из 1", screen.delivered[-1][0])

    async def test_invalid_page_does_not_touch_current_screen(self):
        screen = TelegramScreen()
        callback = screen.callback("my_paypals_list:paid:bad")
        await handlers.my_paypals_list(callback)
        callback.answer.assert_awaited_once_with("Страница не найдена", show_alert=True)
        self.assertEqual(screen.events, [])

    async def test_other_history_categories_and_waiting_actions(self):
        for group, (statuses, _) in handlers.MY_PAYPAL_GROUPS.items():
            with self.subTest(group=group):
                self.rows = [request(i, statuses[0]) for i in range(1, 10)]
                screen = TelegramScreen()
                await handlers.my_paypals_list(screen.callback(f"my_paypals_list:{group}"))
                text, markup = screen.delivered[-1]
                if group == "waiting":
                    actions = [b.callback_data for row in markup.inline_keyboard for b in row]
                    self.assertEqual(len([a for a in actions if a.startswith("my_paypal_card:")]), 9)
                else:
                    self.assertEqual(len(re.findall(r"Заявка #", text)), 4)


class RenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_text_send_keeps_photo_menu(self):
        screen = TelegramScreen()
        screen.fail_send = True
        with self.assertRaises(TelegramBadRequest):
            await handlers.render_screen(screen.callback(), "requests", "x" * 1200)
        self.assertNotIn("delete", screen.events)

    async def test_failed_photo_edit_and_send_keep_old_menu(self):
        screen = TelegramScreen()
        screen.fail_edit = "message can't be edited"
        screen.fail_send = True
        with self.assertRaises(TelegramBadRequest):
            await handlers.render_screen(screen.callback(), "requests", "short")
        self.assertEqual(screen.events, ["edit_media", "send_photo"])

    async def test_replacement_is_sent_before_old_menu_is_deleted(self):
        screen = TelegramScreen()
        screen.fail_edit = "message can't be edited"
        await handlers.render_screen(screen.callback(), "requests", "short")
        self.assertEqual(screen.events, ["edit_media", "send_photo", "delete"])

    async def test_unchanged_text_or_photo_does_not_delete_or_resend(self):
        for photo, text in ((True, "short"), (False, "x" * 1200)):
            with self.subTest(photo=photo):
                screen = TelegramScreen(photo)
                screen.fail_edit = "Bad Request: message is not modified"
                result = await handlers.render_screen(screen.callback(), "requests", text)
                self.assertIs(result, screen.message)
                self.assertEqual(len(screen.events), 1)

    async def test_caption_boundary_and_long_text_navigation(self):
        screen = TelegramScreen()
        await handlers.render_screen(screen.callback(), "requests", "x" * 1024)
        self.assertEqual(screen.events, ["edit_media"])
        await handlers.render_screen(screen.callback(), "requests", "x" * 1025)
        self.assertEqual(screen.events[-2:], ["send_message", "delete"])
        await handlers.render_screen(screen.callback(), "requests", "y" * 1025)
        self.assertEqual(screen.events[-1], "edit_text")
        await handlers.render_screen(screen.callback(), "requests", "short")
        self.assertEqual(screen.events[-2:], ["send_photo", "delete"])


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_pages_and_counts_are_scoped_to_user_and_status(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(db.Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session:
                session.add_all([db.User(id=42), db.User(id=43)])
                session.add_all([
                    db.Request(id=i, user_id=42, amount=100, status="paid_out",
                               updated_at=datetime(2026, 10, 13))
                    for i in range(1, 201)
                ])
                session.add(db.Request(id=201, user_id=43, amount=100, status="paid_out"))
                session.add(db.Request(id=202, user_id=42, amount=100, status="waiting_check"))
                await session.commit()
            with patch.object(db, "SessionLocal", sessions):
                self.assertEqual(await db.count_user_requests_by_statuses(42, ("paid_out",)), 200)
                seen = []
                for offset in range(0, 204, 4):
                    rows = await db.get_user_requests_by_statuses(42, ("paid_out",), limit=4, offset=offset)
                    seen.extend(r.id for r in rows)
                self.assertEqual(seen, list(range(200, 0, -1)))
                self.assertEqual(await db.count_user_requests_by_statuses(99, ("paid_out",)), 0)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
