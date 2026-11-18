"""Isolated SQLite + fake Telegram for API tests and the local browser preview.

This entry point intentionally has no production credentials or network calls.
Run explicitly with `python tests/miniapp_fixture.py`; main.py never imports it.
"""
import os
os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NO_NETWORK"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1/test"
os.environ["ADMIN_IDS"] = "999"
os.environ["MINI_APP_URL"] = "https://example.test/app"

import asyncio
import base64
import hashlib
import hmac
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiohttp import web
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.types import User, Message, Chat, PhotoSize, MessageId, File, BufferedInputFile, FSInputFile
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app import db, handlers, user_messages, autopost_handlers, autoposts
from app.config import settings
from app.miniapp import create_app, STATIC
from app.miniapp_transport import SurfaceStorage, WebTransport

TEST_TOKEN = "123456:TEST_ONLY_NO_NETWORK"
PHOTO = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5XcAAAAASUVORK5CYII=")


def signed_data(uid=1, *, auth_date=None, token=TEST_TOKEN):
    values = {"user": json.dumps({"id": uid, "first_name": "Тестовый участник" if uid != 999 else "Администратор", "username": "demo_member"}, separators=(",", ":")),
              "auth_date": str(int(time.time()) if auth_date is None else auth_date), "query_id": "test-only"}
    check = "\n".join(f"{k}={values[k]}" for k in sorted(values))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


class FakeTelegram(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.sequence = 1000
        self.files = {}

    async def close(self):
        pass

    async def stream_content(self, url, **kwargs):
        yield self.files.get(url.rsplit("/", 1)[-1], PHOTO)

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        name = method.__api_method__
        if name == "getMe":
            return User(id=bot.id, is_bot=True, first_name="DT TEST", username="DT_TEST_BOT")
        if name == "getFile":
            return File(file_id=method.file_id, file_unique_id=method.file_id, file_path=method.file_id, file_size=len(PHOTO))
        if name in {"copyMessage", "forwardMessage"}:
            self.sequence += 1
            return MessageId(message_id=self.sequence)
        if name in {"sendMessage", "sendPhoto", "sendDocument"}:
            self.sequence += 1
            file_id = "test-file-" + str(self.sequence)
            photo = None
            if name == "sendPhoto":
                source = method.photo
                if isinstance(source, BufferedInputFile):
                    self.files[file_id] = source.data
                elif isinstance(source, FSInputFile):
                    self.files[file_id] = Path(source.path).read_bytes()
                photo = [PhotoSize(file_id=file_id, file_unique_id=file_id, width=100, height=100)]
            return Message(message_id=self.sequence, date=datetime.now(timezone.utc),
                chat=Chat(id=method.chat_id, type="private"), from_user=User(id=bot.id, is_bot=True, first_name="DT TEST"),
                text=getattr(method, "text", None), caption=getattr(method, "caption", None), photo=photo,
                reply_markup=getattr(method, "reply_markup", None)).as_(bot)
        return True


async def runtime():
    object.__setattr__(settings, "admin_ids", {999})
    object.__setattr__(settings, "bot_token", TEST_TOKEN)
    object.__setattr__(settings, "mini_app_url", "https://example.test/app")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
        from app import rope, wheel
        await wheel.grant_admin_trials(conn, settings.admin_ids)
        await rope.grant_admin_trials(conn, settings.admin_ids)
    db.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with db.SessionLocal() as session:
        session.add_all([db.User(id=1, username="demo_member", status="approved", payout_method="cryptobot"),
                         db.User(id=2, status="approved", payout_method="xrocket"),
                         db.User(id=3, status="blocked"), db.User(id=4, status="pending"),
                         db.User(id=999, username="admin", status="approved"),
                         db.RateRule(min_amount=40, percent=50), db.RateRule(min_amount=50, percent=60), db.RateRule(min_amount=100, percent=70)])
        for n in range(1, 10):
            session.add(db.PaypalTag(tag=f"@test_paypal_{n}", status="available", gender="female" if n % 2 else "male"))
        await session.commit()
    await db.set_work_enabled(True)
    await db.set_auto_issue_enabled(False)
    await autoposts.seed_auto_posts()
    for uid, amount, withdrawn in [(1, 100, False), (1, 150, True), (2, 200, True)]:
        req = await db.create_request(uid, amount)
        req, tag = await db.issue_paypal(req.id)
        await db.mark_paid_by_user(req.id, uid)
        await db.confirm_payment(req.id, 999)
        if withdrawn:
            await db.mark_paypal_withdrawn(req.id, 999)
    storage = SurfaceStorage()
    dp = Dispatcher(storage=storage)
    for module in (handlers, user_messages, autopost_handlers):
        router = Router()
        for event, observer in module.router.observers.items():
            router.observers[event].handlers.extend(observer.handlers)
        dp.include_router(router)
    fake = FakeTelegram()
    fake.middleware(WebTransport())
    bot = Bot(TEST_TOKEN, session=fake, default=DefaultBotProperties(parse_mode="HTML"))
    bot._me = User(id=bot.id, is_bot=True, first_name="DT TEST", username="DT_TEST_BOT")
    app = create_app(bot, dp)
    return app, engine, bot, dp, fake


async def preview():
    app, engine, bot, dp, fake = await runtime()
    # Explicit local-only fixture switch; never imported by production.
    if os.environ.get("WHEEL_PREVIEW") == "1":
        from app import wheel
        await wheel.set_enabled(True, 999, 0)
        async with db.SessionLocal() as session, session.begin():
            req = db.Request(user_id=1, amount=600, status="waiting_check")
            session.add(req)
            await session.flush()
        await db.confirm_payment(req.id, 999)
        await db.mark_paypal_withdrawn(req.id, 999)

    @web.middleware
    async def local_index(request, handler):
        if request.path in {"/", "/app"}:
            html = (STATIC / "index.html").read_text().replace("https://telegram.org/js/telegram-web-app.js", "/test-telegram.js?admin="+request.query.get("admin","0"))
            return web.Response(text=html, content_type="text/html")
        return await handler(request)

    async def telegram_fixture(request):
        script = "window.Telegram={WebApp:{initData:" + json.dumps(signed_data(999 if request.query.get('admin')=='1' else 1)) + ",ready(){},expand(){},setHeaderColor(){},setBackgroundColor(){},setBottomBarColor(){},BackButton:{hide(){},show(){},onClick(){}}}};"
        return web.Response(text=script, content_type="application/javascript")

    app.middlewares.append(local_index)
    app.router.add_get("/test-telegram.js", telegram_fixture)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", int(os.environ.get("PREVIEW_PORT", "8773"))).start()
    print("Test preview: http://127.0.0.1:8773/app (SQLite + fake Telegram only)", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(preview())
