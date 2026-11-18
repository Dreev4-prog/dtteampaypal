"""DT Wheel ledger. All grants use the same transaction as the source operation.

Lock order: User first; campaign is a global draw/toggle lock. Admin toggles
never acquire a user lock. PostgreSQL READ COMMITTED + FOR UPDATE is required
in production. No background recalculation or historical payment backfill.
"""
from datetime import datetime, timezone
from decimal import Decimal
import logging
import secrets

from sqlalchemy import select, func, text, literal, union_all
from app import db

THRESHOLD = 150
JACKPOT_DENOMINATOR = 1_000_000_000_000
ORDINARY = ("one", "five", "two", "ten", "four", "one", "five", "two", "cash", "four",
            "one", "five", "two", "ten", "four", "one", "five", "two", "ten", "four")
PRIZES = {"one": (1, 0), "two": (2, 0), "four": (4, 0), "five": (5, 0),
          "ten": (10, 0), "cash": (0, 20), "jackpot": (0, 500)}


async def migrate(conn):
    await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS wheel_bonus_percent INTEGER NOT NULL DEFAULT 0"))
    await conn.execute(text("ALTER TABLE balance_entries ALTER COLUMN request_id DROP NOT NULL"))
    await conn.execute(text("ALTER TABLE balance_entries ADD COLUMN IF NOT EXISTS wheel_spin_id INTEGER REFERENCES wheel_spins(id)"))
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_balance_wheel_spin ON balance_entries (wheel_spin_id)"))
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_wheel_single_jackpot ON wheel_spins (prize) WHERE prize = 'jackpot'"))
    await conn.execute(text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'balance_entries'::regclass
                           AND conname = 'ck_balance_origin') THEN
                ALTER TABLE balance_entries ADD CONSTRAINT ck_balance_origin CHECK (
                    (request_id IS NOT NULL AND wheel_spin_id IS NULL) OR
                    (request_id IS NULL AND wheel_spin_id IS NOT NULL));
            END IF;
        END $$
    """))
    await conn.execute(text("INSERT INTO wheel_campaign (id, enabled, revision) VALUES (1, 0, 0) ON CONFLICT (id) DO NOTHING"))

    await grant_admin_trials(conn, db.settings.admin_ids)


async def grant_admin_trials(conn, admin_ids):
    """Issue this one-off grant to the configured admins in the startup transaction."""
    if await db.grant_three_admin_trials(conn, admin_ids, "admin_wheel_trials_nov_2026", db.AdminWheelTrial.__table__):
        logging.getLogger(__name__).info("Issued 3 test spins each to %d admins", len(admin_ids))


def trial_record(row):
    points, cash = PRIZES[row.prize]
    return dict(id=row.slot, prize=row.prize, points=points, cash=cash, test=True)


async def admin_trials(admin_id, nonce=None):
    """Load or use a trial. No payment, campaign or live prize records are touched."""
    if nonce is not None and (not isinstance(nonce, str) or not 16 <= len(nonce) <= 80):
        raise ValueError("Недействительный запрос вращения.")
    async with db.SessionLocal() as session, session.begin():
        stmt = select(db.AdminWheelTrial).where(db.AdminWheelTrial.admin_id == admin_id).order_by(db.AdminWheelTrial.slot)
        if nonce is not None:
            stmt = stmt.with_for_update()
        slots = list(await session.scalars(stmt))
        result = None
        if nonce is not None:
            slot = next((r for r in slots if r.nonce == nonce), None)
            if slot is None:
                slot = next((r for r in slots if r.nonce is None), None)
                if slot is None:
                    raise ValueError("Все тестовые вращения использованы.")
                slot.nonce, slot.prize = nonce, choose_prize(False)
            result = trial_record(slot)
        history = [trial_record(r) for r in reversed(slots) if r.prize]
        state = dict(remaining=len(slots) - len(history), total=len(slots), history=history)
        return dict(result=result, wheel=state)


async def campaign(session, *, lock=False):
    # Insert only when missing (also supports isolated tests). Never reset state.
    row = await session.get(db.WheelCampaign, 1)
    if row is None:
        await session.execute(text("INSERT INTO wheel_campaign (id, enabled, revision) VALUES (1, 0, 0) ON CONFLICT (id) DO NOTHING"))
    query = select(db.WheelCampaign).where(db.WheelCampaign.id == 1)
    if lock:
        query = query.execution_options(populate_existing=True).with_for_update()
    return await session.scalar(query)


def stamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def spin_record(row):
    return dict(id=row.id, prize=row.prize, points=row.points, cash=row.cash,
                at=stamp(row.created_at), used_request_id=row.used_request_id, used_at=stamp(row.used_at))


async def set_enabled(enabled: bool, admin_id: int, expected_revision: int):
    async with db.SessionLocal() as session, session.begin():
        row = await campaign(session, lock=True)
        if row.revision != expected_revision:
            return "stale"
        if bool(row.enabled) == bool(enabled):
            return "unchanged"
        now = datetime.utcnow()
        if enabled:
            session.add(db.WheelPeriod(started_at=now, started_by=admin_id))
            row.started_at = row.started_at or now
        else:
            period = await session.scalar(select(db.WheelPeriod).where(db.WheelPeriod.ended_at.is_(None)).order_by(db.WheelPeriod.id.desc()).limit(1))
            if period:
                period.ended_at, period.ended_by = now, admin_id
        row.enabled, row.revision = int(enabled), row.revision + 1
        row.changed_at, row.changed_by = now, admin_id
    return "changed"


def coupons_query(user_id):
    parts = []
    for model, source, when in ((db.WheelSpin, "wheel", db.WheelSpin.created_at),
                                (db.RopeRun, "rope", db.RopeRun.finished_at)):
        parts.append(select(model.id.label("id"), literal(source).label("source"),
                            model.points.label("points"), when.label("at")).where(
            model.user_id == user_id, model.points > 0, model.used_request_id.is_(None)))
    pool = union_all(*parts).subquery()
    return select(pool).order_by(pool.c.at, pool.c.source, pool.c.id)


async def on_confirmation(session, req, base_percent):
    """Called with user + request locks, before the held balance is inserted."""
    row = await campaign(session, lock=True)
    # Timestamp is assigned after the activation lock: boundary races have one
    # total order. Merely being withdrawn after launch can never qualify a row.
    now = datetime.utcnow()
    req.payment_confirmed_at = now
    if row.enabled:
        period = await session.scalar(select(db.WheelPeriod).where(db.WheelPeriod.ended_at.is_(None)).order_by(db.WheelPeriod.id.desc()).limit(1))
        if period is None:
            raise RuntimeError("Active wheel has no activation period")
        session.add(db.WheelPayment(request_id=req.id, user_id=req.user_id, period_id=period.id,
                                   amount=req.amount, confirmed_at=now))
    first = (await session.execute(coupons_query(req.user_id).limit(1))).mappings().first()
    req.wheel_bonus_percent = first["points"] if first else 0
    if first:
        model = db.RopeRun if first["source"] == "rope" else db.WheelSpin
        coupon = await session.get(model, first["id"], with_for_update=True)
        coupon.used_request_id, coupon.used_at = req.id, now
    return base_percent + req.wheel_bonus_percent


async def totals(session, user_id):
    payment = db.WheelPayment
    def principal(credited):
        return select(func.coalesce(func.sum(payment.amount), 0)).where(payment.user_id == user_id,
                payment.cancelled_at.is_(None), credited).scalar_subquery()

    spins = select(func.count(db.WheelSpin.id)).where(db.WheelSpin.user_id == user_id)
    runs = select(func.coalesce(func.sum(db.RopeRun.cost), 0)).where(db.RopeRun.user_id == user_id)
    qualified, waiting, used, rope_spent = (await session.execute(select(
        principal(payment.credited_at.is_not(None)), principal(payment.credited_at.is_(None)),
        spins.scalar_subquery(), runs.scalar_subquery()))).one()
    # After a refund, later qualifying payments cover previously spent points first.
    unspent = qualified - used * THRESHOLD - rope_spent
    return dict(qualified=qualified, balance=max(0, unspent), rope_spent=rope_spent, used=used, available=max(0, unspent // THRESHOLD),
                progress=max(0, unspent) % THRESHOLD, debt=max(0, -unspent), waiting=waiting,
                remaining=THRESHOLD - max(0, unspent) % THRESHOLD + max(0, -unspent))


async def on_withdrawal(session, req):
    payment = await session.get(db.WheelPayment, req.id)
    if payment is None or payment.credited_at or payment.cancelled_at:
        return
    payment.credited_at = req.paypal_withdrawn_at
    await session.flush()
    after = await totals(session, req.user_id)
    req._dt_credit = payment.amount
    req._wheel_progress = after


async def on_refund(session, req):
    payment = await session.get(db.WheelPayment, req.id)
    if payment:
        payment.cancelled_at = req.payment_refunded_at
    # A returned payment must not burn an earned next-payment coupon.
    for model in (db.WheelSpin, db.RopeRun):
        coupon = await session.scalar(select(model).where(model.used_request_id == req.id).with_for_update())
        if coupon:
            coupon.used_request_id = coupon.used_at = None


def choose_prize(jackpot_claimed):
    if not jackpot_claimed and secrets.randbelow(JACKPOT_DENOMINATOR) == 0:
        return "jackpot"
    return ORDINARY[secrets.randbelow(len(ORDINARY))]


async def spin(user_id, nonce):
    if not isinstance(nonce, str) or not 16 <= len(nonce) <= 80:
        raise ValueError("Недействительный запрос вращения.")
    async with db.SessionLocal() as session, session.begin():
        user = await session.get(db.User, user_id, with_for_update=True)
        if user is None or user.status != "approved":
            raise ValueError("Доступ к акции закрыт.")
        previous = await session.scalar(select(db.WheelSpin).where(db.WheelSpin.user_id == user_id, db.WheelSpin.nonce == nonce))
        if previous:
            return spin_record(previous)
        row = await campaign(session, lock=True)
        if not row.enabled:
            raise ValueError("Акция сейчас выключена. Заработанные бонусы сохранены.")
        balance = await totals(session, user_id)
        if balance["balance"] < THRESHOLD:
            raise ValueError("Пока нет доступных вращений.")
        key = choose_prize(row.jackpot_spin_id is not None)
        points, cash = PRIZES[key]
        prize = db.WheelSpin(user_id=user_id, nonce=nonce, prize=key, points=points, cash=cash)
        session.add(prize)
        await session.flush()
        if cash:
            session.add(db.BalanceEntry(user_id=user_id, request_id=None, wheel_spin_id=prize.id,
                                       amount=Decimal(cash), status="available"))
        if key == "jackpot":
            row.jackpot_spin_id = prize.id
        await session.flush()
        return spin_record(prize)


async def has_open_run(session, user_id):
    return bool(await session.scalar(select(db.RopeRun.id).where(db.RopeRun.user_id == user_id,
                db.RopeRun.state.in_(("ready", "swing", "landed"))).limit(1)))


async def state(user_id, *, admin=False):
    async with db.SessionLocal() as session:
        row = await campaign(session)
        open_run = await has_open_run(session, user_id)
        if not row.enabled and not admin and not open_run:
            return {"enabled": False}
        result = dict(enabled=bool(row.enabled), revision=row.revision, started_at=stamp(row.started_at),
                      changed_at=stamp(row.changed_at), jackpot_claimed=row.jackpot_spin_id is not None,
                      threshold=THRESHOLD, open_run=open_run, **await totals(session, user_id))
        history = list(await session.scalars(select(db.WheelSpin).where(db.WheelSpin.user_id == user_id)
                                             .order_by(db.WheelSpin.id.desc()).limit(50)))
        coupons = [dict(id=v.id, points=v.points, source=v.source, at=stamp(v.at))
                   for v in await session.execute(coupons_query(user_id))]
        result.update(history=[spin_record(v) for v in history], coupons=coupons)
        if admin:
            result["statistics"] = dict(
                spins=int(await session.scalar(select(func.count(db.WheelSpin.id))) or 0),
                cash=int(await session.scalar(select(func.coalesce(func.sum(db.WheelSpin.cash), 0))) or 0),
                participants=int(await session.scalar(select(func.count(func.distinct(db.WheelPayment.user_id)))) or 0))
        return result


async def payment_note(request_id):
    async with db.SessionLocal() as session:
        payment = await session.get(db.WheelPayment, request_id)
        if payment is None:
            return ""
        return f"\n\n🪙 Игры DT: после вывода с PayPal будет начислено {payment.amount} баллов."


async def summary(user_id):
    async with db.SessionLocal() as session:
        row = await campaign(session)
        open_run = await has_open_run(session, user_id)
        if not row.enabled and not open_run:
            return {"enabled": False}
        return {"enabled": bool(row.enabled), "open_run": open_run, "revision": row.revision, **await totals(session, user_id)}
