from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, select, text, func
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
    payout_method: Mapped[str] = mapped_column(String(20), default="cryptobot", index=True)


class PaypalTag(Base):
    __tablename__ = "paypal_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tag: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="available", index=True)
    issued_to_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    gender: Mapped[str] = mapped_column(String(12), default="male", index=True)
    gs_screenshot_file_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="waiting_issue", index=True)
    paypal_tag_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("paypal_tags.id"), nullable=True)
    screenshot_file_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    paypal_gender: Mapped[str] = mapped_column(String(12), default="male", index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    processed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    paid_clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    payment_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    payment_confirmed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    payout_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    payout_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    payout_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payout_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    collection_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    keep_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class PaypalReturn(Base):
    __tablename__ = "paypal_returns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(Integer, ForeignKey("requests.id"), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    paypal_tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("paypal_tags.id"), index=True)
    reason_code: Mapped[str] = mapped_column(String(32))
    reason_text: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    admin_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)


class BalanceEntry(Base):
    __tablename__ = "balance_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    request_id: Mapped[int] = mapped_column(Integer, ForeignKey("requests.id"), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="available", index=True)
    payout_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ManualPayout(Base):
    __tablename__ = "manual_payouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    provider: Mapped[str] = mapped_column(String(20), index=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class RateRule(Base):
    __tablename__ = "rate_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    min_amount: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    percent: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now())


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(4096), nullable=False)
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
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS payout_method VARCHAR(20)"))
        await conn.execute(text("UPDATE users SET payout_method = 'cryptobot' WHERE payout_method IS NULL"))
        await conn.execute(text("ALTER TABLE users ALTER COLUMN payout_method SET DEFAULT 'cryptobot'"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_payout_method ON users (payout_method)"))

        # Все пользователи, которые были в базе до v1.3, сохраняют доступ.
        await conn.execute(text("UPDATE users SET status = 'approved' WHERE status IS NULL"))
        await conn.execute(text("ALTER TABLE users ALTER COLUMN status SET DEFAULT 'pending'"))
        await conn.execute(text("ALTER TABLE users ALTER COLUMN status SET NOT NULL"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_status ON users (status)"))

        # v1.4: произвольная сумма, скриншот и история обработки заявок.
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS screenshot_file_id VARCHAR(512)"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS processed_by BIGINT"))

        # v1.5: постоянная CRM оплат и контроль выплат клиентам.
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS paid_clicked_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS payment_confirmed_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS payment_confirmed_by BIGINT"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS payout_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS payout_by BIGINT"))
        # Старые подтверждённые оплаты становятся ожидающими выплаты.
        await conn.execute(text("UPDATE requests SET status = 'payout_pending' WHERE status = 'paid'"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_requests_status ON requests (status)"))

        # v1.6: автоматический расчёт процентов и суммы к выплате.
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS payout_percent INTEGER"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS payout_amount NUMERIC(12,2)"))
        # v1.6.8: изображение, прикреплённое к отдельному PayPal.
        await conn.execute(text("ALTER TABLE paypal_tags ADD COLUMN IF NOT EXISTS photo_file_id VARCHAR(512)"))
        # v1.6.9: пол PayPal и GS-архив.
        await conn.execute(text("ALTER TABLE paypal_tags ADD COLUMN IF NOT EXISTS gender VARCHAR(12) DEFAULT 'male'"))
        await conn.execute(text("ALTER TABLE paypal_tags ADD COLUMN IF NOT EXISTS gs_screenshot_file_id VARCHAR(512)"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS paypal_gender VARCHAR(12) DEFAULT 'male'"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_paypal_tags_gender ON paypal_tags (gender)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_requests_paypal_gender ON requests (paypal_gender)"))

        # v1.6.4: возвраты и массовый сбор PayPal.
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS collection_notified_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS keep_confirmed_at TIMESTAMP"))
        # v1.6.5: режим Start Work / Stop Work и редактируемые уведомления.
        await conn.execute(text("""
            INSERT INTO app_settings (key, value, updated_at) VALUES
            ('work_enabled', '0', CURRENT_TIMESTAMP),
            ('start_work_message', '🚀 <b>START WORK</b>\n\nПриём заявок на PayPal открыт. Можно создавать новые заявки.', CURRENT_TIMESTAMP),
            ('stop_work_message', '🛑 <b>STOP WORK</b>\n\nПриём новых заявок на PayPal остановлен. Продолжайте работу только с уже выданными PayPal.', CURRENT_TIMESTAMP),
            ('start_work_image', '', CURRENT_TIMESTAMP),
            ('stop_work_image', '', CURRENT_TIMESTAMP),
            ('content_home_text', '━━━━━━━━━━━━━━━━━━\n<b>DT TEAM · PAYPAL SERVICE</b>\n━━━━━━━━━━━━━━━━━━\n\n👋 Добро пожаловать в закрытый сервис DT Team.\n\nПолучайте PayPal, отслеживайте заявки и выплаты в одном месте.\n\n{status}\n\n━━━━━━━━━━━━━━━━━━', CURRENT_TIMESTAMP),
            ('content_home_image', '', CURRENT_TIMESTAMP),
            ('content_paypal_text', '━━━━━━━━━━━━━━━━━━\n<b>💳 НОВАЯ ЗАЯВКА</b>\n━━━━━━━━━━━━━━━━━━\n\nВведите необходимую сумму в евро одним числом.\n\nПример: <code>150</code>\n\nСледующий шаг — выбор типа PayPal\n\n━━━━━━━━━━━━━━━━━━', CURRENT_TIMESTAMP),
            ('content_support_text', '🆘 <b>ПОДДЕРЖКА</b>\n\nЕсли у вас возникли вопросы,\nобратитесь в службу поддержки.\n\n💬 <b>Чат поддержки:</b>\n@workzin\n@profitgeld', CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO NOTHING
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_paypal_returns_status ON paypal_returns (status)"))
        # Для существующей таблицы задаём серверное значение даты: raw SQL INSERT иначе не применяет Python default.
        await conn.execute(text("ALTER TABLE rate_rules ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP"))
        await conn.execute(text("INSERT INTO rate_rules (min_amount, percent, created_at) VALUES (50, 60, CURRENT_TIMESTAMP) ON CONFLICT (min_amount) DO NOTHING"))
        await conn.execute(text("INSERT INTO rate_rules (min_amount, percent, created_at) VALUES (100, 70, CURRENT_TIMESTAMP) ON CONFLICT (min_amount) DO NOTHING"))
        await conn.execute(text("""
            WITH matched_rates AS (
                SELECT req.id AS request_id, rule.percent
                FROM requests AS req
                JOIN LATERAL (
                    SELECT rr.percent
                    FROM rate_rules AS rr
                    WHERE rr.min_amount <= req.amount
                    ORDER BY rr.min_amount DESC
                    LIMIT 1
                ) AS rule ON TRUE
                WHERE req.status IN ('payout_pending', 'paid_out')
                  AND (req.payout_percent IS NULL OR req.payout_amount IS NULL)
            )
            UPDATE requests AS req
            SET payout_percent = matched_rates.percent,
                payout_amount = ROUND((req.amount * matched_rates.percent / 100.0)::numeric, 2)
            FROM matched_rates
            WHERE req.id = matched_rates.request_id
        """))


        # v2.2: переносим существующие начисления в журнал баланса.
        await conn.execute(text("""
            INSERT INTO balance_entries (user_id, request_id, amount, status, created_at, paid_at)
            SELECT r.user_id, r.id, r.payout_amount,
                   CASE WHEN r.status = 'paid_out' THEN 'paid' ELSE 'available' END,
                   COALESCE(r.payment_confirmed_at, r.updated_at, CURRENT_TIMESTAMP),
                   CASE WHEN r.status = 'paid_out' THEN COALESCE(r.payout_at, r.updated_at, CURRENT_TIMESTAMP) ELSE NULL END
            FROM requests r
            WHERE r.status IN ('payout_pending', 'paid_out')
              AND r.payout_amount IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM balance_entries b WHERE b.request_id = r.id)
        """))


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


async def add_paypal_tag(tag: str, photo_file_id: str | None = None, gender: str = "male") -> tuple[PaypalTag | None, bool]:
    """Добавляет один PayPal. Возвращает (объект, был_дубликат)."""
    async with SessionLocal() as session:
        exists = await session.scalar(select(PaypalTag).where(PaypalTag.tag == tag))
        if exists:
            return exists, True
        item = PaypalTag(tag=tag, photo_file_id=photo_file_id, gender=gender)
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item, False


async def add_paypal_tags(tags: list[str], gender: str = "male") -> tuple[int, int]:
    added = 0
    duplicates = 0
    async with SessionLocal() as session:
        for tag in tags:
            exists = await session.scalar(select(PaypalTag).where(PaypalTag.tag == tag))
            if exists:
                duplicates += 1
                continue
            session.add(PaypalTag(tag=tag, gender=gender))
            added += 1
        await session.commit()
    return added, duplicates


async def count_active_requests(user_id: int) -> int:
    active_statuses = {"waiting_issue"}
    async with SessionLocal() as session:
        return int(await session.scalar(
            select(func.count()).select_from(Request).where(
                Request.user_id == user_id, Request.status.in_(active_statuses)
            )
        ) or 0)


async def create_request(user_id: int, amount: int, screenshot_file_id: str | None = None, paypal_gender: str = "male") -> Request:
    async with SessionLocal() as session:
        req = Request(user_id=user_id, amount=amount, screenshot_file_id=screenshot_file_id, paypal_gender=paypal_gender)
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
                .where(PaypalTag.status == "available", PaypalTag.gender == req.paypal_gender)
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


async def update_request_amount(request_id: int, amount: int, user_id: int | None = None) -> Request | None:
    """Replace the single current amount for a request.

    When user_id is supplied, only the request owner may change it and only
    while PayPal has been issued. Admin flows call it without user_id.
    """
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None:
            return None
        if user_id is not None and (req.user_id != user_id or req.status != "paypal_issued"):
            return None
        req.amount = amount
        if req.status in {"payout_pending", "paid_out"}:
            percent = await _get_rate_percent(session, amount)
            req.payout_percent = percent
            req.payout_amount = round(amount * percent / 100, 2) if percent is not None else None
        req.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(req)
        return req


async def mark_paid_by_user(request_id: int, user_id: int) -> bool:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id)
        if req is None or req.user_id != user_id or req.status != "paypal_issued":
            return False
        req.status = "waiting_check"
        req.paid_clicked_at = datetime.utcnow()
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


async def get_user_requests_by_statuses(user_id: int, statuses: tuple[str, ...], limit: int = 50) -> list[Request]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(Request)
            .where(Request.user_id == user_id, Request.status.in_(statuses))
            .order_by(Request.updated_at.desc(), Request.id.desc())
            .limit(limit)
        )
        return list(rows)


async def get_user_profit_summary(user_id: int) -> dict[str, float | int | datetime | None]:
    async with SessionLocal() as session:
        total, count, last_at = (await session.execute(
            select(
                func.coalesce(func.sum(Request.payout_amount), 0),
                func.count(Request.id),
                func.max(Request.payout_at),
            ).where(Request.user_id == user_id, Request.status == "paid_out")
        )).one()
        pending = await session.scalar(
            select(func.coalesce(func.sum(Request.payout_amount), 0)).where(
                Request.user_id == user_id, Request.status == "payout_pending"
            )
        )
        count_int = int(count or 0)
        total_float = float(total or 0)
        return {
            "total": total_float,
            "count": count_int,
            "average": total_float / count_int if count_int else 0.0,
            "last_at": last_at,
            "pending": float(pending or 0),
        }


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


async def get_paypal_tag(tag_id: int | None) -> PaypalTag | None:
    if tag_id is None:
        return None
    async with SessionLocal() as session:
        return await session.get(PaypalTag, tag_id)


PAYMENT_FILTERS = {
    "check": ("waiting_check",),
    "payout": ("payout_pending",),
    "paidout": ("paid_out",),
    "notfound": ("not_found",),
    "gs": ("gs",),
    "waiting": ("paypal_issued",),
    "all": ("paypal_issued", "waiting_check", "payout_pending", "paid_out", "not_found", "gs"),
}


async def get_payment_counts() -> dict[str, int]:
    """Счётчики платёжных очередей.

    В активной категории «Выплаченные» показываются только выплаты за последние
    24 часа. Старые записи остаются в БД и продолжают участвовать в статистике.
    """
    counts = {"check": 0, "payout": 0, "paidout": 0, "notfound": 0, "waiting": 0, "all": 0}
    paid_cutoff = datetime.utcnow() - timedelta(hours=24)
    async with SessionLocal() as session:
        rows = await session.execute(
            select(Request.status, func.count(Request.id))
            .where(Request.status.in_(PAYMENT_FILTERS["all"]))
            .group_by(Request.status)
        )
        raw = {status: int(count) for status, count in rows.all()}
        recent_paid = int(await session.scalar(
            select(func.count(Request.id)).where(
                Request.status == "paid_out",
                Request.payout_at.is_not(None),
                Request.payout_at >= paid_cutoff,
            )
        ) or 0)
    counts["check"] = raw.get("waiting_check", 0)
    counts["payout"] = raw.get("payout_pending", 0)
    counts["paidout"] = recent_paid
    counts["notfound"] = raw.get("not_found", 0)
    counts["waiting"] = raw.get("paypal_issued", 0)
    # «Все» остаётся полной историей платёжных заявок, включая старые выплаты.
    counts["all"] = sum(raw.values())
    return counts


async def list_payment_requests(filter_name: str, offset: int = 0, limit: int = 10) -> tuple[list[Request], bool]:
    statuses = PAYMENT_FILTERS.get(filter_name, PAYMENT_FILTERS["all"])
    query = select(Request).where(Request.status.in_(statuses))
    if filter_name == "paidout":
        # Не удаляем выплату из БД: спустя 24 часа она лишь исчезает из активного списка.
        paid_cutoff = datetime.utcnow() - timedelta(hours=24)
        query = query.where(
            Request.payout_at.is_not(None),
            Request.payout_at >= paid_cutoff,
        )
    async with SessionLocal() as session:
        rows = list(await session.scalars(
            query
            .order_by(Request.updated_at.desc(), Request.id.desc())
            .offset(offset)
            .limit(limit + 1)
        ))
        return rows[:limit], len(rows) > limit


async def confirm_payment(request_id: int, admin_id: int) -> Request | None:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None or req.status != "waiting_check":
            return None
        percent = await _get_rate_percent(session, req.amount)
        if percent is None:
            return None
        req.status = "payout_pending"
        req.payout_percent = percent
        req.payout_amount = round(req.amount * percent / 100, 2)
        req.payment_confirmed_at = datetime.utcnow()
        req.payment_confirmed_by = admin_id
        req.updated_at = datetime.utcnow()
        existing_entry = await session.scalar(select(BalanceEntry).where(BalanceEntry.request_id == req.id))
        if existing_entry is None:
            session.add(BalanceEntry(
                user_id=req.user_id,
                request_id=req.id,
                amount=req.payout_amount,
                status="available",
            ))
        await session.commit()
        await session.refresh(req)
        return req


async def mark_payment_not_found(request_id: int, admin_id: int) -> Request | None:
    """Return a request to the user without removing the issued PayPal.

    The user can press "Я оплатил" again and resend the same request for
    another payment check.
    """
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None or req.status != "waiting_check":
            return None
        req.status = "paypal_issued"
        req.paid_clicked_at = None
        req.processed_at = datetime.utcnow()
        req.processed_by = admin_id
        req.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(req)
        return req


async def return_to_payment_check(request_id: int, admin_id: int) -> Request | None:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None or req.status != "not_found":
            return None
        req.status = "waiting_check"
        req.processed_at = datetime.utcnow()
        req.processed_by = admin_id
        req.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(req)
        return req


async def mark_payout_done(request_id: int, admin_id: int) -> Request | None:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None or req.status != "payout_pending":
            return None
        req.status = "paid_out"
        req.payout_at = datetime.utcnow()
        req.payout_by = admin_id
        req.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(req)
        return req


async def _get_rate_percent(session: AsyncSession, amount: int) -> int | None:
    return await session.scalar(
        select(RateRule.percent)
        .where(RateRule.min_amount <= amount)
        .order_by(RateRule.min_amount.desc())
        .limit(1)
    )


async def get_rate_for_amount(amount: int) -> tuple[int | None, float | None]:
    async with SessionLocal() as session:
        percent = await _get_rate_percent(session, amount)
        payout = round(amount * percent / 100, 2) if percent is not None else None
        return percent, payout


async def list_rate_rules() -> list[RateRule]:
    async with SessionLocal() as session:
        return list(await session.scalars(select(RateRule).order_by(RateRule.min_amount.asc())))


async def upsert_rate_rule(min_amount: int, percent: int) -> RateRule:
    async with SessionLocal() as session:
        rule = await session.scalar(select(RateRule).where(RateRule.min_amount == min_amount))
        if rule is None:
            rule = RateRule(min_amount=min_amount, percent=percent)
            session.add(rule)
        else:
            rule.percent = percent
        await session.commit()
        await session.refresh(rule)
        return rule


async def delete_rate_rule(rule_id: int) -> bool:
    async with SessionLocal() as session:
        rule = await session.get(RateRule, rule_id)
        if rule is None:
            return False
        count = int(await session.scalar(select(func.count()).select_from(RateRule)) or 0)
        if count <= 1:
            return False
        await session.delete(rule)
        await session.commit()
        return True


async def get_finance_summary() -> dict[str, float | int]:
    async with SessionLocal() as session:
        received = float(await session.scalar(
            select(func.coalesce(func.sum(Request.amount), 0)).where(Request.status.in_(("payout_pending", "paid_out")))
        ) or 0)
        payout = float(await session.scalar(
            select(func.coalesce(func.sum(Request.payout_amount), 0)).where(Request.status.in_(("payout_pending", "paid_out")))
        ) or 0)
        pending = float(await session.scalar(
            select(func.coalesce(func.sum(Request.payout_amount), 0)).where(Request.status == "payout_pending")
        ) or 0)
        paid = float(await session.scalar(
            select(func.coalesce(func.sum(Request.payout_amount), 0)).where(Request.status == "paid_out")
        ) or 0)
        return {"received": received, "payout": payout, "profit": received-payout, "pending": pending, "paid": paid}


async def create_paypal_return(request_id: int, user_id: int, reason_code: str, reason_text: str) -> PaypalReturn | None:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None or req.user_id != user_id or req.status != "paypal_issued" or req.paypal_tag_id is None:
            return None
        existing = await session.scalar(select(PaypalReturn).where(PaypalReturn.request_id == request_id))
        if existing:
            return existing
        item = PaypalReturn(request_id=request_id, user_id=user_id, paypal_tag_id=req.paypal_tag_id,
                            reason_code=reason_code, reason_text=reason_text, status="pending")
        session.add(item)
        req.status = "return_pending"
        req.updated_at = datetime.utcnow()
        tag = await session.get(PaypalTag, req.paypal_tag_id)
        if tag:
            tag.status = "return_pending"
        await session.commit()
        await session.refresh(item)
        return item


async def list_paypal_returns(status: str = "pending", limit: int = 50) -> list[PaypalReturn]:
    async with SessionLocal() as session:
        rows = await session.scalars(select(PaypalReturn).where(PaypalReturn.status == status).order_by(PaypalReturn.created_at.asc()).limit(limit))
        return list(rows)


async def get_paypal_return(return_id: int) -> PaypalReturn | None:
    async with SessionLocal() as session:
        return await session.get(PaypalReturn, return_id)


async def resolve_paypal_return(return_id: int, action: str, admin_id: int, admin_reason: str) -> PaypalReturn | None:
    async with SessionLocal() as session:
        item = await session.get(PaypalReturn, return_id, with_for_update=True)
        if item is None or item.status != "pending":
            return None
        req = await session.get(Request, item.request_id, with_for_update=True)
        tag = await session.get(PaypalTag, item.paypal_tag_id, with_for_update=True)
        if req is None or tag is None:
            return None
        now = datetime.utcnow()
        item.status = action
        item.admin_reason = admin_reason
        item.resolved_at = now
        item.resolved_by = admin_id
        if action == "returned":
            tag.status = "available"
            tag.issued_to_user_id = None
            tag.issued_at = None
            req.status = "returned"
        elif action == "gestoppt":
            tag.status = "gestoppt"
            tag.issued_to_user_id = None
            req.status = "returned_gestoppt"
        elif action == "deleted":
            tag.status = "deleted"
            tag.issued_to_user_id = None
            tag.issued_at = None
            req.status = "returned_deleted"
        req.updated_at = now
        await session.commit()
        await session.refresh(item)
        return item


async def get_paypal_database_counts() -> dict[str, int]:
    async with SessionLocal() as session:
        result = {key: int(await session.scalar(select(func.count()).select_from(PaypalTag).where(PaypalTag.status == key)) or 0)
                  for key in ("available", "issued", "return_pending", "gestoppt", "gs")}
        result["all"] = int(await session.scalar(
            select(func.count()).select_from(PaypalTag).where(PaypalTag.status != "deleted")
        ) or 0)
        return result


async def list_paypal_tags(filter_name: str = "all", limit: int = 50) -> list[PaypalTag]:
    async with SessionLocal() as session:
        query = select(PaypalTag).where(PaypalTag.status != "deleted").order_by(PaypalTag.id.desc())
        if filter_name != "all":
            query = query.where(PaypalTag.status == filter_name)
        return list(await session.scalars(query.limit(limit)))


async def delete_free_paypal_tag(tag_id: int) -> tuple[bool, str]:
    """Delete a PayPal tag only when it is currently free.

    Tags referenced by old requests are soft-deleted to preserve CRM history;
    unreferenced tags are removed physically.
    """
    async with SessionLocal() as session:
        tag = await session.get(PaypalTag, tag_id, with_for_update=True)
        if tag is None or tag.status == "deleted":
            return False, "not_found"
        if tag.status != "available":
            return False, "not_available"

        request_refs = int(await session.scalar(
            select(func.count()).select_from(Request).where(Request.paypal_tag_id == tag_id)
        ) or 0)
        return_refs = int(await session.scalar(
            select(func.count()).select_from(PaypalReturn).where(PaypalReturn.paypal_tag_id == tag_id)
        ) or 0)

        if request_refs or return_refs:
            tag.status = "deleted"
            tag.issued_to_user_id = None
            tag.issued_at = None
        else:
            await session.delete(tag)

        await session.commit()
        return True, "deleted"


async def set_paypal_tag_status(tag_id: int, status: str) -> PaypalTag | None:
    if status not in {"available", "gestoppt"}:
        raise ValueError("Unsupported PayPal status")
    async with SessionLocal() as session:
        tag = await session.get(PaypalTag, tag_id)
        if tag is None:
            return None
        tag.status = status
        if status in {"available", "gestoppt"}:
            tag.issued_to_user_id = None
            if status == "available":
                tag.issued_at = None
        await session.commit()
        await session.refresh(tag)
        return tag


async def get_working_dates() -> list[tuple[str, int]]:
    async with SessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT TO_CHAR(issued_at, 'YYYY-MM-DD') AS day, COUNT(*)
            FROM paypal_tags
            WHERE status = 'issued' AND issued_at IS NOT NULL
            GROUP BY day ORDER BY day DESC
        """))).all()
        return [(str(day), int(count)) for day, count in rows]


async def get_working_requests_by_date(day: str) -> list[Request]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(Request).join(PaypalTag, PaypalTag.id == Request.paypal_tag_id).where(
                PaypalTag.status == "issued", func.to_char(PaypalTag.issued_at, 'YYYY-MM-DD') == day,
                Request.status == "paypal_issued"
            ).order_by(PaypalTag.issued_at.asc())
        )
        return list(rows)


async def mark_collection_notified(request_id: int) -> Request | None:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id)
        if req is None or req.status != "paypal_issued":
            return None
        req.collection_notified_at = datetime.utcnow()
        req.keep_confirmed_at = None
        await session.commit(); await session.refresh(req); return req


async def user_return_paypal_after_warning(request_id: int, user_id: int) -> tuple[Request | None, PaypalTag | None]:
    """Immediately return an issued PayPal to the free pool after a 30-minute warning."""
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None or req.user_id != user_id or req.status != "paypal_issued" or req.paypal_tag_id is None:
            return None, None
        tag = await session.get(PaypalTag, req.paypal_tag_id, with_for_update=True)
        if tag is None or tag.status != "issued":
            return None, None
        now = datetime.utcnow()
        tag.status = "available"
        tag.issued_to_user_id = None
        tag.issued_at = None
        req.status = "user_returned_after_warning"
        req.processed_at = now
        req.processed_by = user_id
        req.updated_at = now
        await session.commit()
        await session.refresh(req)
        await session.refresh(tag)
        return req, tag


async def confirm_paypal_keep(request_id: int, user_id: int) -> Request | None:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id)
        if req is None or req.user_id != user_id or req.status != "paypal_issued":
            return None
        req.keep_confirmed_at = datetime.utcnow()
        await session.commit(); await session.refresh(req); return req


async def list_unconfirmed_collection(day: str) -> list[Request]:
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(Request).join(PaypalTag, PaypalTag.id == Request.paypal_tag_id).where(
                PaypalTag.status == "issued", func.to_char(PaypalTag.issued_at, 'YYYY-MM-DD') == day,
                Request.status == "paypal_issued", Request.collection_notified_at.is_not(None),
                Request.keep_confirmed_at.is_(None)
            )
        )
        return list(rows)

async def admin_recall_working_request(request_id: int, action: str, admin_id: int) -> tuple[Request | None, PaypalTag | None]:
    """Take an issued PayPal away from a user and either free, gestop or delete it."""
    if action not in {"available", "gestoppt", "deleted"}:
        raise ValueError("Unsupported recall action")
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None or req.status != "paypal_issued" or req.paypal_tag_id is None:
            return None, None
        tag = await session.get(PaypalTag, req.paypal_tag_id, with_for_update=True)
        if tag is None or tag.status != "issued":
            return None, None
        now = datetime.utcnow()
        tag.status = action
        tag.issued_to_user_id = None
        if action in {"available", "deleted"}:
            tag.issued_at = None
        req.status = {
            "available": "admin_recalled",
            "gestoppt": "admin_recalled_gestoppt",
            "deleted": "admin_recalled_deleted",
        }[action]
        req.processed_at = now
        req.processed_by = admin_id
        req.updated_at = now
        await session.commit()
        await session.refresh(req)
        await session.refresh(tag)
        return req, tag


async def bulk_delete_working_day(day: str, admin_id: int) -> list[tuple[int, str]]:
    """Soft-delete every still-issued PayPal for a selected issue date.

    Returns (user_id, paypal_tag) for notifications.
    """
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(Request, PaypalTag).join(PaypalTag, PaypalTag.id == Request.paypal_tag_id).where(
                PaypalTag.status == "issued",
                func.to_char(PaypalTag.issued_at, "YYYY-MM-DD") == day,
                Request.status == "paypal_issued",
            ).with_for_update()
        )).all()
        now = datetime.utcnow()
        result: list[tuple[int, str]] = []
        for req, tag in rows:
            result.append((req.user_id, tag.tag))
            tag.status = "deleted"
            tag.issued_to_user_id = None
            tag.issued_at = None
            req.status = "admin_recalled_deleted"
            req.processed_at = now
            req.processed_by = admin_id
            req.updated_at = now
        await session.commit()
        return result


async def search_working_requests(query: str, limit: int = 50) -> list[Request]:
    value = query.strip()
    if not value:
        return []
    pattern = f"%{value.lstrip('@')}%"
    async with SessionLocal() as session:
        stmt = (
            select(Request)
            .join(PaypalTag, PaypalTag.id == Request.paypal_tag_id)
            .join(User, User.id == Request.user_id)
            .where(PaypalTag.status == "issued", Request.status == "paypal_issued")
            .where(
                PaypalTag.tag.ilike(pattern)
                | User.username.ilike(pattern)
                | User.full_name.ilike(pattern)
                | func.cast(Request.user_id, String).ilike(pattern)
            )
            .order_by(PaypalTag.issued_at.desc())
            .limit(limit)
        )
        return list(await session.scalars(stmt))


async def get_app_setting(key: str, default: str = "") -> str:
    async with SessionLocal() as session:
        row = await session.get(AppSetting, key)
        return row.value if row else default


async def set_app_setting(key: str, value: str) -> None:
    async with SessionLocal() as session:
        row = await session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=value, updated_at=datetime.utcnow()))
        else:
            row.value = value
            row.updated_at = datetime.utcnow()
        await session.commit()


async def is_work_enabled() -> bool:
    return (await get_app_setting("work_enabled", "0")) == "1"


async def set_work_enabled(enabled: bool) -> None:
    await set_app_setting("work_enabled", "1" if enabled else "0")


async def list_approved_user_ids() -> list[int]:
    async with SessionLocal() as session:
        return list(await session.scalars(select(User.id).where(User.status == "approved")))


async def mark_payment_gs(request_id: int, admin_id: int, screenshot_file_id: str | None = None) -> Request | None:
    async with SessionLocal() as session:
        async with session.begin():
            req = await session.get(Request, request_id, with_for_update=True)
            if req is None or req.status != "waiting_check":
                return None
            req.status = "gs"
            req.processed_at = datetime.utcnow()
            req.processed_by = admin_id
            if req.paypal_tag_id:
                tag = await session.get(PaypalTag, req.paypal_tag_id, with_for_update=True)
                if tag:
                    tag.status = "gs"
                    tag.gs_screenshot_file_id = screenshot_file_id
            return req

# v1.7.0 CRM helpers
async def get_dashboard_summary() -> dict:
    async with SessionLocal() as session:
        async def scalar(stmt):
            return (await session.scalar(stmt)) or 0
        today = datetime.utcnow().date()
        return {
            "available": await scalar(select(func.count(PaypalTag.id)).where(PaypalTag.status == "available")),
            "working": await scalar(select(func.count(Request.id)).where(Request.status == "paypal_issued")),
            "waiting_check": await scalar(select(func.count(Request.id)).where(Request.status == "waiting_check")),
            "payout_pending": await scalar(select(func.count(Request.id)).where(Request.status == "payout_pending")),
            "paid_today": await scalar(select(func.count(Request.id)).where(Request.status == "paid_out", func.date(Request.payout_at) == today)),
            "gs": await scalar(select(func.count(PaypalTag.id)).where(PaypalTag.status == "gs")),
            "users": await scalar(select(func.count(User.id)).where(User.status == "approved")),
            "queue": await scalar(select(func.count(Request.id)).where(Request.status == "waiting_issue")),
        }

async def get_user_crm_stats(user_id: int) -> dict:
    async with SessionLocal() as session:
        rows = (await session.execute(select(Request.status, func.count(Request.id), func.coalesce(func.sum(Request.amount), 0)).where(Request.user_id == user_id).group_by(Request.status))).all()
        counts = {status: int(count) for status, count, _ in rows}
        total_amount = sum(float(amount or 0) for _, _, amount in rows)
        successful = counts.get("paid_out", 0) + counts.get("payout_pending", 0)
        returned = sum(counts.get(s, 0) for s in ("returned", "admin_recalled", "user_returned", "return_pending"))
        active = sum(counts.get(s, 0) for s in ("waiting_issue", "paypal_issued", "waiting_check", "payout_pending"))
        return {
            "received": sum(counts.get(s, 0) for s in ("paypal_issued", "waiting_check", "payout_pending", "paid_out", "gs", "not_found")),
            "successful": successful,
            "returned": returned,
            "gs": counts.get("gs", 0),
            "active": active,
            "total_amount": total_amount,
        }

async def global_admin_search(query: str, limit: int = 30) -> dict:
    value = query.strip().lstrip("@")
    if not value:
        return {"users": [], "requests": [], "tags": []}
    pattern = f"%{value}%"
    async with SessionLocal() as session:
        users = list(await session.scalars(select(User).where(
            User.username.ilike(pattern) | User.full_name.ilike(pattern) | func.cast(User.id, String).ilike(pattern)
        ).limit(limit)))
        requests = list(await session.scalars(select(Request).join(User, User.id == Request.user_id, isouter=True).where(
            func.cast(Request.id, String).ilike(pattern) |
            func.cast(Request.user_id, String).ilike(pattern) |
            func.cast(Request.amount, String).ilike(pattern) |
            User.username.ilike(pattern)
        ).order_by(Request.id.desc()).limit(limit)))
        tags = list(await session.scalars(select(PaypalTag).where(PaypalTag.tag.ilike(pattern)).order_by(PaypalTag.id.desc()).limit(limit)))
        return {"users": users, "requests": requests, "tags": tags}

async def get_period_statistics(period: str) -> dict:
    now = datetime.utcnow()
    start = None
    if period == "today": start = datetime.combine(now.date(), datetime.min.time())
    elif period == "yesterday":
        start = datetime.combine(now.date() - timedelta(days=1), datetime.min.time())
        end = datetime.combine(now.date(), datetime.min.time())
    elif period == "7d": start = now - timedelta(days=7)
    elif period == "30d": start = now - timedelta(days=30)
    async with SessionLocal() as session:
        conditions = []
        if start: conditions.append(Request.created_at >= start)
        if period == "yesterday": conditions.append(Request.created_at < end)
        stmt = select(Request).where(*conditions)
        requests = list(await session.scalars(stmt))
        return {
            "requests": len(requests),
            "issued": sum(r.paypal_tag_id is not None for r in requests),
            "successful": sum(r.status in {"payout_pending", "paid_out"} for r in requests),
            "returns": sum(r.status in {"returned", "admin_recalled", "user_returned", "return_pending"} for r in requests),
            "gs": sum(r.status == "gs" for r in requests),
            "turnover": sum(float(r.amount or 0) for r in requests if r.status in {"payout_pending", "paid_out"}),
            "payout": sum(float(r.payout_amount or 0) for r in requests if r.status in {"payout_pending", "paid_out"}),
            "active_users": len({r.user_id for r in requests}),
        }


# ==================== v2.2: БАЛАНС И РУЧНЫЕ ВЫПЛАТЫ ====================

async def get_user_payout_method(user_id: int) -> str:
    async with SessionLocal() as session:
        value = await session.scalar(select(User.payout_method).where(User.id == user_id))
        return value or "cryptobot"


async def set_user_payout_method(user_id: int, method: str) -> bool:
    if method not in {"cryptobot", "xrocket"}:
        return False
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            return False
        user.payout_method = method
        await session.commit()
        return True


async def get_user_balance(user_id: int) -> dict:
    async with SessionLocal() as session:
        available = float(await session.scalar(
            select(func.coalesce(func.sum(BalanceEntry.amount), 0)).where(
                BalanceEntry.user_id == user_id, BalanceEntry.status == "available"
            )
        ) or 0)
        paid = float(await session.scalar(
            select(func.coalesce(func.sum(BalanceEntry.amount), 0)).where(
                BalanceEntry.user_id == user_id, BalanceEntry.status == "paid"
            )
        ) or 0)
        count_available = int(await session.scalar(
            select(func.count(BalanceEntry.id)).where(
                BalanceEntry.user_id == user_id, BalanceEntry.status == "available"
            )
        ) or 0)
        count_paid = int(await session.scalar(
            select(func.count(ManualPayout.id)).where(ManualPayout.user_id == user_id)
        ) or 0)
        last = await session.scalar(
            select(ManualPayout).where(ManualPayout.user_id == user_id).order_by(ManualPayout.id.desc()).limit(1)
        )
        method = await session.scalar(select(User.payout_method).where(User.id == user_id)) or "cryptobot"
        return {
            "available": available, "paid": paid, "count_available": count_available,
            "count_paid": count_paid, "last": last, "method": method,
        }


async def list_users_with_available_balance(offset: int = 0, limit: int = 10):
    async with SessionLocal() as session:
        query = (
            select(User, func.sum(BalanceEntry.amount).label("balance"), func.count(BalanceEntry.id).label("entries"))
            .join(BalanceEntry, BalanceEntry.user_id == User.id)
            .where(BalanceEntry.status == "available")
            .group_by(User.id)
            .order_by(func.sum(BalanceEntry.amount).desc(), User.id)
            .offset(offset).limit(limit + 1)
        )
        rows = list((await session.execute(query)).all())
        return rows[:limit], len(rows) > limit


async def get_payout_user_details(user_id: int) -> dict | None:
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            return None
        entries = list(await session.scalars(
            select(BalanceEntry).where(
                BalanceEntry.user_id == user_id, BalanceEntry.status == "available"
            ).order_by(BalanceEntry.id)
        ))
        return {
            "user": user,
            "entries": entries,
            "total": round(sum(float(e.amount) for e in entries), 2),
            "method": user.payout_method or "cryptobot",
        }


async def complete_manual_payout(user_id: int, admin_id: int, source_message_id: int | None = None) -> ManualPayout | None:
    async with SessionLocal() as session:
        async with session.begin():
            user = await session.get(User, user_id, with_for_update=True)
            if user is None:
                return None
            entries = list(await session.scalars(
                select(BalanceEntry).where(
                    BalanceEntry.user_id == user_id, BalanceEntry.status == "available"
                ).order_by(BalanceEntry.id).with_for_update()
            ))
            if not entries:
                return None
            total = round(sum(float(e.amount) for e in entries), 2)
            payout = ManualPayout(
                user_id=user_id, total_amount=total, provider=user.payout_method or "cryptobot",
                admin_id=admin_id, source_message_id=source_message_id,
            )
            session.add(payout)
            await session.flush()
            now = datetime.utcnow()
            request_ids = []
            for entry in entries:
                entry.status = "paid"
                entry.payout_id = payout.id
                entry.paid_at = now
                request_ids.append(entry.request_id)
            requests = list(await session.scalars(select(Request).where(Request.id.in_(request_ids)).with_for_update()))
            for req in requests:
                req.status = "paid_out"
                req.payout_at = now
                req.payout_by = admin_id
                req.updated_at = now
        await session.refresh(payout)
        return payout


async def list_manual_payouts(user_id: int, limit: int = 10) -> list[ManualPayout]:
    async with SessionLocal() as session:
        return list(await session.scalars(
            select(ManualPayout).where(ManualPayout.user_id == user_id).order_by(ManualPayout.id.desc()).limit(limit)
        ))


async def get_payout_dashboard_counts() -> dict:
    async with SessionLocal() as session:
        users_count = int(await session.scalar(
            select(func.count(func.distinct(BalanceEntry.user_id))).where(BalanceEntry.status == "available")
        ) or 0)
        total = float(await session.scalar(
            select(func.coalesce(func.sum(BalanceEntry.amount), 0)).where(BalanceEntry.status == "available")
        ) or 0)
        paid_total = float(await session.scalar(select(func.coalesce(func.sum(ManualPayout.total_amount), 0))) or 0)
        paid_count = int(await session.scalar(select(func.count(ManualPayout.id))) or 0)
        return {"users": users_count, "total": total, "paid_total": paid_total, "paid_count": paid_count}
