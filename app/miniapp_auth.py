"""Telegram Mini App authentication and safe rendering, without Telegram I/O."""
import hashlib
import hmac
import json
import time
from html import escape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlsplit


def validate_init_data(raw: str, bot_token: str, *, now=None, max_age=3600) -> dict:
    if not isinstance(raw, str) or not raw or len(raw) > 16384:
        raise ValueError("Откройте Mini App через кнопку в боте.")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
        data = dict(pairs)
        if len(data) != len(pairs):
            raise ValueError()
        received = data.pop("hash")
        check = "\n".join(f"{key}={data[key]}" for key in sorted(data))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received):
            raise ValueError()
        age = (time.time() if now is None else now) - int(data["auth_date"])
        if age < -30 or age > max_age:
            raise ValueError()
        user = json.loads(data["user"])
        if type(user.get("id")) is not int or not 0 < user["id"] < 2**52 or user.get("is_bot"):
            raise ValueError()
        if data.get("chat_type") not in (None, "sender", "private"):
            raise ValueError()
        return {key: value for key, value in user.items()
                if key in {"id", "first_name", "last_name", "username", "language_code"}}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Сессия Telegram недействительна. Закройте Mini App и откройте её из бота.") from exc


def safe_url(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        return None
    parts = urlsplit(value)
    if parts.scheme == "https" and parts.hostname and not parts.username and not parts.password:
        return value
    if parts.scheme == "tg" and parts.netloc in {"user", "resolve"}:
        return value
    return None


class SafeTelegramHTML(HTMLParser):
    tags = {"b", "strong", "i", "em", "u", "s", "del", "code", "pre", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.opened = []

    def handle_starttag(self, tag, attrs):
        if tag in self.tags:
            self.parts.append(f"<{tag}>")
            self.opened.append(tag)
        elif tag == "a":
            href = safe_url(dict(attrs).get("href"))
            if href:
                self.parts.append(f'<a href="{escape(href, quote=True)}" target="_blank" rel="noopener noreferrer">')
                self.opened.append(tag)
        elif tag == "br":
            self.parts.append("<br>")

    def handle_endtag(self, tag):
        if tag in self.opened:
            while self.opened:
                closed = self.opened.pop()
                self.parts.append(f"</{closed}>")
                if closed == tag:
                    break

    def handle_data(self, data):
        self.parts.append(escape(data))

    def result(self):
        return "".join(self.parts) + "".join(f"</{tag}>" for tag in reversed(self.opened))


def safe_html(text, html=True):
    if not html:
        return escape(text or "")
    parser = SafeTelegramHTML()
    parser.feed(text or "")
    return parser.result()
