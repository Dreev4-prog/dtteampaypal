from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, select, text
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
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)


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

        # create_all не добавляет новые столбцы в уже существующие таблицы.
        # Поэтому обновляем таблицу users безопасными ALTER TABLE.
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20)"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS applied_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS decided_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS decided_by BIGINT"))

        # Все пользователи, которые были в базе до v1.3, сохраняют доступ.
        await conn.execute(text("UPDATE users SET status = 'approved' WHERE status IS NULL"))
        await conn.execute(text("ALTER TABLE users ALTER COLUMN status SET DEFAULT 'pending'"))
        await conn.execute(text("ALTER TABLE users ALTER COLUMN status SET NOT NULL"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_status ON users (status)"))


async def get_or_create_user(user_id: int, username: str | None) -> User:
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            user = User(id=user_id, username=username, status="pending")
            session.add(user)
        else:
            user.username = username
        await session.commit()
        await session.refresh(user)
        return user


async def get_user(user_id: int) -> User | None:
    async with SessionLocal() as session:
        return await session.get(User, user_id)


async def submit_membership_application(user_id: int) -> User | None:
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None or user.status in {"approved", "blocked"}:
            return user
        if user.applied_at is None:
            user.applied_at = datetime.utcnow()
        user.status = "pending"
        await session.commit()
        await session.refresh(user)
        return user


async def set_user_access_status(user_id: int, status: str, admin_id: int) -> User | None:
    if status not in {"approved", "rejected", "blocked", "pending"}:
        raise ValueError("Unsupported user status")

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            return None
        user.status = status
        user.decided_at = datetime.utcnow()
        user.decided_by = admin_id
        await session.commit()
        await session.refresh(user)
        return user


async def add_paypal_tags(tags: list[str]) -> tuple[int, int]:
    added = 0
    duplicates = 0
    async with SessionLocal() as session:
        for tag in tags:
            exists = await session.scalar(select(PaypalTag).where(PaypalTag.tag == tag))
            if exists:
                duplicates += 1
                continue
            session.add(PaypalTag(tag=tag))
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


async def get_user_requests(user_id: int) -> list[Request]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(Request)
            .where(Request.user_id == user_id)
            .order_by(Request.id.desc())
            .limit(10)
        )
        return list(rows)


async def count_available_tags() -> int:
    async with SessionLocal() as session:
        rows = await session.scalars(select(PaypalTag).where(PaypalTag.status == "available"))
        return len(list(rows))
