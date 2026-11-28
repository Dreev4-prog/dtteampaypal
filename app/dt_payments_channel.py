"""Publish only newly confirmed DT Payments to the channel chosen by an admin."""
import asyncio
from datetime import datetime, timedelta, timezone
from html import escape
import logging
from pathlib import Path

from aiogram.exceptions import (
    TelegramAPIError, TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter, TelegramServerError,
)
from aiogram.types import FSInputFile
from sqlalchemy import func, select, text, update

from app import db

BANNER = Path(__file__).resolve().parent.parent / "assets" / "dt_payments_channel.jpg"
logger = logging.getLogger(__name__)


def payment_caption(amount: int, tag: str, confirmed_at: datetime, *, refunded=False) -> str:
    moscow = confirmed_at.replace(tzinfo=timezone.utc).astimezone(db.MOSCOW_TZ)
    title = "↩️ <b>Оплата возвращена</b>" if refunded else "✅ <b>Оплата подтверждена</b>"
    amount_text = f"{amount:,}".replace(",", " ")
    return (
        f"{title}\n\n"
        f"💶 <b>{amount_text} €</b>\n"
        f"🏷 <b>{escape(tag)}</b>\n"
        f"🕒 {moscow:%d.%m.%Y · %H:%M} МСК"
    )


async def set_channel(channel_id: int | None) -> None:
    async with db.SessionLocal() as session, session.begin():
        await session.execute(text("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (:key, :value, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """), {"key": db.DT_PAYMENTS_CHANNEL, "value": str(channel_id) if channel_id else ""})
        post = db.DTPaymentsPost
        await session.execute(update(post).where(post.status == "pending", post.channel_id != (channel_id or 0))
                              .values(status="skipped"))


async def channel_counts() -> dict[str, int]:
    post = db.DTPaymentsPost
    async with db.SessionLocal() as session:
        return dict((await session.execute(select(post.status, func.count()).group_by(post.status))).all())


async def claim_post():
    post = db.DTPaymentsPost
    now = datetime.utcnow()
    async with db.SessionLocal() as session, session.begin():
        # An interrupted send may already have reached Telegram. Replaying it
        # automatically could publish the same payment twice.
        await session.execute(update(post).where(post.status == "sending", post.next_attempt_at <= now)
                              .values(status="failed"))
        item = (await session.execute(
            select(post, db.Request.status).join(db.Request, db.Request.id == post.request_id)
            .where(post.next_attempt_at <= now,
                   (post.status == "pending") | ((post.status == "posted") & (db.Request.status == "payment_refunded")))
            .order_by(post.next_attempt_at, post.request_id)
            .limit(1).with_for_update(of=post, skip_locked=True)
        )).first()
        if item is None:
            return None
        row, request_status = item
        if row.status == "posted":
            row.next_attempt_at = now + timedelta(minutes=2)
        else:
            channel = await session.get(db.AppSetting, db.DT_PAYMENTS_CHANNEL)
            if request_status == "payment_refunded" or channel is None or channel.value != str(row.channel_id):
                row.status = "skipped"
                return None
            row.status, row.next_attempt_at = "sending", now + timedelta(minutes=2)
        return row


async def deliver_one(bot) -> bool:
    row = await claim_post()
    if row is None:
        return False
    refund = row.message_id is not None
    caption = payment_caption(row.amount, row.tag, row.confirmed_at, refunded=refund)
    message_id = row.message_id
    delay = 0
    try:
        if refund:
            await bot.edit_message_caption(chat_id=row.channel_id, message_id=message_id,
                                           caption=caption, request_timeout=20)
        else:
            msg = await bot.send_photo(row.channel_id, FSInputFile(BANNER), caption=caption, request_timeout=20)
            message_id = msg.message_id
        status = "refunded" if refund else "posted"
    except TelegramRetryAfter as exc:
        status = "posted" if refund else "pending"
        delay = max(1, exc.retry_after)
    except (TelegramAPIError, asyncio.TimeoutError, OSError) as exc:
        if refund and isinstance(exc, TelegramBadRequest) and "message is not modified" in str(exc).lower():
            status = "refunded"
        elif refund and isinstance(exc, (TelegramNetworkError, TelegramServerError, asyncio.TimeoutError)):
            status, delay = "posted", 60  # Repeating a caption edit is safe.
        else:
            status = "refund_failed" if refund else "failed"
            logger.warning("DT Payments channel delivery failed for request %s (%s)",
                           row.request_id, type(exc).__name__)
    async with db.SessionLocal() as session, session.begin():
        await session.execute(update(db.DTPaymentsPost)
                              .where(db.DTPaymentsPost.request_id == row.request_id)
                              .values(status=status, message_id=message_id,
                                      next_attempt_at=datetime.utcnow() + timedelta(seconds=delay)))
    return True


async def channel_post_loop(bot) -> None:
    while True:
        try:
            if await deliver_one(bot):
                continue
        except Exception:
            logger.exception("DT Payments channel worker failed")
        await asyncio.sleep(5)
