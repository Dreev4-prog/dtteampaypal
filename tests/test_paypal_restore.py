"""Restore through real handlers and SQLite; Telegram calls remain offline."""
import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from test_paypal_history import TelegramScreen
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db, handlers, keyboards


class RestoreScreen(TelegramScreen):
    def __init__(self, photo=False):
        super().__init__(photo)
        self.message.edit_caption = self.edit_caption
        self.user_notice = AsyncMock()
        self.bot.send_message = self.send_message

    async def edit_caption(self, caption, reply_markup=None):
        if not self.message.photo:
            raise self.error("there is no caption in the message to edit")
        return self.record("edit_caption", caption, reply_markup, True)

    async def send_message(self, chat_id, text, reply_markup=None):
        if chat_id != self.message.chat.id:
            self.events.append("user_notice")
            return await self.user_notice(chat_id, text, reply_markup=reply_markup)
        return await super().send_message(chat_id, text, reply_markup)

    def callback(self, data, user_id=999):
        callback = super().callback(data)
        callback.from_user.id = user_id
        callback.answer.side_effect = lambda *args, **kwargs: self.events.append("answer")
        return callback


class RestoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(db, "SessionLocal", self.sessions))
        self.stack.enter_context(patch.object(handlers, "is_admin", side_effect=lambda uid: uid == 999))
        async with self.sessions() as session:
            session.add_all([db.User(id=1, username="member", status="approved"),
                             db.User(id=2, full_name="Anna <&>", status="approved")])
            await session.commit()

    async def asyncTearDown(self):
        self.stack.close()
        await self.engine.dispose()

    async def fixture(self, statuses=(), name="@JonasWagner12"):
        async with self.sessions() as session:
            tag = db.PaypalTag(tag=name, status="deleted", had_gestop=1)
            session.add(tag)
            await session.flush()
            requests = []
            for index, status in enumerate(statuses, start=1):
                req = db.Request(user_id=index, amount=100, status=status, paypal_tag_id=tag.id)
                session.add(req)
                requests.append(req)
            await session.commit()
            return tag, requests

    def assert_screen(self, screen, text):
        self.assertIn(text, screen.delivered[-1][0])
        self.assertEqual(screen.events[0], "answer", "Answer before editing or notifying")

    async def test_free_restore_confirmation_opens_on_text_and_photo(self):
        tag, _ = await self.fixture()
        for photo in (False, True):
            with self.subTest(photo=photo):
                screen = RestoreScreen(photo)
                await handlers.paypal_restore_ask_handler(screen.callback(f"paypal_restore_ask:{tag.id}"))
                self.assert_screen(screen, "Восстановить PayPal?")
                self.assertEqual((await db.get_paypal_tag(tag.id)).status, "deleted")

    async def test_free_restore_commits_and_renders_on_text_and_photo(self):
        for photo in (False, True):
            tag, _ = await self.fixture(name=f"@JonasWagner12_{photo}")
            screen = RestoreScreen(photo)
            await handlers.paypal_restore_confirm_handler(screen.callback(f"paypal_restore_confirm:{tag.id}"))
            self.assert_screen(screen, "PayPal восстановлен")
            restored = await db.get_paypal_tag(tag.id)
            self.assertEqual((restored.status, restored.had_gestop), ("available", 1))
            self.assertIsNone(restored.issued_to_user_id)

    async def test_previous_user_selection_on_text_and_photo(self):
        tag, requests = await self.fixture(("admin_recalled_deleted", "returned_deleted"))
        for photo in (False, True):
            screen = RestoreScreen(photo)
            await handlers.paypal_restore_working_users_handler(screen.callback(f"paypal_restore_working_users:{tag.id}"))
            self.assert_screen(screen, "Выберите пользователя")
            actions = [b.callback_data for row in screen.delivered[-1][1].inline_keyboard for b in row]
            for req in requests:
                self.assertIn(f"paypal_restore_working_ask:{tag.id}:{req.id}", actions)

    async def test_previous_user_confirmation_on_text_and_photo(self):
        tag, requests = await self.fixture(("admin_recalled_deleted",))
        for photo in (False, True):
            screen = RestoreScreen(photo)
            await handlers.paypal_restore_working_ask_handler(screen.callback(f"paypal_restore_working_ask:{tag.id}:{requests[0].id}"))
            self.assert_screen(screen, "Вернуть PayPal тому же пользователю?")

    async def test_previous_user_restored_once_on_text_and_photo(self):
        for photo in (False, True):
            tag, requests = await self.fixture(("admin_recalled_deleted",), name=f"@restore_{photo}")
            screen = RestoreScreen(photo)
            data = f"paypal_restore_working_confirm:{tag.id}:{requests[0].id}"
            await handlers.paypal_restore_working_confirm_handler(screen.callback(data))
            self.assert_screen(screen, "PayPal возвращён в работу")
            self.assertEqual((await db.get_paypal_tag(tag.id)).issued_to_user_id, 1)
            self.assertEqual((await db.get_request(requests[0].id)).status, "paypal_issued")
            screen.user_notice.assert_awaited_once()
            await handlers.paypal_restore_working_confirm_handler(screen.callback(data))
            screen.user_notice.assert_awaited_once()

    async def test_global_search_to_restore_and_back_to_trash(self):
        tag, _ = await self.fixture()
        markup = keyboards.global_search_results_menu({"tags": [tag]})
        screen = RestoreScreen(photo=False)
        await handlers.paypal_card_admin_handler(screen.callback(markup.inline_keyboard[0][0].callback_data))
        restore = screen.delivered[-1][1].inline_keyboard[0][0].callback_data
        await handlers.paypal_restore_ask_handler(screen.callback(restore))
        confirm = screen.delivered[-1][1].inline_keyboard[0][0].callback_data
        await handlers.paypal_restore_confirm_handler(screen.callback(confirm))
        self.assertEqual((await db.get_paypal_tag(tag.id)).status, "available")
        # An old text card's Back button must also remain usable.
        back = RestoreScreen(photo=False)
        await handlers.paypal_db_list_handler(back.callback("paypal_db_list:deleted:0"))
        self.assert_screen(back, "Корзина PayPal")

    async def test_repeated_free_restore_does_not_change_assignment(self):
        tag, requests = await self.fixture(("admin_recalled_deleted",))
        await db.restore_deleted_paypal_to_work(tag.id, 999, requests[0].id)
        screen = RestoreScreen()
        callback = screen.callback(f"paypal_restore_confirm:{tag.id}")
        await handlers.paypal_restore_confirm_handler(callback)
        callback.answer.assert_awaited_once_with("PayPal уже восстановлен", show_alert=True)
        self.assertEqual((await db.get_paypal_tag(tag.id)).status, "issued")
        self.assertFalse(screen.delivered)

    async def test_restore_after_return_keeps_old_history(self):
        tag, requests = await self.fixture(("returned_deleted",))
        screen = RestoreScreen()
        await handlers.paypal_restore_working_confirm_handler(screen.callback(f"paypal_restore_working_confirm:{tag.id}:{requests[0].id}"))
        self.assertEqual((await db.get_request(requests[0].id)).status, "returned_deleted")
        async with self.sessions() as session:
            active = await session.scalar(select(db.Request).where(db.Request.status == "paypal_issued"))
            self.assertNotEqual(active.id, requests[0].id)
            self.assertEqual((active.user_id, active.paypal_was_gestop), (1, 1))
            self.assertEqual(await session.scalar(select(func.count()).select_from(db.Request)), 2)

    async def test_non_admin_cannot_open_or_restore(self):
        tag, requests = await self.fixture(("admin_recalled_deleted",))
        for suffix, handler in (
            ("ask", handlers.paypal_restore_ask_handler),
            ("confirm", handlers.paypal_restore_confirm_handler),
            ("working_users", handlers.paypal_restore_working_users_handler),
            ("working_ask", handlers.paypal_restore_working_ask_handler),
            ("working_confirm", handlers.paypal_restore_working_confirm_handler),
        ):
            screen = RestoreScreen()
            callback = screen.callback(f"paypal_restore_{suffix}:{tag.id}", user_id=1)
            await handler(callback)
            callback.answer.assert_awaited_once_with("Нет доступа", show_alert=True)
            self.assertFalse(screen.delivered)
        self.assertEqual((await db.get_paypal_tag(tag.id)).status, "deleted")

    async def test_special_characters_in_card_and_restore_are_escaped(self):
        tag, _ = await self.fixture(("admin_recalled_deleted", "returned_deleted"), name="@Example<&>")
        screen = RestoreScreen()
        await handlers.paypal_card_admin_handler(screen.callback(f"paypal_card:{tag.id}:deleted"))
        self.assertIn("Anna &lt;&amp;&gt;", screen.delivered[-1][0])
        self.assertIn("@Example&lt;&amp;&gt;", screen.delivered[-1][0])
        await handlers.paypal_restore_ask_handler(screen.callback(f"paypal_restore_ask:{tag.id}"))
        self.assertIn("@Example&lt;&amp;&gt;", screen.delivered[-1][0])

    async def test_failed_edit_sends_replacement_before_deleting_old_screen(self):
        tag, _ = await self.fixture()
        screen = RestoreScreen(photo=True)
        screen.fail_edit = "message can't be edited"
        await handlers.paypal_restore_ask_handler(screen.callback(f"paypal_restore_ask:{tag.id}"))
        self.assert_screen(screen, "Восстановить PayPal?")
        self.assertLess(screen.events.index("send_photo"), screen.events.index("delete"))

    async def test_same_confirmation_is_not_an_error(self):
        tag, _ = await self.fixture()
        screen = RestoreScreen(photo=True)
        screen.fail_edit = "message is not modified"
        callback = screen.callback(f"paypal_restore_ask:{tag.id}")
        await handlers.paypal_restore_ask_handler(callback)
        callback.answer.assert_awaited_once()
        self.assertNotIn("delete", screen.events)

    async def test_long_deleted_card_remains_usable_for_restore(self):
        tag, _ = await self.fixture()
        async with self.sessions() as session:
            user = await session.get(db.User, 2)
            user.full_name = "Длинное имя " * 20
            session.add_all([
                db.Request(user_id=2, amount=100, status="returned_deleted", paypal_tag_id=tag.id)
                for _ in range(30)
            ])
            await session.commit()
        screen = RestoreScreen(photo=True)
        await handlers.paypal_card_admin_handler(screen.callback(f"paypal_card:{tag.id}:deleted"))
        self.assertFalse(screen.message.photo)
        self.assertIn("Связанные прежние выдачи: 30", screen.delivered[-1][0])
        self.assertIn("Показаны последние 5", screen.delivered[-1][0])
        # The selection keeps every request; limiting the card must not lose them.
        await handlers.paypal_restore_working_users_handler(screen.callback(f"paypal_restore_working_users:{tag.id}"))
        actions = [b.callback_data for row in screen.delivered[-1][1].inline_keyboard for b in row]
        self.assertEqual(sum(a.startswith("paypal_restore_working_ask:") for a in actions), 30)

    async def test_remaining_trash_total_is_not_limited_to_first_50(self):
        tag, _ = await self.fixture()
        async with self.sessions() as session:
            session.add_all([db.PaypalTag(tag=f"@deleted_{i}", status="deleted") for i in range(70)])
            await session.commit()
        screen = RestoreScreen()
        await handlers.paypal_restore_confirm_handler(screen.callback(f"paypal_restore_confirm:{tag.id}"))
        self.assertIn("В корзине осталось: <b>70</b>", screen.delivered[-1][0])

    async def test_failed_user_notification_does_not_hide_restoration(self):
        tag, requests = await self.fixture(("admin_recalled_deleted",))
        screen = RestoreScreen()
        screen.user_notice.side_effect = screen.error("chat not found")
        await handlers.paypal_restore_working_confirm_handler(screen.callback(f"paypal_restore_working_confirm:{tag.id}:{requests[0].id}"))
        self.assert_screen(screen, "PayPal возвращён в работу")
        self.assertEqual((await db.get_paypal_tag(tag.id)).status, "issued")


if __name__ == "__main__":
    unittest.main()
