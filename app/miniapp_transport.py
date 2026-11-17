"""Reuse the bot's handlers; capture only responses to the active Web App user.

Other recipients still use Telegram. Inbound photos/receipts are genuine Telegram
messages, so existing file IDs, audit records and repeat receipt delivery survive.
"""
import mimetypes
import secrets
from contextvars import ContextVar
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from aiogram.client.default import Default
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, PhotoSize, User, InputFile, FSInputFile, BufferedInputFile

from app.miniapp_auth import safe_html, safe_url

web_context = ContextVar("dt_miniapp_context", default=None)


class SurfaceStorage(MemoryStorage):
    """Separate ongoing Mini App forms from forms in the Telegram conversation."""
    @staticmethod
    def surface_key(key):
        return replace(key, destiny="miniapp") if web_context.get() is not None else key

    async def set_state(self, key, state=None):
        return await super().set_state(self.surface_key(key), state)

    async def get_state(self, key):
        return await super().get_state(self.surface_key(key))

    async def set_data(self, key, data):
        return await super().set_data(self.surface_key(key), data)

    async def get_data(self, key):
        return await super().get_data(self.surface_key(key))

    async def get_value(self, storage_key, dict_key, default=None):
        return await super().get_value(self.surface_key(storage_key), dict_key, default)


class WebTransport(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        ctx = web_context.get()
        if ctx is None:
            return await make_request(bot, method)
        name = method.__api_method__
        if name == "answerCallbackQuery":
            if method.text:
                ctx.notices.append(method.text)
            return True
        if getattr(method, "chat_id", None) != ctx.user.id:
            return await make_request(bot, method)
        if name in {"copyMessage", "forwardMessage"}:
            # Stored payout receipts stay in Telegram, where their original
            # buttons and provider semantics remain available to the recipient.
            result = await make_request(bot, method)
            ctx.notices.append("Чек отправлен в чат с ботом.")
            return result
        if name == "sendChatAction":
            return True
        if name == "deleteMessage":
            ctx.messages.pop(method.message_id, None)
            ctx.emitted.pop(method.message_id, None)
            return True
        if name in {"sendMessage", "sendPhoto", "sendDocument", "editMessageText",
                    "editMessageCaption", "editMessageMedia", "editMessageReplyMarkup"}:
            mid = getattr(method, "message_id", None)
            previous = ctx.messages.get(mid)
            if mid is None:
                ctx.counter -= 1
                mid = ctx.counter
            record = dict(previous or {"id": mid, "text": "", "html": "", "rows": [], "photo": None, "document": None})
            media = getattr(method, "media", None)
            raw = getattr(method, "text", None)
            if raw is None:
                raw = getattr(media, "caption", None) if media else getattr(method, "caption", None)
            if raw is not None:
                mode = getattr(media or method, "parse_mode", None)
                html = isinstance(mode, Default) or str(mode).upper() == "HTML"
                record.update(text=raw, html=safe_html(raw, html))
            if name != "editMessageReplyMarkup" or hasattr(method, "reply_markup"):
                record["markup"] = getattr(method, "reply_markup", None)
            photo = getattr(media, "media", None) if media else getattr(method, "photo", None)
            if photo is not None:
                record["photo"] = self.media(ctx, photo, "photo")
            document = getattr(method, "document", None)
            if document is not None:
                record["document"] = self.media(ctx, document, "document")
            if name == "editMessageText":
                record["photo"] = None
            record["banner"] = ctx.banner
            ctx.messages[mid] = record
            ctx.emitted[mid] = record
            return self.message(bot, ctx, record)
        return await make_request(bot, method)

    @staticmethod
    def media(ctx, source, kind):
        token = secrets.token_urlsafe(18)
        filename = getattr(source, "filename", None) or ("photo.jpg" if kind == "photo" else "document")
        if isinstance(source, FSInputFile):
            filename = source.path.name if isinstance(source.path, Path) else Path(source.path).name
        ctx.media[token] = {"source": source, "filename": filename, "kind": kind}
        builtin = isinstance(source, FSInputFile) and filename not in {"auto_post_day.png", "auto_post_evening.png"}
        return {"id": token, "filename": filename, "is_banner": builtin}

    @staticmethod
    def message(bot, ctx, record):
        photo = [PhotoSize(file_id="miniapp-screen", file_unique_id="miniapp-screen", width=1100, height=620)] if record.get("photo") else None
        return Message(message_id=record["id"], date=datetime.now(timezone.utc),
                       chat=Chat(id=ctx.user.id, type="private"),
                       from_user=User(id=bot.id, is_bot=True, first_name="DT TEAM"),
                       caption=record["text"] if photo else None,
                       text=None if photo else record["text"], photo=photo,
                       reply_markup=record.get("markup")).as_(bot)


def public_records(ctx):
    """Opaque action IDs bind each button to its server-held message and callback."""
    ctx.actions = {}
    result = []
    for record in ctx.display[-24:]:
        rows = []
        markup = record.get("markup")
        for row in getattr(markup, "inline_keyboard", []):
            buttons = []
            for button in row:
                if button.callback_data:
                    token = secrets.token_urlsafe(18)
                    ctx.actions[token] = (record["id"], button.callback_data)
                    buttons.append({"label": button.text, "action": token})
                elif button.url and safe_url(button.url):
                    buttons.append({"label": button.text, "url": safe_url(button.url)})
                # The launcher points back to this same app; don't recurse.
            if buttons:
                rows.append(buttons)
        result.append({key: record.get(key) for key in ("id", "html", "photo", "document", "banner")} | {"rows": rows})
    return result


async def media_bytes(bot, item):
    source = item["source"]
    if isinstance(source, BufferedInputFile):
        data = source.data
    elif isinstance(source, FSInputFile):
        data = Path(source.path).read_bytes()
    elif isinstance(source, InputFile):
        data = b"".join([chunk async for chunk in source.read(bot)])
    elif isinstance(source, str) and not source.startswith(("https://", "http://")):
        data = (await bot.download(source)).getvalue()
    else:
        raise ValueError("Unsupported media")
    mime = mimetypes.guess_type(item["filename"])[0] or "application/octet-stream"
    return data, mime
