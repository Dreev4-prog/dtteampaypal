"""Recent personal events reconstructed from committed business records.

No delivery guesses or second ledger: restarting the bot cannot erase these
milestones, and the client never supplies a recipient ID.
"""
from datetime import timedelta, timezone
from sqlalchemy import select
from app import db


async def recent_events(user_id, admin=False):
    events = []

    def add(key, at, title, body, nav, label, tone="info"):
        if at is None:
            return
        stamp = at.replace(tzinfo=timezone.utc).isoformat()
        events.append(dict(id=f"{key}:{stamp}", at=stamp, title=title, body=body,
                           nav=nav, label=label, tone=tone))

    async with db.SessionLocal() as session:
        query = select(db.Request, db.PaypalTag.tag).outerjoin(db.PaypalTag, db.Request.paypal_tag_id == db.PaypalTag.id)
        if not admin:
            query = query.where(db.Request.user_id == user_id)
        rows = (await session.execute(query.order_by(db.Request.updated_at.desc(), db.Request.id.desc()).limit(30))).all()
        for req, tag in rows:
            own = req.user_id == user_id
            prefix = tag or f"Заявка #{req.id}"
            if admin and not own:
                prefix += f" · ID {req.user_id}"
            nav, label = ("my_paypals", "Мои PayPal") if own else ("admin_home", "Открыть управление")
            money = f"{float(req.payout_amount or 0):.2f} USDT"
            if req.status == "waiting_issue":
                add(f"request:{req.id}", req.created_at, "Заявка отправлена" if own else "Новая заявка на PayPal", f"{prefix} · {req.amount} €. Ожидает выдачи PayPal.", nav, label)
            if req.processed_at and req.paypal_tag_id:
                add(f"issued:{req.id}", req.processed_at, "PayPal выдан", f"{prefix} · заявка на {req.amount} €.", nav, label)
            if req.status == "waiting_check":
                add(f"check:{req.id}", req.paid_clicked_at or req.updated_at, "Оплата на проверке", f"{prefix} · {req.amount} €. Ожидает подтверждения администрации.", nav, label)
            if req.payment_confirmed_at:
                add(f"confirmed:{req.id}", req.payment_confirmed_at, "Оплата подтверждена", f"{prefix} · получение {req.amount} € подтверждено. Начисление доступно к выплате только после вывода с PayPal.", nav, label, "success")
            if req.withdrawal_retry_at and req.status == "withdrawal_pending":
                retry = req.withdrawal_retry_at.replace(tzinfo=timezone.utc).astimezone(db.MOSCOW_TZ).strftime("%d.%m в %H:%M")
                add(f"wait:{req.id}:{req.withdrawal_wait_count}", req.withdrawal_retry_at-timedelta(hours=24), "Ждём 24 часа", f"{prefix}. Вывести деньги пока не удалось. Следующая попытка — после {retry} МСК. {money} остаются в ожидании.", nav, label, "waiting")
            if req.paypal_withdrawn_at:
                add(f"withdrawn:{req.id}", req.paypal_withdrawn_at, "Деньги выведены с PayPal", f"{prefix}. На баланс к выплате начислено {money}.", "wallet" if own else "admin_home", "Открыть кошелёк" if own else label, "success")
            if req.payment_refunded_at:
                add(f"refund:{req.id}", req.payment_refunded_at, "Оплата возвращена", f"{prefix}. Начисление {money} отменено и исключено из выплат.", nav, label, "warning")
            problems = {"not_found": "Оплата не найдена", "paypal_limited": "PayPal стал недоступен", "gs": "Оплата Goods & Services", "returned": "Возврат PayPal принят", "returned_gestoppt": "PayPal переведён в Gestop", "returned_deleted": "PayPal удалён", "admin_recalled_deleted": "PayPal отозван", "return_pending": "Возврат на рассмотрении", "rejected": "Заявка отклонена"}
            if req.status in problems:
                add(f"status:{req.id}:{req.status}", req.updated_at, problems[req.status], f"{prefix}. Подробности и доступные действия — в карточке PayPal.", nav, label, "warning")
        payouts = select(db.ManualPayout)
        if not admin:
            payouts = payouts.where(db.ManualPayout.user_id == user_id)
        for payout in (await session.scalars(payouts.order_by(db.ManualPayout.created_at.desc(), db.ManualPayout.id.desc()).limit(20))).all():
            own = payout.user_id == user_id
            provider = "xRocket" if payout.provider == "xrocket" else "CryptoBot"
            body = f"{float(payout.total_amount):.2f} USDT через {provider}. Чек доступен в истории выплат."
            if not own:
                body = f"ID {payout.user_id} · " + body
            add(f"paid:{payout.id}", payout.created_at, "Выплата завершена", body, "wallet" if own else "admin_home", "История выплат" if own else "Открыть управление", "success")
    return sorted(events, key=lambda e: (e["at"], e["id"]), reverse=True)[:60]
