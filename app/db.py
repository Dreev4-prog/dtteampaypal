from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, select, text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
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
    screenshot_file_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    processed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # create_all не добавляет новые столбцы в уже существующие таблицы.
        # Поэтому обновляем таблицу users безопасными ALTER TABLE.
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20)"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS applied_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS decided_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS decided_by BIGINT"))

        # Все пользователи, которые были в базе до v1.3, сохраняют доступ.
        await conn.execute(text("UPDATE users SET status = 'approved' WHERE status IS NULL"))
        await conn.execute(text("ALTER TABLE users ALTER COLUMN status SET DEFAULT 'pending'"))
        await conn.execute(text("ALTER TABLE users ALTER COLUMN status SET NOT NULL"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_status ON users (status)"))

        # v1.4: произвольная сумма, скриншот и история обработки заявок.
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS screenshot_file_id VARCHAR(512)"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS processed_by BIGINT"))


async def get_or_create_user(user_id: int, username: str | None, full_name: str | None = None) -> User:
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            user = User(id=user_id, username=username, full_name=full_name, status="pending")
            session.add(user)
        else:
            user.username = username
            user.full_name = full_name
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


async def count_active_requests(user_id: int) -> int:
    active_statuses = {"waiting_issue", "paypal_issued", "waiting_check"}
    async with SessionLocal() as session:
        return int(await session.scalar(
            select(func.count()).select_from(Request).where(
                Request.user_id == user_id, Request.status.in_(active_statuses)
            )
        ) or 0)


async def create_request(user_id: int, amount: int, screenshot_file_id: str | None = None) -> Request:
    async with SessionLocal() as session:
        req = Request(user_id=user_id, amount=amount, screenshot_file_id=screenshot_file_id)
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
            req.processed_at = datetime.utcnow()
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


async def set_request_status(request_id: int, status: str, admin_id: int | None = None) -> Request | None:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id)
        if req is None:
            return None
        req.status = status
        req.updated_at = datetime.utcnow()
        if admin_id is not None:
            req.processed_by = admin_id
            req.processed_at = datetime.utcnow()
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


async def get_user_counts() -> dict[str, int]:
    from sqlalchemy import func

    counts = {"all": 0, "pending": 0, "approved": 0, "rejected": 0, "blocked": 0}
    async with SessionLocal() as session:
        counts["all"] = int(await session.scalar(select(func.count()).select_from(User)) or 0)
        rows = await session.execute(select(User.status, func.count(User.id)).group_by(User.status))
        for status, count in rows.all():
            if status in counts:
                counts[status] = int(count)
    return counts


async def list_users(status: str = "all", offset: int = 0, limit: int = 10) -> tuple[list[User], bool]:
    async with SessionLocal() as session:
        query = select(User)
        if status != "all":
            query = query.where(User.status == status)
        query = query.order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit + 1)
        rows = list(await session.scalars(query))
        return rows[:limit], len(rows) > limit


async def search_users(query_text: str, limit: int = 10) -> list[User]:
    from sqlalchemy import or_

    value = query_text.strip()
    if value.startswith("@"):
        value = value[1:]
    async with SessionLocal() as session:
        conditions = [User.username.ilike(f"%{value}%"), User.full_name.ilike(f"%{value}%")]
        if value.isdigit():
            conditions.append(User.id == int(value))
        rows = await session.scalars(
            select(User).where(or_(*conditions)).order_by(User.created_at.desc()).limit(limit)
        )
        return list(rows)


async def count_user_paypals(user_id: int) -> int:
    from sqlalchemy import func

    async with SessionLocal() as session:
        return int(await session.scalar(
            select(func.count()).select_from(PaypalTag).where(PaypalTag.issued_to_user_id == user_id)
        ) or 0)


async def count_waiting_requests() -> int:
    async with SessionLocal() as session:
        return int(await session.scalar(
            select(func.count()).select_from(Request).where(Request.status == "waiting_issue")
        ) or 0)


async def list_waiting_requests(offset: int = 0, limit: int = 10) -> tuple[list[Request], bool]:
    async with SessionLocal() as session:
        rows = list(await session.scalars(
            select(Request)
            .where(Request.status == "waiting_issue")
            .order_by(Request.created_at.asc(), Request.id.asc())
            .offset(offset)
            .limit(limit + 1)
        ))
        return rows[:limit], len(rows) > limit
