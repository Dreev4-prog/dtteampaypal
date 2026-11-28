"""Authenticated same-origin Mini App, sharing the existing bot/DB operations."""
import asyncio
import base64
import logging
import os
import secrets
import time
from collections import OrderedDict
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import BufferedInputFile, CallbackQuery, Chat, Message, Update, User
from sqlalchemy import text

from app.config import settings
from app import db, wheel, rope, game_stats
from app.miniapp_auth import validate_init_data
from app.miniapp_transport import WebTransport, public_records, web_context, media_bytes

STATIC = Path(__file__).resolve().parent / "miniapp_static"
TTL = 8 * 3600
MAX_PHOTO = 8 * 1024 * 1024
NAVIGATION = {"home", "paypal_request", "request_back", "my_paypals", "wallet", "profile", "support", "dt_payments", "admin_home", "wheel", "rope", "wheel_test", "rope_test"}


@dataclass
class WebSession:
    user: User
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    created: float = field(default_factory=time.time)
    counter: int = -100000
    version: int = 0
    messages: dict = field(default_factory=dict)
    emitted: dict = field(default_factory=dict)
    media: dict = field(default_factory=dict)
    actions: dict = field(default_factory=dict)
    display: list = field(default_factory=list)
    notices: list = field(default_factory=list)
    operations: OrderedDict = field(default_factory=OrderedDict)
    response: dict = field(default_factory=dict)
    banner: str = "home"
    route: str = "home"
    section: str = "home"
    busy: bool = False
    closed: bool = False
    hits: list = field(default_factory=list)
    updates_at: float = 0
    updates: dict = field(default_factory=dict)


class MiniApp:
    def __init__(self, bot, dispatcher):
        self.bot = bot
        self.dp = dispatcher
        self.sessions = {}
        self.user_locks = {}
        self.tasks = set()
        self.auth_hits = {}

    def lock(self, user_id):
        return self.user_locks.setdefault(user_id, asyncio.Lock())

    def fsm(self, session):
        return FSMContext(self.dp.storage, StorageKey(bot_id=self.bot.id, chat_id=session.user.id,
                                                    user_id=session.user.id, destiny="miniapp"))

    async def identity(self, session):
        user = await db.get_user(session.user.id)
        admin = session.user.id in settings.admin_ids
        return user, admin

    def reap(self):
        now = time.time()
        for key, session in list(self.sessions.items()):
            if not session.busy and (session.closed or now - session.created > TTL):
                self.sessions.pop(key, None)
        active_users = {s.user.id for s in self.sessions.values()}
        for uid, lock in list(self.user_locks.items()):
            if uid not in active_users and not lock.locked():
                self.user_locks.pop(uid, None)
        self.auth_hits = {key: values for key, values in self.auth_hits.items()
                          if values and now - values[-1] < 60}

    def session(self, request):
        token = request.headers.get("Authorization", "").removeprefix("MiniApp ")
        session = self.sessions.get(token)
        if not session or session.closed or time.time() - session.created > TTL:
            raise web.HTTPUnauthorized(text="Закройте Mini App и снова откройте её из бота.")
        return session

    async def bootstrap(self, request):
        self.reap()
        ip = request.headers.get("X-Forwarded-For", request.remote or "").split(",")[0]
        recent = [t for t in self.auth_hits.get(ip, []) if time.time() - t < 60]
        if len(recent) >= 30 or len(self.sessions) >= 2000:
            raise web.HTTPTooManyRequests(text="Повторите открытие через минуту.")
        self.auth_hits[ip] = recent + [time.time()]
        body = await request.json()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(text="Ожидается объект запроса.")
        try:
            identity = validate_init_data(body.get("init_data"), settings.bot_token)
        except ValueError as exc:
            raise web.HTTPUnauthorized(text=str(exc)) from exc
        user = User(**identity, is_bot=False)
        async with self.lock(user.id):
            # One form per user/surface. Opening a second Mini App invalidates the
            # previous window; it cannot later submit an obsolete financial form.
            if any(s.user.id == user.id and s.busy for s in self.sessions.values()):
                raise web.HTTPConflict(text="Предыдущее действие ещё выполняется. Дождитесь результата.")
            for old in self.sessions.values():
                if old.user.id == user.id:
                    old.closed = True
            session = WebSession(user=user)
            self.sessions[session.token] = session
            await self.execute(session, {"nav": "home"}, initial=True)
            return web.json_response({"token": session.token, **session.response})

    async def get_state(self, request):
        session = self.session(request)
        user, admin = await self.identity(session)
        if user and user.status in {"blocked", "rejected"} and not admin:
            return web.json_response({"version": session.version, "busy": session.busy,
                "user": {"id": user.id, "name": session.user.full_name, "admin": False, "status": user.status},
                "messages": [], "form": None, "route": "home", "notices": ["Доступ к сервису закрыт. Обратитесь в поддержку."]})
        return web.json_response({**session.response, "busy": session.busy})

    async def get_updates(self, request):
        session = self.session(request)
        user, admin = await self.identity(session)
        if not admin and (not user or user.status != "approved"):
            raise web.HTTPForbidden(text="Уведомления доступны после одобрения доступа.")
        if time.time() - session.updates_at >= 5:
            from app.miniapp_events import recent_events
            session.updates = {"events": await recent_events(session.user.id, admin),
                               "summary": await db.get_user_home_summary(session.user.id),
                               "work": await db.is_work_enabled(),
                               "wheel": await wheel.summary(session.user.id)}
            session.updates["summary"] = {k: float(v) for k, v in session.updates["summary"].items()}
            session.updates_at = time.time()
        return web.json_response(session.updates)

    async def wheel_access(self, request):
        session = self.session(request)
        user, _ = await self.identity(session)
        if not user or user.status != "approved":
            raise web.HTTPForbidden(text="Доступ к акции закрыт.")
        return session

    async def get_wheel(self, request):
        session = await self.wheel_access(request)
        return web.json_response(await wheel.state(session.user.id))

    async def spin_wheel(self, request):
        session = await self.wheel_access(request)
        body = await request.json()
        if not isinstance(body, dict) or set(body) != {"request_id"}:
            raise web.HTTPBadRequest(text="Недействительный запрос вращения.")
        hits = [t for t in session.hits if time.time() - t < 60]
        if len(hits) >= 90:
            raise web.HTTPTooManyRequests(text="Слишком много действий. Подождите немного.")
        session.hits = hits + [time.time()]
        async with self.lock(session.user.id):
            # A replacement WebView may have revoked this session while waiting.
            self.session(request)
            try:
                result = await wheel.spin(session.user.id, body.get("request_id"))
            except ValueError as exc:
                raise web.HTTPConflict(text=str(exc)) from exc
            session.updates_at = 0
            return web.json_response({"result": result, "wheel": await wheel.state(session.user.id)})

    async def wheel_test(self, request):
        session = self.session(request)
        if session.user.id not in settings.admin_ids:
            raise web.HTTPForbidden(text="Тестовые вращения доступны только администраторам.")
        if request.method == "GET":
            return web.json_response((await wheel.admin_trials(session.user.id))["wheel"])
        body = await request.json()
        if not isinstance(body, dict) or set(body) != {"request_id"} or not isinstance(body["request_id"], str):
            raise web.HTTPBadRequest(text="Недействительный запрос вращения.")
        async with self.lock(session.user.id):
            self.session(request)
            try:
                result = await wheel.admin_trials(session.user.id, body["request_id"])
            except ValueError as exc:
                raise web.HTTPConflict(text=str(exc)) from exc
            return web.json_response(result)

    async def rope_game(self, request):
        return await self.handle_rope(request, trial=False)

    async def rope_test(self, request):
        return await self.handle_rope(request, trial=True)

    async def handle_rope(self, request, *, trial):
        received = datetime.utcnow()
        if trial:
            session = self.session(request)
            if session.user.id not in settings.admin_ids:
                raise web.HTTPForbidden(text="Тестовые забеги доступны только администраторам.")
        else:
            session = await self.wheel_access(request)
        if request.method == "POST":
            body = await request.json()
            if not isinstance(body, dict):
                raise web.HTTPBadRequest(text="Ожидается действие игры.")
            hits = [t for t in session.hits if time.time() - t < 60]
            if len(hits) >= 90:
                raise web.HTTPTooManyRequests(text="Подождите немного.")
            session.hits = hits + [time.time()]
            async with self.lock(session.user.id):
                self.session(request)
                try:
                    if trial:
                        return web.json_response(await rope.admin_trials(session.user.id, body, received))
                    await rope.play(session.user.id, body, received)
                except ValueError as exc:
                    raise web.HTTPConflict(text=str(exc)) from exc
                session.updates_at = 0
        if trial:
            return web.json_response(await rope.admin_trials(session.user.id))
        return web.json_response(await rope.state(session.user.id))

    async def game_statistics(self, request):
        session = self.session(request)
        if session.user.id not in settings.admin_ids:
            raise web.HTTPForbidden(text="Нет доступа к статистике.")
        page = int(request.query.get("page", "0"))
        uid = int(request.query["uid"]) if "uid" in request.query else None
        if not 0 <= page <= 100000000 or (uid is not None and not 0 < uid < 2**63):
            raise web.HTTPBadRequest(text="Недействительная страница или ID.")
        return web.json_response(await game_stats.report(page, uid))

    async def action(self, request):
        session = self.session(request)
        body = await request.json()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(text="Ожидается объект запроса.")
        user, admin = await self.identity(session)
        callback = session.actions.get(body.get("action"), (None, ""))[1]
        if body.get("nav") in ("admin_home", "wheel_test", "rope_test") and not admin:
            raise web.HTTPForbidden(text="Нет доступа к управлению.")
        if not admin and (not user or user.status != "approved"):
            if body.get("nav") not in {"home", "support"} and callback != "membership_apply":
                raise web.HTTPForbidden(text="Дождитесь одобрения доступа.")
        nonce = body.get("request_id", "")
        if not isinstance(nonce, str) or not 16 <= len(nonce) <= 80:
            raise web.HTTPBadRequest(text="Недействительный запрос.")
        if nonce in session.operations:
            return web.json_response({**session.response, "busy": session.busy})
        if session.busy or body.get("version") != session.version:
            raise web.HTTPConflict(text="Экран уже изменился. Обновляем состояние.")
        hits = [t for t in session.hits if time.time() - t < 60]
        if len(hits) >= 90:
            raise web.HTTPTooManyRequests(text="Слишком много действий. Подождите немного.")
        session.hits = hits + [time.time()]
        self.validate_action(session, body)
        session.operations[nonce] = True
        while len(session.operations) > 64:
            session.operations.popitem(last=False)
        session.busy = True
        task = asyncio.create_task(self.run_action(session, body))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        # Handlers may notify many users or wait for AUTO. The operation continues
        # if the WebView closes; clients poll its result instead of resubmitting.
        return web.json_response({**session.response, "busy": True}, status=202)

    @staticmethod
    def validate_action(session, body):
        kinds = [name for name in ("nav", "action", "input") if name in body]
        if len(kinds) != 1:
            raise web.HTTPBadRequest(text="Выберите одно действие.")
        if "nav" in body and body["nav"] not in NAVIGATION:
            raise web.HTTPForbidden(text="Этот раздел недоступен.")
        if "action" in body and body["action"] not in session.actions:
            raise web.HTTPConflict(text="Кнопка устарела. Откройте раздел заново.")
        if "input" in body:
            value = body["input"]
            if not isinstance(value, dict) or len(str(value.get("text", ""))) > 10000:
                raise web.HTTPBadRequest(text="Слишком длинный текст.")

    async def run_action(self, session, body):
        async with self.lock(session.user.id):
            try:
                await self.execute(session, body)
            except web.HTTPException as exc:
                session.version += 1
                session.response = {**session.response, "version": session.version,
                    "messages": public_records(session), "notices": [exc.text]}
            except Exception as exc:
                logging.error("Mini App operation failed (%s)", type(exc).__name__, exc_info=True)
                # Never replay automatically after an ambiguous delivery/commit.
                session.version += 1
                session.response = {**session.response, "version": session.version,
                    "notices": ["Не удалось подтвердить результат. Действие не повторяется автоматически. Проверьте состояние в разделе или в боте."],
                    "form": None}
                session.actions.clear()
            finally:
                session.busy = False
                session.updates_at = 0

    async def execute(self, session, body, initial=False):
        from app.handlers import show_home
        user, admin = await self.identity(session)
        approved = user is not None and user.status == "approved"
        nav = body.get("nav")
        if nav in {"admin_home", "wheel_test", "rope_test"} and not admin:
            raise web.HTTPForbidden(text="Нет доступа.")
        if not approved and not admin and nav not in {"home", "support"}:
            # Membership apply is the sole non-navigation callback permitted.
            callback = session.actions.get(body.get("action"), (None, ""))[1]
            if callback != "membership_apply":
                raise web.HTTPForbidden(text="Дождитесь одобрения доступа.")
        session.emitted = {}
        session.notices = []
        token = web_context.set(session)
        try:
            state = self.fsm(session)
            if nav == "request_back":
                from app.handlers import PaypalRequestForm
                previous = await state.get_state()
                if previous not in {"PaypalRequestForm:gender", "PaypalRequestForm:screenshot"}:
                    raise web.HTTPConflict(text="Этот шаг уже завершён. Откройте заявку заново.")
                session.route = "paypal_request"
                session.section = "my_paypals"
                if previous == "PaypalRequestForm:gender":
                    await self.dispatch_callback(session, "paypal_request", self.incoming(session))
                else:
                    value = (await state.get_data()).get("amount", "")
                    await state.update_data(paypal_gender=None)
                    await state.set_state(PaypalRequestForm.amount)
                    message = self.incoming(session, text=str(value))
                    await self.dp.feed_update(self.bot, Update(update_id=abs(message.message_id), message=message))
            elif nav in {"wheel_test", "rope_test"}:
                await state.clear()
                session.route, session.section = nav, "admin_home"
                session.display = []
                session.actions.clear()
            elif nav is not None:
                await state.clear()
                session.route = nav
                session.section = "my_paypals" if nav == "paypal_request" else nav
                session.banner = {"wallet": "profile", "my_paypals": "requests", "paypal_request": "paypal",
                    "support": "support", "profile": "profile", "admin_home": "admin", "dt_payments": "payments"}.get(nav, "home")
                message = self.incoming(session, text="/start")
                if nav == "home":
                    await show_home(message)
                else:
                    await self.dispatch_callback(session, "wheel" if nav == "rope" else nav, message)
                if not session.emitted and not await state.get_state():
                    session.route = "home"
                    session.section = "home"
                    await show_home(message)
            elif "action" in body:
                mid, callback = session.actions[body["action"]]
                record = session.messages[mid]
                message = WebTransport.message(self.bot, session, record)
                session.route = callback
                if callback in NAVIGATION:
                    session.section = "my_paypals" if callback == "paypal_request" else callback
                elif callback.startswith("my_paypals"):
                    session.section = "my_paypals"
                elif callback.startswith(("payout_method", "set_payout_method", "payout_history", "payout_receipt")):
                    session.section = "wallet"
                await self.dispatch_callback(session, callback, message)
            else:
                form_state = await state.get_state()
                if not form_state:
                    raise web.HTTPConflict(text="Эта форма уже закрыта.")
                value = body["input"]
                message = await self.input_message(session, value, form_state)
                await self.dp.feed_update(self.bot, Update(update_id=abs(message.message_id), message=message))
            if session.emitted:
                session.display = list(session.emitted.values())
            # Keep old screen if the only result is a callback alert or receipt.
            session.version += 1
            user, admin = await self.identity(session)
            summary = await db.get_user_home_summary(session.user.id) if user and user.status == "approved" else None
            form_state = await state.get_state()
            state_data = await state.get_data()
            session.response = {
                "version": session.version, "route": session.route, "section": session.section, "busy": False,
                "user": {"id": session.user.id, "name": session.user.full_name, "admin": admin,
                         "status": user.status if user else "pending"},
                "summary": {k: float(v) for k, v in summary.items()} if summary else None,
                "work": await db.is_work_enabled(),
                "messages": public_records(session), "notices": session.notices,
                "form": form_description(form_state, state_data),
                "journey": journey_description(form_state, state_data),
                "wheel": await wheel.summary(session.user.id) if approved or admin else {"enabled": False},
            }
            if session.route in {"wheel", "rope"} and (approved or admin):
                session.response["wheel"] = await wheel.state(session.user.id)
            if admin and session.route == "wheel_test":
                session.response["trials"] = (await wheel.admin_trials(session.user.id))["wheel"]
            if admin and session.route.startswith("payouts_v22"):
                totals = await db.get_payout_dashboard_counts()
                session.response["payouts"] = {key: float(totals.get(key, 0)) for key in ("cryptobot_total", "xrocket_total")}
            if admin and session.route == "admin_home":
                session.response["dashboard"] = await db.get_dashboard_summary()
            if approved and session.route in {"wallet", "my_balance"}:
                balance = await db.get_user_balance(session.user.id)
                session.response["wallet"] = {key: balance[key] for key in ("available", "held", "paid", "count_paid", "method", "wheel_next_bonus", "wheel_bonus_count")}
                points = session.response["wheel"].get("balance")
                if points is None:
                    async with db.SessionLocal() as ledger:
                        points = (await wheel.totals(ledger, session.user.id))["balance"]
                session.response["wallet"]["game_points"] = points
            keep_ids = {record["id"] for record in session.display}
            session.messages = {key: value for key, value in session.messages.items() if key in keep_ids}
            media_ids = {item["id"] for record in session.display for item in (record.get("photo"), record.get("document")) if item}
            session.media = {key: value for key, value in session.media.items() if key in media_ids}
        finally:
            web_context.reset(token)

    def incoming(self, session, text=None, **kwargs):
        session.counter -= 1
        return Message(message_id=session.counter, date=datetime.now(timezone.utc),
                       chat=Chat(id=session.user.id, type="private"), from_user=session.user,
                       text=text, **kwargs).as_(self.bot)

    async def dispatch_callback(self, session, data, message):
        callback = CallbackQuery(id=secrets.token_hex(12), from_user=session.user,
                                 chat_instance="miniapp", message=message, data=data)
        await self.dp.feed_update(self.bot, Update(update_id=abs(session.counter), callback_query=callback))

    async def input_message(self, session, value, form_state):
        text_value = value.get("text") or ""
        if not isinstance(text_value, str) or text_value.lstrip().startswith("/"):
            raise web.HTTPBadRequest(text="Введите значение для текущей формы.")
        photo = value.get("photo")
        description = form_description(form_state, await self.fsm(session).get_data())
        if not description or (photo and description["kind"] not in {"photo", "receipt"}):
            raise web.HTTPBadRequest(text="Эта форма не принимает фотографии.")
        if description["kind"] == "photo" and not photo:
            raise web.HTTPBadRequest(text="Прикрепите фото.")
        message = None
        # Upload directly to Telegram for a durable, real file/message reference.
        # Bypass capture only for this explicit upload, never for screen responses.
        token = web_context.set(None)
        try:
            if photo:
                if not isinstance(photo, str) or len(photo) > MAX_PHOTO * 4 // 3 + 8:
                    raise web.HTTPBadRequest(text="Фото должно быть не больше 8 МБ.")
                try:
                    data = base64.b64decode(photo, validate=True)
                except ValueError as exc:
                    raise web.HTTPBadRequest(text="Не удалось прочитать фото.") from exc
                valid = data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")) or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
                if not valid or len(data) > MAX_PHOTO:
                    raise web.HTTPBadRequest(text="Прикрепите JPEG, PNG или WebP до 8 МБ.")
                message = await self.bot.send_photo(session.user.id, BufferedInputFile(data, filename="miniapp-photo.jpg"),
                                                    caption=text_value or None, parse_mode=None)
            elif form_state == "ManualPayoutForm:check":
                if not text_value.strip():
                    raise web.HTTPBadRequest(text="Пришлите чек.")
                message = await self.bot.send_message(session.user.id, text_value, parse_mode=None)
        finally:
            web_context.reset(token)
        if message is not None:
            # Handlers receive the authenticated person as author, while retaining
            # Telegram's actual message ID and files for repeat check delivery.
            data = message.model_dump(exclude_none=True, by_alias=True)
            data["from"] = session.user.model_dump()
            return Message.model_validate(data, context={"bot": self.bot})
        if not text_value.strip():
            raise web.HTTPBadRequest(text="Введите текст или прикрепите фото.")
        return self.incoming(session, text=text_value)

    async def media(self, request):
        session = self.session(request)
        user, admin = await self.identity(session)
        if not admin and (not user or user.status != "approved"):
            raise web.HTTPForbidden()
        item = session.media.get(request.match_info["media_id"])
        if item is None:
            raise web.HTTPNotFound()
        data, mime = await media_bytes(self.bot, item)
        return web.Response(body=data, content_type=mime,
                            headers={"Content-Disposition": "attachment" if item["kind"] == "document" else "inline"})

    async def cleanup(self, app):
        if self.tasks:
            done, pending = await asyncio.wait(self.tasks, timeout=30)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)


def form_description(state, data):
    if not state or state.split(":")[-1] in {"gender", "timing", "confirm"}:
        return None
    name = state.split(":")[-1]
    photo = name in {"photo", "image", "screenshot"}
    if state == "AutoPostForm:value":
        photo = data.get("ap_field") == "photo"
    receipt = state == "ManualPayoutForm:check"
    number = "amount" in name or name in {"min_amount", "percent", "custom_limit"}
    result = {"kind": "photo" if photo else "receipt" if receipt else "number" if number else "text",
            "key": ":".join(str(v) for v in (state, data.get("payment_request_id", ""), data.get("ap_id", ""), data.get("ap_field", ""))),
            "label": "Прикрепить фото" if photo else "Чек для получателя" if receipt else "Введите значение",
            "placeholder": "Ссылка или текст чека" if receipt else "Введите здесь",
            "submit": "Отправить чек и завершить выплату" if receipt else "Продолжить"}
    if state == "PaypalRequestForm:amount":
        result.update(label="Ожидаемая сумма, €", placeholder="Например, 100", quick=[50, 100, 200], submit="Далее — тип PayPal")
    elif state == "PaypalRequestForm:screenshot":
        result.update(label="Скриншот готовности к оплате", submit="Отправить заявку")
    elif state.startswith("PaymentAmountForm:"):
        result.update(label="Сумма оплаты, €", placeholder="Например, 100", submit="Проверить сумму")
    elif state in {"MemberTagSearch:query", "MemberSearch:query"}:
        result.update(label="Пользователь", placeholder="Telegram ID или @username", submit="Найти пользователя")
    elif name == "query":
        result.update(label="Поиск", placeholder="Введите запрос", submit="Найти")
    elif state == "PaypalAddForm:tag":
        result.update(label="Тег PayPal", placeholder="Введите тег PayPal")
    elif state == "PaypalAddForm:bulk":
        result.update(label="Список PayPal", placeholder="Каждый PayPal с новой строки")
    elif state == "DTPaymentsChannelForm:channel":
        result.update(label="Канал DT Payments", placeholder="@username или ID канала", submit="Проверить и подключить")
    elif state == "DTPaymentsTagForm:new_tag":
        result.update(label="Ваш тег в DT Payments", placeholder="Введите тег", submit="Сохранить тег")
    elif state == "HappyHoursForm:text":
        result.update(label="Текст поста", initial=data.get("happy_initial", ""), rows=8,
                      placeholder="Введите текст для участников", submit="Сохранить и посмотреть")
    elif state == "AutoPostForm:value":
        field = data.get("ap_field")
        if field == "minute":
            result.update(kind="time", label="Время отправки по Москве", placeholder="13:00", submit="Сохранить время")
        elif field in {"name", "body"}:
            result.update(label="Название поста" if field == "name" else "Текст поста", placeholder="Введите название" if field == "name" else "Введите текст для участников")
    elif name in {"custom_reason", "reject_reason"}:
        result.update(label="Причина", placeholder="Кратко объясните причину")
    return result


def journey_description(state, data):
    steps = {"PaypalRequestForm:amount": 1, "PaypalRequestForm:gender": 2, "PaypalRequestForm:screenshot": 3}
    if state not in steps:
        return None
    return {"step": steps[state], "labels": ["Сумма", "Тип PayPal", "Скриншот"],
            "amount": data.get("amount"), "gender": data.get("paypal_gender")}


@web.middleware
async def security_headers(request, handler):
    try:
        if request.path.startswith("/api/"):
            if request.path == "/api/session" and (request.content_length or 0) > 20000:
                raise web.HTTPRequestEntityTooLarge(max_size=20000, actual_size=request.content_length)
            origin = request.headers.get("Origin")
            if origin and origin not in {f"https://{request.host}", f"http://{request.host}"}:
                raise web.HTTPForbidden(text="Недопустимый источник запроса.")
            if request.method == "POST" and request.content_type != "application/json":
                raise web.HTTPBadRequest(text="Ожидается JSON.")
        response = await handler(request)
    except web.HTTPException as exc:
        response = web.json_response({"error": exc.text}, status=exc.status)
    except (ValueError, TypeError, KeyError):
        response = web.json_response({"error": "Не удалось прочитать запрос."}, status=400)
    except Exception as exc:
        logging.error("Mini App HTTP failure (%s)", type(exc).__name__)
        response = web.json_response({"error": "Сервис временно недоступен. Попробуйте позже."}, status=503)
    response.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store" if request.path.startswith("/api/") else "no-cache",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors https://web.telegram.org https://*.telegram.org"})
    return response


def create_app(bot, dispatcher):
    service = MiniApp(bot, dispatcher)
    app = web.Application(client_max_size=12 * 1024 * 1024, middlewares=[security_headers])
    app["miniapp"] = service
    app.router.add_post("/api/session", service.bootstrap)
    app.router.add_get("/api/state", service.get_state)
    app.router.add_get("/api/updates", service.get_updates)
    app.router.add_post("/api/action", service.action)
    app.router.add_get("/api/rope/test", service.rope_test)
    app.router.add_post("/api/rope/test", service.rope_test)
    app.router.add_get("/api/rope", service.rope_game)
    app.router.add_post("/api/rope", service.rope_game)
    app.router.add_get("/api/games/statistics", service.game_statistics)
    app.router.add_get("/api/wheel/test", service.wheel_test)
    app.router.add_post("/api/wheel/test", service.wheel_test)
    app.router.add_get("/api/wheel", service.get_wheel)
    app.router.add_post("/api/wheel/spin", service.spin_wheel)
    app.router.add_get("/api/media/{media_id}", service.media)

    async def health(request):
        try:
            async with asyncio.timeout(4), db.SessionLocal() as session:
                await session.execute(text("SELECT 1"))
            return web.json_response({"ok": True, "service": "dt-team", "miniapp": True})
        except Exception:
            return web.json_response({"ok": False}, status=503)

    async def index(request):
        return web.FileResponse(STATIC / "index.html")

    app.router.add_get("/healthz", health)
    app.router.add_get("/", index)
    app.router.add_get("/app", index)
    app.router.add_static("/static/", STATIC, show_index=False, follow_symlinks=False)
    app.on_cleanup.append(service.cleanup)
    return app


async def start_web_server(bot, dispatcher):
    runner = web.AppRunner(create_app(bot, dispatcher), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "8080"))).start()
    logging.info("DT Mini App HTTP server ready")
    return runner
