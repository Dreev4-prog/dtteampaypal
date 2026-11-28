"""Publish only newly confirmed DT Payments to the channel chosen by an admin."""
import asyncio
from datetime import datetime, timedelta
from html import escape
import logging
from pathlib import Path
import re

from aiogram.exceptions import (
    TelegramAPIError, TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter, TelegramServerError,
)
from aiogram.types import FSInputFile
from sqlalchemy import func, literal, select, text, update
from sqlalchemy.orm import aliased

from app import db

BANNER = Path(__file__).resolve().parent.parent / "assets" / "dt_payments_channel.jpg"
logger = logging.getLogger(__name__)
MANUAL_INTERVAL = timedelta(minutes=8)


def payment_caption(amount: int, tag: str, *, refunded=False, manual=False) -> str:
    anonymous = re.fullmatch(r"anonim-([0-9]+)", tag)
    worker = f"#аноним{anonymous[1]}" if anonymous else tag
    title = "↩️ <b>Оплата возвращена</b>" if refunded else "🗝 <b>DT TEAM · НОВЫЙ ЗАВОЗ</b>"
    amount_text = f"{amount:,}".replace(",", " ")
    source = "\n<i>Внесено вручную</i>" if manual else ""
    return (
        f"{title}\n\n"
        f"<b>{amount_text} €</b>\n"
        f"Воркер <b>{escape(worker)}</b>\n"
        f"Реквизит <b>♦️ REG EU</b>{source}\n\n"
        '<a href="https://t.me/DT_TEAM_PAYPAL_BOT">@DT_TEAM_PAYPAL_BOT</a>'
    )


async def set_channel(channel_id: int | None) -> None:
    async with db.SessionLocal() as session, session.begin():
        await session.execute(text("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (:key, :value, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """), {"key": db.DT_PAYMENTS_CHANNEL, "value": str(channel_id) if channel_id else ""})
        for post in (db.DTPaymentsPost, db.DTPaymentsManual):
            await session.execute(update(post).where(post.status == "pending", post.channel_id != (channel_id or 0))
                                  .values(status="skipped"))


async def channel_counts() -> dict[str, int]:
    totals: dict[str, int] = {}
    async with db.SessionLocal() as session:
        for post in (db.DTPaymentsPost, db.DTPaymentsManual):
            counts = await session.execute(select(post.status, func.count()).group_by(post.status))
            for status, count in counts:
                totals[status] = totals.get(status, 0) + count
    return totals


async def claim_post(*, manual=False):
    post = db.DTPaymentsManual if manual else db.DTPaymentsPost
    now = datetime.utcnow()
    async with db.SessionLocal() as session, session.begin():
        # A timed-out send may have reached Telegram already.
        await session.execute(update(post).where(post.status == "sending", post.next_attempt_at <= now)
                              .values(status="failed"))
        if manual:
            previous = aliased(db.DTPaymentsManual)
            earlier = select(previous.id).where(
                previous.batch_key == post.batch_key, previous.position < post.position,
                previous.status.in_(("pending", "sending")),
            ).exists()
            query = select(post, literal(None)).where(post.status == "pending", ~earlier)
            order = post.id
        else:
            query = (select(post, db.Request.status).join(db.Request, db.Request.id == post.request_id)
                     .where((post.status == "pending") | ((post.status == "posted") & (db.Request.status == "payment_refunded"))))
            order = post.request_id
        item = (await session.execute(query.where(post.next_attempt_at <= now)
                                     .order_by(post.next_attempt_at, order)
                                     .limit(1).with_for_update(of=post, skip_locked=True))).first()
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
    row = await claim_post() or await claim_post(manual=True)
    if row is None:
        return False
    manual = isinstance(row, db.DTPaymentsManual)
    identity = row.id if manual else row.request_id
    refund = row.message_id is not None
    caption = payment_caption(row.amount, row.tag, refunded=refund, manual=manual)
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
            logger.warning("DT Payments channel delivery failed for %s %s (%s)",
                           "manual record" if manual else "request", identity, type(exc).__name__)
    async with db.SessionLocal() as session, session.begin():
        model = type(row)
        key = model.id if manual else model.request_id
        now = datetime.utcnow()
        await session.execute(update(model).where(key == identity)
                              .values(status=status, message_id=message_id,
                                      next_attempt_at=now + timedelta(seconds=delay)))
        if manual and status == "posted":
            earliest = now + MANUAL_INTERVAL
            await session.execute(update(model).where(
                model.batch_key == row.batch_key, model.position == row.position + 1,
                model.status == "pending", model.next_attempt_at < earliest,
            ).values(next_attempt_at=earliest))
    return True


async def channel_post_loop(bot) -> None:
    while True:
        try:
            if await deliver_one(bot):
                continue
        except Exception:
            logger.exception("DT Payments channel worker failed")
        await asyncio.sleep(5)
