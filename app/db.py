from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaypalTag(Base):
    __tablename__ = "paypal_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tag: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="available", index=True)
    issued_to_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="waiting_issue", index=True)
    paypal_tag_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("paypal_tags.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_or_create_user(user_id: int, username: str | None) -> None:
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            session.add(User(id=user_id, username=username))
        else:
            user.username = username
        await session.commit()


async def add_paypal_tags(tags: list[str]) -> tuple[int, int]:
    added = 0
    duplicates = 0
    async with SessionLocal() as session:
        existing = set(
            await session.scalars(select(PaypalTag.tag).where(PaypalTag.tag.in_(tags)))
        ) if tags else set()
        for tag in tags:
            if tag in existing:
                duplicates += 1
                continue
            session.add(PaypalTag(tag=tag))
            existing.add(tag)
            added += 1
        await session.commit()
    return added, duplicates


async def create_request(user_id: int, amount: int) -> Request:
    async with SessionLocal() as session:
        req = Request(user_id=user_id, amount=amount)
        session.add(req)
        await session.commit()
        await session.refresh(req)
        return req


async def get_request(request_id: int) -> Request | None:
    async with SessionLocal() as session:
        return await session.get(Request, request_id)


async def issue_paypal(request_id: int) -> tuple[Request | None, PaypalTag | None]:
    async with SessionLocal() as session:
        async with session.begin():
            req = await session.get(Request, request_id, with_for_update=True)
            if req is None or req.status != "waiting_issue":
                return req, None
            tag = await session.scalar(
                select(PaypalTag)
                .where(PaypalTag.status == "available")
                .order_by(PaypalTag.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if tag is None:
                return req, None
            tag.status = "issued"
            tag.issued_to_user_id = req.user_id
            tag.issued_at = datetime.utcnow()
            req.paypal_tag_id = tag.id
            req.status = "paypal_issued"
            req.updated_at = datetime.utcnow()
        await session.refresh(req)
        await session.refresh(tag)
        return req, tag


async def mark_paid_by_user(request_id: int, user_id: int) -> bool:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id)
        if req is None or req.user_id != user_id or req.status != "paypal_issued":
            return False
        req.status = "waiting_check"
        req.updated_at = datetime.utcnow()
        await session.commit()
        return True


async def set_request_status(request_id: int, status: str) -> Request | None:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id)
        if req is None:
            return None
        req.status = status
        req.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(req)
        return req


async def get_user_requests(user_id: int, limit: int = 10) -> list[Request]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(Request).where(Request.user_id == user_id).order_by(Request.id.desc()).limit(limit)
        )
        return list(rows)


async def get_requests(status: str | None = None, limit: int = 20) -> list[Request]:
    async with SessionLocal() as session:
        query = select(Request).order_by(Request.id.desc()).limit(limit)
        if status:
            query = query.where(Request.status == status)
        return list(await session.scalars(query))


async def get_user(user_id: int) -> User | None:
    async with SessionLocal() as session:
        return await session.get(User, user_id)


async def get_recent_users(limit: int = 20) -> list[User]:
    async with SessionLocal() as session:
        return list(await session.scalars(select(User).order_by(User.created_at.desc()).limit(limit)))


async def get_paypal_tags(status: str | None = None, limit: int = 30) -> list[PaypalTag]:
    async with SessionLocal() as session:
        query = select(PaypalTag).order_by(PaypalTag.id.desc()).limit(limit)
        if status:
            query = query.where(PaypalTag.status == status)
        return list(await session.scalars(query))


async def find_paypal_tag(value: str) -> PaypalTag | None:
    normalized = value.strip()
    if normalized and not normalized.startswith("@"):
        normalized = "@" + normalized
    async with SessionLocal() as session:
        return await session.scalar(select(PaypalTag).where(func.lower(PaypalTag.tag) == normalized.lower()))


async def delete_paypal_tag(value: str) -> tuple[bool, str]:
    normalized = value.strip()
    if normalized and not normalized.startswith("@"):
        normalized = "@" + normalized
    async with SessionLocal() as session:
        tag = await session.scalar(select(PaypalTag).where(func.lower(PaypalTag.tag) == normalized.lower()))
        if tag is None:
            return False, "not_found"
        if tag.status != "available":
            return False, "issued"
        await session.delete(tag)
        await session.commit()
        return True, "deleted"


async def count_available_tags() -> int:
    async with SessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(PaypalTag).where(PaypalTag.status == "available")) or 0)


async def get_admin_stats() -> dict[str, int]:
    today = datetime.utcnow() - timedelta(hours=24)
    async with SessionLocal() as session:
        users = int(await session.scalar(select(func.count()).select_from(User)) or 0)
        available = int(await session.scalar(select(func.count()).select_from(PaypalTag).where(PaypalTag.status == "available")) or 0)
        issued = int(await session.scalar(select(func.count()).select_from(PaypalTag).where(PaypalTag.status == "issued")) or 0)
        waiting_issue = int(await session.scalar(select(func.count()).select_from(Request).where(Request.status == "waiting_issue")) or 0)
        waiting_check = int(await session.scalar(select(func.count()).select_from(Request).where(Request.status == "waiting_check")) or 0)
        paid = int(await session.scalar(select(func.count()).select_from(Request).where(Request.status == "paid")) or 0)
        paid_24h = int(await session.scalar(select(func.count()).select_from(Request).where(Request.status == "paid", Request.updated_at >= today)) or 0)
    return {
        "users": users,
        "available": available,
        "issued": issued,
        "waiting_issue": waiting_issue,
        "waiting_check": waiting_check,
        "paid": paid,
        "paid_24h": paid_24h,
    }
