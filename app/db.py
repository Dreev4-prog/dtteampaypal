from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, select, text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


MOSCOW_TZ = ZoneInfo("Europe/Moscow")
UTC_TZ = ZoneInfo("UTC")


def _moscow_day_utc_bounds(day: date) -> tuple[datetime, datetime]:
    start_msk = datetime.combine(
        day,
        datetime.min.time(),
        tzinfo=MOSCOW_TZ,
    )
    end_msk = start_msk + timedelta(days=1)
    return (
        start_msk.astimezone(UTC_TZ).replace(tzinfo=None),
        end_msk.astimezone(UTC_TZ).replace(tzinfo=None),
    )


def _moscow_today() -> date:
    return datetime.now(UTC_TZ).astimezone(MOSCOW_TZ).date()


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
    paypal_withdrawn_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    paypal_withdrawn_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    happy_hours_campaign_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    happy_hours_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    happy_hours_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    happy_hours_applied: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    collection_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    keep_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    working_bucket_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


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


class HappyHoursCampaign(Base):
    __tablename__ = "happy_hours_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    min_amount: Mapped[int] = mapped_column(Integer)
    percent: Mapped[int] = mapped_column(Integer)
    broadcast_text: Mapped[str] = mapped_column(String(4096))
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_enabled: Mapped[int] = mapped_column(Integer, default=1, index=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    activated_by: Mapped[int] = mapped_column(BigInteger)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
        # v2.2.24: внутренний статус вывода денег с конкретного PayPal.
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS paypal_withdrawn_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS paypal_withdrawn_by BIGINT"))
        # v2.3.0: Happy Hours snapshot fields on requests.
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS happy_hours_campaign_id INTEGER"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS happy_hours_percent INTEGER"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS happy_hours_locked_at TIMESTAMP"))
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS happy_hours_applied INTEGER DEFAULT 0"))
        await conn.execute(text("UPDATE requests SET happy_hours_applied = 0 WHERE happy_hours_applied IS NULL"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_requests_happy_hours_campaign_id ON requests (happy_hours_campaign_id)"))
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
        # v2.3.1: отдельная дата группировки PayPal в разделе «В работе».
        # Реальное время выдачи processed_at не переписывается.
        await conn.execute(text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS working_bucket_at TIMESTAMP"))
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
        # v2.3.0: Happy Hours draft configuration. Times are entered/displayed as Europe/Moscow.
        await conn.execute(text("""
            INSERT INTO app_settings (key, value, updated_at) VALUES
            ('happy_hours_start_time', '13:00', CURRENT_TIMESTAMP),
            ('happy_hours_end_time', '17:00', CURRENT_TIMESTAMP),
            ('happy_hours_min_amount', '100', CURRENT_TIMESTAMP),
            ('happy_hours_percent', '80', CURRENT_TIMESTAMP),
            ('happy_hours_text', '🔥 <b>СЧАСТЛИВЫЕ ЧАСЫ DT TEAM</b>\n\nТолько с {start} до {end} МСК!\n\n💶 От {min_amount} €\n🚀 Выплата — {percent}%\n\nПолучите PayPal во время акции и отправьте оплату на проверку до {end} МСК, чтобы повышенный процент зафиксировался.', CURRENT_TIMESTAMP),
            ('happy_hours_photo', '', CURRENT_TIMESTAMP)
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

            now = datetime.utcnow()
            tag.status = "issued"
            tag.issued_to_user_id = req.user_id
            tag.issued_at = now

            req.paypal_tag_id = tag.id
            req.status = "paypal_issued"
            req.processed_at = now
            req.updated_at = now
            req.working_bucket_at = now

            # Happy Hours applies only to PayPal actually issued while the
            # manually launched campaign is active. Older PayPal never become
            # promo-eligible retroactively.
            campaign = await session.scalar(
                select(HappyHoursCampaign)
                .where(
                    HappyHoursCampaign.is_enabled == 1,
                    HappyHoursCampaign.start_at <= now,
                    HappyHoursCampaign.end_at > now,
                )
                .order_by(HappyHoursCampaign.id.desc())
                .limit(1)
            )
            req.happy_hours_campaign_id = campaign.id if campaign else None
            req.happy_hours_percent = None
            req.happy_hours_locked_at = None
            req.happy_hours_applied = 0

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
            percent, is_happy = await _get_effective_request_rate(session, req)
            req.payout_percent = percent
            req.payout_amount = round(amount * percent / 100, 2) if percent is not None else None
            req.happy_hours_applied = 1 if is_happy else 0
        req.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(req)
        return req


async def mark_paid_by_user(request_id: int, user_id: int) -> bool:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None or req.user_id != user_id or req.status != "paypal_issued":
            return False

        now = datetime.utcnow()
        req.status = "waiting_check"
        req.paid_clicked_at = now
        req.updated_at = now

        # A previously locked Happy Hours rate survives a later re-check.
        # Otherwise lock it only when ALL conditions are true:
        # PayPal was issued during this campaign, amount meets the threshold,
        # and the user sends the payment to check before the campaign ends.
        if req.happy_hours_percent is None and req.happy_hours_campaign_id is not None:
            campaign = await session.get(
                HappyHoursCampaign,
                req.happy_hours_campaign_id,
            )
            if (
                campaign is not None
                and campaign.is_enabled == 1
                # campaign_id is assigned only by issue_paypal while the
                # campaign is active, so it is the authoritative proof that
                # this PayPal was taken during Happy Hours.
                and campaign.start_at <= now < campaign.end_at
                and req.amount >= campaign.min_amount
            ):
                req.happy_hours_percent = campaign.percent
                req.happy_hours_locked_at = now

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


async def search_users_by_tag(query_text: str, limit: int = 20) -> list[User]:
    """Search users by Telegram username, prioritising an exact match."""
    value = query_text.strip().lstrip("@").strip()
    if not value:
        return []

    async with SessionLocal() as session:
        rows = await session.scalars(
            select(User)
            .where(User.username.is_not(None), User.username.ilike(f"%{value}%"))
            .order_by(
                # Exact username first, then prefix matches, then newest users.
                (func.lower(User.username) == value.lower()).desc(),
                User.username.ilike(f"{value}%").desc(),
                User.created_at.desc(),
                User.id.desc(),
            )
            .limit(limit)
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
        if filter_name == "payout":
            query = query.order_by(
                Request.paypal_withdrawn_at.is_not(None).asc(),
                Request.updated_at.desc(),
                Request.id.desc(),
            )
        else:
            query = query.order_by(Request.updated_at.desc(), Request.id.desc())

        rows = list(await session.scalars(
            query
            .offset(offset)
            .limit(limit + 1)
        ))
        return rows[:limit], len(rows) > limit


async def get_paypal_withdrawal_counts() -> dict[str, int]:
    """Counts for the admin-only «Вывести деньги» control list."""
    async with SessionLocal() as session:
        not_withdrawn = int(
            await session.scalar(
                select(func.count(Request.id)).where(
                    Request.status == "payout_pending",
                    Request.paypal_withdrawn_at.is_(None),
                )
            )
            or 0
        )
        withdrawn = int(
            await session.scalar(
                select(func.count(Request.id)).where(
                    Request.status == "payout_pending",
                    Request.paypal_withdrawn_at.is_not(None),
                )
            )
            or 0
        )
        return {
            "not_withdrawn": not_withdrawn,
            "withdrawn": withdrawn,
            "total": not_withdrawn + withdrawn,
        }


async def mark_paypal_withdrawn(
    request_id: int,
    admin_id: int,
) -> tuple[Request | None, str]:
    """Mark money as withdrawn from this PayPal without completing user payout."""
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None:
            return None, "not_found"
        if req.status != "payout_pending":
            return req, "not_pending"
        if req.paypal_withdrawn_at is not None:
            return req, "already_done"

        req.paypal_withdrawn_at = datetime.utcnow()
        req.paypal_withdrawn_by = admin_id
        req.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(req)
        return req, "done"


async def confirm_payment(request_id: int, admin_id: int) -> Request | None:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None or req.status != "waiting_check":
            return None
        percent, is_happy = await _get_effective_request_rate(session, req)
        if percent is None:
            return None
        req.status = "payout_pending"
        req.payout_percent = percent
        req.payout_amount = round(req.amount * percent / 100, 2)
        req.happy_hours_applied = 1 if is_happy else 0
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


async def confirm_working_payment(request_id: int, admin_id: int) -> Request | None:
    """Confirm money directly from the admin card of an issued PayPal.

    The configured rate is applied automatically and one balance entry is
    created for the request. Repeated callback presses cannot duplicate it.
    """
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if req is None or req.status != "paypal_issued":
            return None
        percent = await _get_rate_percent(session, req.amount)
        if percent is None:
            return None
        now = datetime.utcnow()
        req.status = "payout_pending"
        req.payout_percent = percent
        req.payout_amount = round(req.amount * percent / 100, 2)
        req.happy_hours_applied = 0
        req.payment_confirmed_at = now
        req.payment_confirmed_by = admin_id
        req.updated_at = now
        existing_entry = await session.scalar(
            select(BalanceEntry).where(BalanceEntry.request_id == req.id)
        )
        if existing_entry is None:
            session.add(BalanceEntry(
                user_id=req.user_id,
                request_id=req.id,
                amount=req.payout_amount,
                status="available",
            ))
        if req.paypal_tag_id is not None:
            tag = await session.get(
                PaypalTag,
                req.paypal_tag_id,
                with_for_update=True,
            )
            if tag is not None:
                remaining_req = await session.scalar(
                    select(Request)
                    .where(
                        Request.paypal_tag_id == req.paypal_tag_id,
                        Request.status == "paypal_issued",
                        Request.id != req.id,
                    )
                    .order_by(Request.id.desc())
                    .limit(1)
                )
                if remaining_req is None:
                    tag.status = "used"
                    tag.issued_to_user_id = None
                else:
                    tag.status = "issued"
                    tag.issued_to_user_id = remaining_req.user_id
                    tag.issued_at = (
                        remaining_req.processed_at
                        or remaining_req.updated_at
                        or remaining_req.created_at
                    )
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


async def _get_effective_request_rate(
    session: AsyncSession,
    req: Request,
) -> tuple[int | None, bool]:
    """Return rate for a request, respecting a Happy Hours snapshot."""
    if req.happy_hours_percent is not None and req.happy_hours_campaign_id is not None:
        campaign = await session.get(HappyHoursCampaign, req.happy_hours_campaign_id)
        if campaign is not None and req.amount >= campaign.min_amount:
            return int(req.happy_hours_percent), True

    return await _get_rate_percent(session, req.amount), False


async def get_effective_rate_for_request(
    request_id: int,
) -> tuple[int | None, float | None, bool]:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id)
        if req is None:
            return None, None, False
        percent, is_happy = await _get_effective_request_rate(session, req)
        payout = round(req.amount * percent / 100, 2) if percent is not None else None
        return percent, payout, is_happy


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


async def get_happy_hours_campaign(
    campaign_id: int | None,
) -> HappyHoursCampaign | None:
    if campaign_id is None:
        return None
    async with SessionLocal() as session:
        return await session.get(HappyHoursCampaign, campaign_id)


async def get_open_happy_hours_campaign(
    now: datetime | None = None,
) -> HappyHoursCampaign | None:
    now = now or datetime.utcnow()
    async with SessionLocal() as session:
        return await session.scalar(
            select(HappyHoursCampaign)
            .where(
                HappyHoursCampaign.is_enabled == 1,
                HappyHoursCampaign.end_at > now,
            )
            .order_by(HappyHoursCampaign.id.desc())
            .limit(1)
        )


async def get_current_happy_hours_campaign(
    now: datetime | None = None,
) -> HappyHoursCampaign | None:
    now = now or datetime.utcnow()
    async with SessionLocal() as session:
        return await session.scalar(
            select(HappyHoursCampaign)
            .where(
                HappyHoursCampaign.is_enabled == 1,
                HappyHoursCampaign.start_at <= now,
                HappyHoursCampaign.end_at > now,
            )
            .order_by(HappyHoursCampaign.id.desc())
            .limit(1)
        )


async def create_happy_hours_campaign(
    start_at: datetime,
    end_at: datetime,
    min_amount: int,
    percent: int,
    broadcast_text: str,
    photo_file_id: str | None,
    admin_id: int,
) -> tuple[HappyHoursCampaign | None, str]:
    now = datetime.utcnow()
    async with SessionLocal() as session:
        async with session.begin():
            # Expired campaigns never block a new manual launch.
            stale = list(await session.scalars(
                select(HappyHoursCampaign).where(
                    HappyHoursCampaign.is_enabled == 1,
                    HappyHoursCampaign.end_at <= now,
                )
            ))
            for item in stale:
                item.is_enabled = 0
                item.ended_at = item.ended_at or item.end_at

            existing = await session.scalar(
                select(HappyHoursCampaign)
                .where(
                    HappyHoursCampaign.is_enabled == 1,
                    HappyHoursCampaign.end_at > now,
                )
                .order_by(HappyHoursCampaign.id.desc())
                .limit(1)
                .with_for_update()
            )
            if existing is not None:
                return None, "already_open"

            campaign = HappyHoursCampaign(
                start_at=start_at,
                end_at=end_at,
                min_amount=min_amount,
                percent=percent,
                broadcast_text=broadcast_text,
                photo_file_id=photo_file_id or None,
                is_enabled=1,
                activated_at=now,
                activated_by=admin_id,
            )
            session.add(campaign)

        await session.refresh(campaign)
        return campaign, "created"


async def stop_happy_hours_campaign(
    admin_id: int,
) -> HappyHoursCampaign | None:
    now = datetime.utcnow()
    async with SessionLocal() as session:
        campaign = await session.scalar(
            select(HappyHoursCampaign)
            .where(
                HappyHoursCampaign.is_enabled == 1,
                HappyHoursCampaign.end_at > now,
            )
            .order_by(HappyHoursCampaign.id.desc())
            .limit(1)
            .with_for_update()
        )
        if campaign is None:
            return None
        campaign.is_enabled = 0
        campaign.ended_at = now
        campaign.ended_by = admin_id
        await session.commit()
        await session.refresh(campaign)
        return campaign


async def list_happy_hours_campaigns(limit: int = 10) -> list[HappyHoursCampaign]:
    async with SessionLocal() as session:
        return list(await session.scalars(
            select(HappyHoursCampaign)
            .order_by(HappyHoursCampaign.id.desc())
            .limit(limit)
        ))


async def get_happy_hours_stats(campaign_id: int) -> dict[str, float | int]:
    async with SessionLocal() as session:
        issued = int(await session.scalar(
            select(func.count(Request.id)).where(
                Request.happy_hours_campaign_id == campaign_id
            )
        ) or 0)
        locked = int(await session.scalar(
            select(func.count(Request.id)).where(
                Request.happy_hours_campaign_id == campaign_id,
                Request.happy_hours_percent.is_not(None),
            )
        ) or 0)
        applied = int(await session.scalar(
            select(func.count(Request.id)).where(
                Request.happy_hours_campaign_id == campaign_id,
                Request.happy_hours_applied == 1,
            )
        ) or 0)
        turnover = float(await session.scalar(
            select(func.coalesce(func.sum(Request.amount), 0)).where(
                Request.happy_hours_campaign_id == campaign_id,
                Request.happy_hours_applied == 1,
            )
        ) or 0)
        return {
            "issued": issued,
            "locked": locked,
            "applied": applied,
            "turnover": turnover,
        }


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
        rows = (await session.execute(
            select(PaypalReturn, Request.amount, User.username, User.full_name, PaypalTag.tag)
            .join(Request, Request.id == PaypalReturn.request_id)
            .join(User, User.id == PaypalReturn.user_id)
            .join(PaypalTag, PaypalTag.id == PaypalReturn.paypal_tag_id)
            .where(PaypalReturn.status == status)
            .order_by(PaypalReturn.created_at.asc())
            .limit(limit)
        )).all()
        result: list[PaypalReturn] = []
        for item, amount, username, full_name, paypal_tag in rows:
            item._display_amount = amount
            item._display_username = f"@{username}" if username else (full_name or str(item.user_id))
            item._display_tag = paypal_tag
            result.append(item)
        return result


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
        result = {
            key: int(
                await session.scalar(
                    select(func.count())
                    .select_from(PaypalTag)
                    .where(PaypalTag.status == key)
                )
                or 0
            )
            for key in (
                "available",
                "return_pending",
                "gestoppt",
                "gs",
                "deleted",
            )
        }

        # «PayPal в работе» должен совпадать с реальным списком заявок.
        # Один статус issued у тега недостаточен: у него должна быть
        # активная связанная заявка paypal_issued.
        result["issued"] = int(
            await session.scalar(
                select(func.count(func.distinct(Request.id)))
                .select_from(Request)
                .join(PaypalTag, PaypalTag.id == Request.paypal_tag_id)
                .where(
                    Request.status == "paypal_issued",
                    Request.paypal_tag_id.is_not(None),
                )
            )
            or 0
        )

        result["all"] = int(
            await session.scalar(
                select(func.count())
                .select_from(PaypalTag)
                .where(PaypalTag.status != "deleted")
            )
            or 0
        )
        return result


async def get_paypal_gender_counts(status: str = "available") -> dict[str, int]:
    """Return exact PayPal counts by gender for the selected status."""
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(PaypalTag.gender, func.count(PaypalTag.id))
                .where(PaypalTag.status == status)
                .group_by(PaypalTag.gender)
            )
        ).all()

        counts = {
            "male": 0,
            "female": 0,
            "other": 0,
            "total": 0,
        }
        for gender, count in rows:
            value = int(count or 0)
            normalized = (gender or "").lower()
            if normalized == "male":
                counts["male"] += value
            elif normalized == "female":
                counts["female"] += value
            else:
                counts["other"] += value
            counts["total"] += value

        return counts


async def list_paypal_tags(filter_name: str = "all", limit: int = 50) -> list[PaypalTag]:
    async with SessionLocal() as session:
        query = select(PaypalTag).order_by(PaypalTag.id.desc())
        if filter_name == "deleted":
            query = query.where(PaypalTag.status == "deleted")
        elif filter_name == "all":
            query = query.where(PaypalTag.status != "deleted")
        else:
            query = query.where(
                PaypalTag.status == filter_name,
                PaypalTag.status != "deleted",
            )
        return list(await session.scalars(query.limit(limit)))


async def delete_free_paypal_tag(tag_id: int) -> tuple[bool, str]:
    """Move a free PayPal tag to the trash without deleting its database row."""
    async with SessionLocal() as session:
        tag = await session.get(PaypalTag, tag_id, with_for_update=True)
        if tag is None or tag.status == "deleted":
            return False, "not_found"
        if tag.status != "available":
            return False, "not_available"

        tag.status = "deleted"
        tag.issued_to_user_id = None
        tag.issued_at = None

        await session.commit()
        return True, "deleted"


async def get_deleted_working_request(tag_id: int) -> Request | None:
    """Return the latest user request linked to a deleted working PayPal.

    Supports both direct deletion from «PayPal в работе» and deletion after
    the PayPal was sent to the returns section for an administrator check.
    """
    async with SessionLocal() as session:
        return await session.scalar(
            select(Request)
            .where(
                Request.paypal_tag_id == tag_id,
                Request.status.in_(
                    (
                        "admin_recalled_deleted",
                        "returned_deleted",
                    )
                ),
            )
            .order_by(Request.updated_at.desc(), Request.id.desc())
            .limit(1)
        )


async def restore_deleted_paypal_to_work(
    tag_id: int,
    admin_id: int,
    source_request_id: int | None = None,
) -> tuple[Request | None, PaypalTag | None, str]:
    """Restore a deleted PayPal to the same user.

    Directly recalled PayPal restores the original request. A PayPal deleted
    after the returns workflow gets a fresh active request so that the old
    return history remains intact and future returns still work correctly.
    """
    async with SessionLocal() as session:
        tag = await session.get(PaypalTag, tag_id, with_for_update=True)
        if tag is None:
            return None, None, "not_found"
        if tag.status != "deleted":
            return None, None, "not_deleted"

        source_query = select(Request).where(
            Request.paypal_tag_id == tag_id,
            Request.status.in_(
                (
                    "admin_recalled_deleted",
                    "returned_deleted",
                )
            ),
        )
        if source_request_id is not None:
            source_query = source_query.where(Request.id == source_request_id)
        source_req = await session.scalar(
            source_query
            .order_by(Request.updated_at.desc(), Request.id.desc())
            .limit(1)
            .with_for_update()
        )
        if source_req is None:
            return None, tag, "no_working_request"

        now = datetime.utcnow()

        if source_req.status == "returned_deleted":
            # The old request already has a resolved PaypalReturn record with
            # a unique request_id. Preserve that history and create a clean
            # request for the restored work.
            req = Request(
                user_id=source_req.user_id,
                amount=source_req.amount,
                status="paypal_issued",
                paypal_tag_id=tag.id,
                screenshot_file_id=source_req.screenshot_file_id,
                paypal_gender=source_req.paypal_gender,
                created_at=now,
                updated_at=now,
            )
            session.add(req)
            await session.flush()
        else:
            req = source_req
            req.status = "paypal_issued"
            req.processed_at = None
            req.processed_by = None
            req.collection_notified_at = None
            req.keep_confirmed_at = None
            req.updated_at = now

        tag.status = "issued"
        tag.issued_to_user_id = req.user_id
        tag.issued_at = now

        await session.commit()
        await session.refresh(req)
        await session.refresh(tag)
        return req, tag, "restored_to_work"


async def restore_deleted_paypal_tag(tag_id: int) -> tuple[PaypalTag | None, str]:
    """Restore a PayPal tag from the trash to the free active pool."""
    async with SessionLocal() as session:
        tag = await session.get(PaypalTag, tag_id, with_for_update=True)
        if tag is None:
            return None, "not_found"
        if tag.status != "deleted":
            return None, "not_deleted"

        tag.status = "available"
        tag.issued_to_user_id = None
        tag.issued_at = None

        await session.commit()
        await session.refresh(tag)
        return tag, "restored"


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
        issued_expr = func.coalesce(
            Request.working_bucket_at,
            Request.processed_at,
            Request.updated_at,
            Request.created_at,
        )
        day_expr = func.to_char(
            issued_expr + text("INTERVAL '3 hours'"),
            "YYYY-MM-DD",
        )
        rows = (
            await session.execute(
                select(
                    day_expr.label("day"),
                    func.count(Request.id),
                )
                .select_from(Request)
                .where(
                    Request.status == "paypal_issued",
                    Request.paypal_tag_id.is_not(None),
                )
                .group_by(day_expr)
                .order_by(day_expr.desc())
            )
        ).all()
        return [(str(day), int(count)) for day, count in rows]


async def get_working_requests_by_date(day: str) -> list[Request]:
    async with SessionLocal() as session:
        issued_expr = func.coalesce(
            Request.working_bucket_at,
            Request.processed_at,
            Request.updated_at,
            Request.created_at,
        )
        rows = (
            await session.execute(
                select(Request, User.username, User.full_name, PaypalTag.tag)
                .join(PaypalTag, PaypalTag.id == Request.paypal_tag_id)
                .join(User, User.id == Request.user_id)
                .where(
                    func.to_char(
                        issued_expr + text("INTERVAL '3 hours'"),
                        "YYYY-MM-DD",
                    ) == day,
                    Request.status == "paypal_issued",
                )
                .order_by(issued_expr.asc(), Request.id.asc())
            )
        ).all()

        result: list[Request] = []
        for req, username, full_name, paypal_tag in rows:
            duplicate_count = int(
                await session.scalar(
                    select(func.count(Request.id)).where(
                        Request.paypal_tag_id == req.paypal_tag_id,
                        Request.status == "paypal_issued",
                    )
                )
                or 0
            )
            req._display_username = (
                f"@{username}" if username else (full_name or str(req.user_id))
            )
            req._display_tag = paypal_tag
            req._display_duplicate_count = duplicate_count
            req._display_issued_at = (
                req.processed_at or req.updated_at or req.created_at
            )
            result.append(req)
        return result


async def get_active_requests_for_tag(tag_id: int) -> list[Request]:
    """Return every active request linked to the same PayPal tag."""
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Request, User.username, User.full_name)
                .join(User, User.id == Request.user_id)
                .where(
                    Request.paypal_tag_id == tag_id,
                    Request.status == "paypal_issued",
                )
                .order_by(
                    func.coalesce(
                        Request.processed_at,
                        Request.updated_at,
                        Request.created_at,
                    ).asc(),
                    Request.id.asc(),
                )
            )
        ).all()

        result: list[Request] = []
        for req, username, full_name in rows:
            req._display_username = (
                f"@{username}" if username else (full_name or str(req.user_id))
            )
            result.append(req)
        return result


async def list_deleted_working_requests(tag_id: int) -> list[Request]:
    """Return all previous users linked to a PayPal currently in the trash."""
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Request, User.username, User.full_name)
                .join(User, User.id == Request.user_id)
                .where(
                    Request.paypal_tag_id == tag_id,
                    Request.status.in_(
                        (
                            "admin_recalled_deleted",
                            "returned_deleted",
                        )
                    ),
                )
                .order_by(Request.updated_at.desc(), Request.id.desc())
            )
        ).all()

        result: list[Request] = []
        for req, username, full_name in rows:
            req._display_username = (
                f"@{username}" if username else (full_name or str(req.user_id))
            )
            result.append(req)
        return result


async def cancel_duplicate_working_request(
    request_id: int,
    admin_id: int,
) -> tuple[Request | None, PaypalTag | None, int, str]:
    """Cancel one mistaken duplicate assignment without touching the others."""
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if (
            req is None
            or req.status != "paypal_issued"
            or req.paypal_tag_id is None
        ):
            return None, None, 0, "not_active"

        active_requests = list(
            await session.scalars(
                select(Request)
                .where(
                    Request.paypal_tag_id == req.paypal_tag_id,
                    Request.status == "paypal_issued",
                )
                .order_by(Request.id.asc())
                .with_for_update()
            )
        )
        if len(active_requests) <= 1:
            return None, None, len(active_requests), "not_duplicate"

        tag = await session.get(PaypalTag, req.paypal_tag_id, with_for_update=True)
        if tag is None:
            return None, None, 0, "tag_not_found"

        now = datetime.utcnow()
        req.status = "duplicate_cancelled"
        req.processed_at = now
        req.processed_by = admin_id
        req.updated_at = now

        remaining = [item for item in active_requests if item.id != req.id]
        current = remaining[-1]
        tag.status = "issued"
        tag.issued_to_user_id = current.user_id
        tag.issued_at = (
            current.processed_at
            or current.updated_at
            or current.created_at
            or now
        )

        await session.commit()
        await session.refresh(req)
        await session.refresh(tag)
        return req, tag, len(remaining), "cancelled"


async def mark_collection_notified(request_id: int) -> Request | None:
    async with SessionLocal() as session:
        req = await session.get(Request, request_id)
        if req is None or req.status != "paypal_issued":
            return None
        req.collection_notified_at = datetime.utcnow()
        req.keep_confirmed_at = None
        await session.commit(); await session.refresh(req); return req


async def user_return_paypal_after_warning(
    request_id: int,
    user_id: int,
) -> tuple[Request | None, PaypalTag | None, PaypalReturn | None]:
    """Move the PayPal to the existing returns queue after the 30-minute warning."""
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if (
            req is None
            or req.user_id != user_id
            or req.status != "paypal_issued"
            or req.paypal_tag_id is None
        ):
            return None, None, None

        tag = await session.get(PaypalTag, req.paypal_tag_id, with_for_update=True)
        if tag is None or tag.status != "issued":
            return None, None, None

        existing = await session.scalar(
            select(PaypalReturn).where(PaypalReturn.request_id == request_id)
        )
        if existing is not None:
            return req, tag, existing

        return_item = PaypalReturn(
            request_id=request_id,
            user_id=user_id,
            paypal_tag_id=req.paypal_tag_id,
            reason_code="warning_return",
            reason_text="Пользователь вернул PayPal после уведомления о сборе через 30 минут.",
            status="pending",
        )
        session.add(return_item)

        req.status = "return_pending"
        req.updated_at = datetime.utcnow()
        tag.status = "return_pending"

        await session.commit()
        await session.refresh(req)
        await session.refresh(tag)
        await session.refresh(return_item)
        return req, tag, return_item


async def confirm_paypal_keep(request_id: int, user_id: int) -> Request | None:
    """Keep PayPal with the user and move it into the current working day.

    processed_at remains the real issue timestamp. working_bucket_at controls
    only the date grouping inside «PayPal в работе».
    """
    async with SessionLocal() as session:
        req = await session.get(Request, request_id, with_for_update=True)
        if (
            req is None
            or req.user_id != user_id
            or req.status != "paypal_issued"
        ):
            return None

        now = datetime.utcnow()
        req.keep_confirmed_at = now
        req.collection_notified_at = None
        req.working_bucket_at = now
        req.updated_at = now

        await session.commit()
        await session.refresh(req)
        return req


async def list_unconfirmed_collection(day: str) -> list[Request]:
    async with SessionLocal() as session:
        working_expr = func.coalesce(
            Request.working_bucket_at,
            Request.processed_at,
            Request.updated_at,
            Request.created_at,
        )
        rows = await session.scalars(
            select(Request)
            .join(PaypalTag, PaypalTag.id == Request.paypal_tag_id)
            .where(
                PaypalTag.status == "issued",
                func.to_char(
                    working_expr + text("INTERVAL '3 hours'"),
                    'YYYY-MM-DD',
                ) == day,
                Request.status == "paypal_issued",
                Request.collection_notified_at.is_not(None),
                Request.keep_confirmed_at.is_(None),
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
                func.to_char(
                    PaypalTag.issued_at + text("INTERVAL '3 hours'"),
                    "YYYY-MM-DD",
                ) == day,
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
            select(Request, User.username, User.full_name, PaypalTag.tag)
            .join(PaypalTag, PaypalTag.id == Request.paypal_tag_id)
            .join(User, User.id == Request.user_id)
            .where(Request.status == "paypal_issued")
            .where(
                PaypalTag.tag.ilike(pattern)
                | User.username.ilike(pattern)
                | User.full_name.ilike(pattern)
                | func.cast(Request.user_id, String).ilike(pattern)
            )
            .order_by(PaypalTag.issued_at.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        result: list[Request] = []
        for req, username, full_name, paypal_tag in rows:
            duplicate_count = int(
                await session.scalar(
                    select(func.count(Request.id)).where(
                        Request.paypal_tag_id == req.paypal_tag_id,
                        Request.status == "paypal_issued",
                    )
                )
                or 0
            )
            req._display_username = (
                f"@{username}" if username else (full_name or str(req.user_id))
            )
            req._display_tag = paypal_tag
            req._display_duplicate_count = duplicate_count
            result.append(req)
        return result


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
        today_start, today_end = _moscow_day_utc_bounds(_moscow_today())
        return {
            "available": await scalar(select(func.count(PaypalTag.id)).where(PaypalTag.status == "available")),
            "working": await scalar(select(func.count(Request.id)).where(Request.status == "paypal_issued")),
            "waiting_check": await scalar(select(func.count(Request.id)).where(Request.status == "waiting_check")),
            "payout_pending": await scalar(select(func.count(Request.id)).where(Request.status == "payout_pending")),
            "paid_today": await scalar(
                select(func.count(Request.id)).where(
                    Request.status == "paid_out",
                    Request.payout_at >= today_start,
                    Request.payout_at < today_end,
                )
            ),
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
    end = None
    today_msk = _moscow_today()
    if period == "today":
        start, end = _moscow_day_utc_bounds(today_msk)
    elif period == "yesterday":
        start, end = _moscow_day_utc_bounds(
            today_msk - timedelta(days=1)
        )
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    async with SessionLocal() as session:
        conditions = []
        if start:
            conditions.append(Request.created_at >= start)
        if end:
            conditions.append(Request.created_at < end)
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


async def list_manual_payouts(user_id: int, limit: int = 10, offset: int = 0) -> list[ManualPayout]:
    async with SessionLocal() as session:
        return list(await session.scalars(
            select(ManualPayout)
            .where(ManualPayout.user_id == user_id)
            .order_by(ManualPayout.id.desc())
            .offset(offset)
            .limit(limit)
        ))


async def get_manual_payout(payout_id: int) -> ManualPayout | None:
    async with SessionLocal() as session:
        return await session.get(ManualPayout, payout_id)


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
