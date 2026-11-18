"""Admin-only, paginated reports over durable wheel and rope records."""
from sqlalchemy import Integer, select, func, literal, union_all, case
from app import db, wheel

PAGE_SIZE = 20


def activity(uid=None):
    w, r = db.WheelSpin, db.RopeRun
    spins = select(w.id.label("id"), w.user_id.label("uid"), literal("wheel").label("game"),
                   literal("won").label("status"), w.created_at.label("at"), w.points.label("points"),
                   w.cash.label("cash"), literal(wheel.THRESHOLD).label("cost"), literal(None).cast(Integer).label("level"),
                   w.used_request_id.label("applied"))
    runs = select(r.id, r.user_id, literal("rope"), r.state, func.coalesce(r.finished_at, r.created_at),
                  r.points, literal(0), r.cost, r.level, r.used_request_id)
    if uid is not None:
        spins = spins.where(w.user_id == uid)
        runs = runs.where(r.user_id == uid)
    return union_all(spins, runs).subquery()


def measures(a):
    def count(condition, name):
        return func.coalesce(func.sum(case((condition, 1), else_=0)), 0).label(name)
    return (count(a.c.game == "wheel", "spins"), count(a.c.game == "rope", "runs"),
            count(a.c.status == "lost", "failed"), count(a.c.status == "banked", "banked"),
            count(a.c.status.in_(("ready","swing","landed")), "open"),
            count(a.c.status.in_(("won","banked")), "awards"),
            func.coalesce(func.sum(a.c.cash), 0).label("cash"), func.coalesce(func.sum(a.c.cost), 0).label("spent"))


async def report(page=0, uid=None):
    a = activity(uid)
    async with db.SessionLocal() as session:
        stats = dict((await session.execute(select(*measures(a)))).mappings().one())
        if uid is None:
            groups = select(a.c.uid, *measures(a), func.max(a.c.at).label("last")).group_by(a.c.uid).subquery()
            query = select(groups, db.User.username, db.User.full_name).join(db.User, db.User.id == groups.c.uid
                    ).order_by(groups.c.last.desc(), groups.c.uid)
        else:
            query = select(a).order_by(a.c.at.desc(), a.c.game, a.c.id.desc())
        rows = [dict(row) for row in (await session.execute(query.offset(page*PAGE_SIZE).limit(PAGE_SIZE+1))).mappings()]
        for row in rows:
            key = "last" if uid is None else "at"
            row[key] = wheel.stamp(row[key])
        return dict(stats=stats, rows=rows[:PAGE_SIZE], more=len(rows)>PAGE_SIZE, page=page, uid=uid)
