"""Paid rooftop runs. Each durable run is a single debit; only the server decides landings."""
import math
from datetime import datetime

from sqlalchemy import select, func
from app import db, wheel

COST = 100
# Left/right edges and angular speed of the approved four roofs.
LEVELS = ((315, 346, 2.05), (330, 359, 2.20), (340, 360, 2.35), (347, 367, 2.50))
BONUS = (1, 3, 7, 12)
OPEN = ("ready", "swing", "landed")


def landing(level, seconds):
    left, right, speed = LEVELS[level]
    phase = max(0.0, seconds) * speed
    angle = -.96 * math.cos(phase)
    rate = .96 * speed * math.sin(phase)
    x, y = 154 + 137 * math.sin(angle), 47 + 137 * math.cos(angle)
    vx, vy = 137 * math.cos(angle) * rate, -137 * math.sin(angle) * rate
    t = (-vy + math.sqrt(vy * vy + 1050 * (192 - y))) / 525
    x += vx * t
    return x, left <= x <= right


def record(run):
    if run is None:
        return None
    return dict(id=run.id, state=run.state, level=run.level, version=run.version,
                landing_x=run.landing_x, points=run.points)


async def latest(session, uid):
    return await session.scalar(select(db.RopeRun).where(db.RopeRun.user_id == uid)
                                .order_by(db.RopeRun.id.desc()).limit(1))


async def state(uid):
    async with db.SessionLocal() as session:
        row = await wheel.campaign(session)
        stats = {"banked": [0]*4, "lost": [0]*4}
        for status, level, count in await session.execute(select(db.RopeRun.state, db.RopeRun.level,
                func.count()).where(db.RopeRun.user_id == uid, db.RopeRun.state.in_(stats))
                .group_by(db.RopeRun.state, db.RopeRun.level)):
            stats[status][level] = count
        return dict(run=record(await latest(session, uid)), enabled=bool(row.enabled), stats=stats,
                    balance=(await wheel.totals(session, uid))["balance"], price=COST,
                    levels=[dict(left=l,right=r,speed=s,bonus=b) for (l,r,s),b in zip(LEVELS,BONUS)])


async def play(uid, body, received):
    action = body.get("action")
    expected = {"action", "request_id", "previous_id"} if action == "start" else {"action", "id", "version"}
    if set(body) != expected or action not in ("start", "arm", "release", "next", "bank"):
        raise ValueError("Недействительное действие игры.")
    async with db.SessionLocal() as session, session.begin():
        user = await session.get(db.User, uid, with_for_update=True)
        if not user or user.status != "approved":
            raise ValueError("Доступ к акции закрыт.")
        if action == "start":
            nonce = body["request_id"]
            if not isinstance(nonce, str) or not 16 <= len(nonce) <= 80 or type(body["previous_id"]) is not int:
                raise ValueError("Недействительный запрос старта.")
            prior = await session.scalar(select(db.RopeRun.id).where(
                db.RopeRun.user_id == uid, db.RopeRun.nonce == nonce))
            current = await latest(session, uid)
            if prior or (current and current.state in OPEN):
                return
            if (current.id if current else 0) != body["previous_id"]:
                raise ValueError("Обновите состояние забега.")
            if not (await wheel.campaign(session, lock=True)).enabled:
                raise ValueError("Акция сейчас на паузе.")
            if (await wheel.totals(session, uid))["balance"] < COST:
                raise ValueError("Для забега нужно 100 баллов.")
            session.add(db.RopeRun(user_id=uid, nonce=nonce, cost=COST))
            return
        if type(body["id"]) is not int or type(body["version"]) is not int:
            raise ValueError("Недействительный номер забега.")
        run = await session.scalar(select(db.RopeRun).where(db.RopeRun.id == body["id"],
                                   db.RopeRun.user_id == uid).with_for_update())
        if not run:
            raise ValueError("Забег не найден.")
        if run.version != body["version"]:
            return  # A retry observes the committed result without repeating the action.
        if action == "arm" and run.state in ("ready", "swing"):
            run.swing_at, run.state = received, "swing"
        elif action == "release" and run.state == "swing":
            x, ok = landing(run.level, (received - run.swing_at).total_seconds())
            run.landing_x, run.state = x, "landed" if ok else "lost"
            if not ok:
                run.finished_at = datetime.utcnow()
        elif action == "next" and run.state == "landed" and run.level < 3:
            run.level += 1
            run.state, run.landing_x = "ready", None
        elif action == "bank" and run.state == "landed":
            run.points, run.finished_at, run.state = BONUS[run.level], datetime.utcnow(), "banked"
        else:
            raise ValueError("Это действие уже недоступно.")
        run.version += 1
