"""Announce matured stock; the SQL availability gate works without this task."""
import asyncio
import logging

from app.db import claim_matured_paypal_stock


async def announce_matured_stock(bot, notify) -> None:
    for gender in sorted(await claim_matured_paypal_stock()):
        await notify(bot, gender)


async def stock_warmup_loop(bot, notify) -> None:
    while True:
        try:
            await announce_matured_stock(bot, notify)
        except Exception:
            logging.exception("Не удалось отправить уведомления о PayPal после выдержки")
        await asyncio.sleep(30)
