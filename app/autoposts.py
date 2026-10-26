"""Daily Moscow-time posts. No catch-up and no automatic resend of a claimed run."""
import asyncio
import logging
import re
from datetime import datetime
from html import escape
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app import db

logger = logging.getLogger(__name__)
MSK = ZoneInfo("Europe/Moscow")
UTC = ZoneInfo("UTC")
ASSETS = Path(__file__).resolve().parent.parent / "assets"
BUILTIN_PHOTOS = {"asset:day": ASSETS / "auto_post_day.png", "asset:evening": ASSETS / "auto_post_evening.png"}
DEFAULT_BODY = (
    "🇪🇺REG EU PAYPAL\n\n"
    "7️⃣0️⃣% от 1️⃣0️⃣0️⃣€\n\n"
    "6️⃣0️⃣% от 5️⃣0️⃣ €\n\n"
    "🔥Минимум гестопов\n\n"
    "✅1 палка = 1 платеж\n\n"
    "🚀Support : @profitgeld\n@workzin"
)
PAGE_SIZE = 10


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)


def parse_time(value: str) -> int:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value.strip()):
        raise ValueError("Введите время в формате ЧЧ:ММ, например 13:00. Время московское.")
    hour, minute = map(int, value.strip().split(":"))
    return hour * 60 + minute


def display_time(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def validate_field(field, value):
    if field == "name":
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
            raise ValueError("Название: от 1 до 80 символов.")
        return value.strip()
    if field == "body":
        if not isinstance(value, str) or not value.strip() or len(value.encode("utf-16-le")) // 2 > 1024:
            raise ValueError("Текст: от 1 до 1024 символов Telegram. Эмодзи могут занимать несколько символов.")
        return value  # Plain text; markup is escaped only at delivery.
    if field == "minute":
        if type(value) is not int or not 0 <= value < 1440:
            raise ValueError("Некорректное время.")
        return value
    if field == "photo":
        if not isinstance(value, str) or len(value) > 512:
            raise ValueError("Некорректная картинка.")
        if value.startswith("asset:") and value not in BUILTIN_PHOTOS:
            raise ValueError("Неизвестный баннер.")
        return value
    if field == "enabled":
        if value not in (0, 1):
            raise ValueError("Некорректное состояние.")
        return int(value)
    raise ValueError("Неизвестное поле.")


async def seed_auto_posts():
    """Unique seed keys survive soft deletion, so restart never restores a removed post."""
    async with db.SessionLocal() as session:
        for key, name, minute, photo in (
            ("seed:day", "Дневной · PayPal ждёт тебя", 13 * 60, "asset:day"),
            ("seed:evening", "Вечерний · Продолжаем работу", 18 * 60, "asset:evening"),
        ):
            await session.execute(text("""
                INSERT INTO auto_posts
                    (creation_key, name, body, photo, minute, enabled, revision, schedule_changed_at, created_at)
                VALUES (:key, :name, :body, :photo, :minute, 1, 1, :now, :now)
                ON CONFLICT (creation_key) DO NOTHING
            """), dict(key=key, name=name, body=DEFAULT_BODY, photo=photo, minute=minute, now=utc_now()))
        await session.commit()


async def create_post(draft: dict, creation_key: str | None = None):
    values = {key: validate_field(key, draft[key]) for key in ("name", "body", "minute", "photo")}
    key = creation_key or str(uuid4())
    async with db.SessionLocal() as session:
        row = db.AutoPost(**values, creation_key=key, enabled=1, revision=1, schedule_changed_at=utc_now())
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # Double press of Save returns the same post, not another schedule.
            row = await session.scalar(select(db.AutoPost).where(db.AutoPost.creation_key == key))
            if row is None:
                raise
        return row


async def get_post(post_id):
    async with db.SessionLocal() as session:
        row = await session.get(db.AutoPost, post_id)
        return row if row and row.deleted_at is None else None


async def list_posts(page=0):
    async with db.SessionLocal() as session:
        where = db.AutoPost.deleted_at.is_(None)
        total = int(await session.scalar(select(func.count(db.AutoPost.id)).where(where)) or 0)
        last = max(0, (total - 1) // PAGE_SIZE)
        page = min(max(0, page), last)
        rows = list(await session.scalars(select(db.AutoPost).where(where)
                    .order_by(db.AutoPost.minute, db.AutoPost.id).offset(page * PAGE_SIZE).limit(PAGE_SIZE)))
        return dict(rows=rows, total=total, page=page, last=last)


async def edit_post(post_id, revision, field, value):
    value = validate_field(field, value)
    async with db.SessionLocal() as session:
        row = await session.get(db.AutoPost, post_id, with_for_update=True)
        if row is None or row.deleted_at is not None or row.revision != revision:
            return None
        if getattr(row, field) != value:
            setattr(row, field, value)
            row.revision += 1
            if field in {"minute", "enabled"}:
                row.schedule_changed_at = utc_now()
            await session.commit()
        return row


async def delete_post(post_id, revision):
    async with db.SessionLocal() as session:
        row = await session.get(db.AutoPost, post_id, with_for_update=True)
        if row is None or row.deleted_at is not None or row.revision != revision:
            return False
        row.deleted_at = utc_now()
        row.enabled = 0
        row.revision += 1
        await session.commit()
        return True


async def last_run(post_id):
    async with db.SessionLocal() as session:
        return await session.scalar(select(db.AutoPostRun).where(db.AutoPostRun.post_id == post_id)
                                    .order_by(db.AutoPostRun.day.desc()).limit(1))


def local_slot(now):
    """UTC naive storage, explicit Moscow date and minute (independent of host TZ)."""
    aware = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    local = aware.astimezone(MSK)
    return local.date().isoformat(), local.hour * 60 + local.minute, aware.replace(second=0, microsecond=0, tzinfo=None)


async def claim_due_post(post_id, now):
    day, minute, scheduled = local_slot(now)
    async with db.SessionLocal() as session:
        post = await session.get(db.AutoPost, post_id, with_for_update=True)
        if not post or post.deleted_at is not None or not post.enabled or post.minute != minute:
            return None
        if await session.get(db.AutoPostRun, (post_id, day)):
            return None
        work = await session.get(db.AppSetting, "work_enabled")
        reason = ""
        if not work or work.value != "1":
            reason = "STOP WORK"
        elif work.updated_at > scheduled:
            reason = "START WORK включён после времени поста"
        elif post.schedule_changed_at > scheduled:
            reason = "Расписание включено или изменено после времени поста"
        row = db.AutoPostRun(post_id=post_id, day=day, revision=post.revision, scheduled_at=scheduled,
                             status="skipped" if reason else "sending", reason=reason,
                             started_at=now.replace(tzinfo=None) if now.tzinfo is None else now.astimezone(UTC).replace(tzinfo=None),
                             finished_at=utc_now() if reason else None)
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            # The primary key also arbitrates two worker instances on PostgreSQL.
            await session.rollback()
            return None
        return row


async def delivery_guard(run, user_id=None):
    async with db.SessionLocal() as session:
        post = await session.get(db.AutoPost, run.post_id)
        if not post or post.deleted_at is not None or not post.enabled or post.revision != run.revision:
            return "stop", "Пост изменён, выключен или удалён"
        work = await session.get(db.AppSetting, "work_enabled")
        if not work or work.value != "1" or work.updated_at > run.scheduled_at:
            return "stop", "STOP WORK или новый сеанс работы"
        if user_id is not None:
            user = await session.get(db.User, user_id)
            if not user or user.status != "approved":
                return "skip", "Доступ участника изменён"
        return "ok", ""


def post_markup():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💳 Получить PayPal", callback_data="paypal_request")
    ]])


async def send_post(bot, chat_id, post):
    caption = escape(post.body)
    kwargs = dict(reply_markup=post_markup(), parse_mode="HTML")
    if post.photo:
        if post.photo.startswith("asset:"):
            path = BUILTIN_PHOTOS[post.photo]
            if not path.is_file():
                raise FileNotFoundError(path.name)
            photo = FSInputFile(path)
        else:
            photo = post.photo
        return await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, **kwargs)
    else:
        return await bot.send_message(chat_id=chat_id, text=caption, **kwargs)


def remember_photo(post, result):
    # Upload each bundled banner only once per run, then reuse Telegram's file id.
    # The detached post is a delivery snapshot; the stored editable image stays intact.
    photos = getattr(result, "photo", None)
    if post.photo.startswith("asset:") and isinstance(photos, (list, tuple)) and photos:
        file_id = getattr(photos[-1], "file_id", None)
        if isinstance(file_id, str) and file_id:
            post.photo = file_id


async def save_progress(run, *, status=None, reason=""):
    async with db.SessionLocal() as session:
        saved = await session.get(db.AutoPostRun, (run.post_id, run.day))
        saved.sent, saved.failed, saved.total = run.sent, run.failed, run.total
        if status:
            saved.status, saved.reason, saved.finished_at = status, reason, utc_now()
        await session.commit()


async def deliver_run(bot, run, *, sleep=asyncio.sleep, pace=None):
    """At most one automatic attempt per recipient; only an explicit 429 is retried.

    A restarted/second process cannot resume a claimed run. This favors no
    duplicate promotional messages over retrying an ambiguous Telegram delivery.
    """
    status, reason = "complete", ""
    try:
        post = await get_post(run.post_id)
        if post is None:
            status, reason = "stopped", "Пост удалён"
            return
        users = await db.list_approved_user_ids()
        run.total = len(users)
        await save_progress(run)
        for user_id in users:
            if pace:
                await pace()
            else:
                await sleep(0.15)
            mode, guard_reason = await delivery_guard(run, user_id)
            if mode == "stop":
                status, reason = "stopped", guard_reason
                break
            if mode == "skip":
                continue
            try:
                result = await asyncio.wait_for(send_post(bot, user_id, post), timeout=20)
            except TelegramRetryAfter as exc:
                if exc.retry_after > 60:
                    status, reason = "interrupted", "Telegram запросил длительную паузу"
                    break
                await sleep(max(0, exc.retry_after) + 0.1)
                if pace:
                    await pace()
                else:
                    await sleep(0.15)
                mode, guard_reason = await delivery_guard(run, user_id)
                if mode == "stop":
                    status, reason = "stopped", guard_reason
                    break
                if mode == "skip":
                    continue
                try:
                    result = await asyncio.wait_for(send_post(bot, user_id, post), timeout=20)
                except TelegramRetryAfter:
                    status, reason = "interrupted", "Повторное ограничение Telegram"
                    break
                except Exception as error:
                    run.failed += 1
                    logger.warning("Auto post %s delivery failed: %s", run.post_id, type(error).__name__)
                else:
                    remember_photo(post, result)
                    run.sent += 1
            except Exception as error:
                run.failed += 1
                logger.warning("Auto post %s delivery failed: %s", run.post_id, type(error).__name__)
            else:
                remember_photo(post, result)
                run.sent += 1
            await save_progress(run)
        if status == "complete" and run.failed:
            status = "partial"
    except asyncio.CancelledError:
        status, reason = "interrupted", "Рассылка прервана; автоматического повтора нет"
        raise
    except Exception:
        status, reason = "error", "Ошибка рассылки; подробности в журнале сервера"
        logger.exception("Auto post %s run failed", run.post_id)
    finally:
        await save_progress(run, status=status, reason=reason)


async def claim_due_runs(now=None):
    now = now or utc_now()
    _, minute, _ = local_slot(now)
    async with db.SessionLocal() as session:
        ids = list(await session.scalars(select(db.AutoPost.id).where(
            db.AutoPost.minute == minute, db.AutoPost.enabled == 1, db.AutoPost.deleted_at.is_(None)
        ).order_by(db.AutoPost.id)))
    # Claim every post scheduled for this minute before starting network I/O.
    runs = []
    for post_id in ids:
        run = await claim_due_post(post_id, now)
        if run is not None and run.status == "sending":
            runs.append(run)
    return runs


async def deliver_with_timeout(bot, run, *, sleep=asyncio.sleep, pace=None):
    try:
        await asyncio.wait_for(deliver_run(bot, run, sleep=sleep, pace=pace), timeout=20 * 60)
    except asyncio.TimeoutError:
        logger.warning("Auto post %s exceeded the delivery time limit", run.post_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Auto post %s could not record delivery result", run.post_id)


async def tick(bot, *, now=None, sleep=asyncio.sleep):
    for run in await claim_due_runs(now):
        await deliver_with_timeout(bot, run, sleep=sleep)


async def auto_post_loop(bot):
    tasks = set()
    pace_lock = asyncio.Lock()

    async def pace():
        # All simultaneous posts share one send rate. Check START WORK afterwards.
        async with pace_lock:
            await asyncio.sleep(0.15)

    try:
        while True:
            try:
                for run in await claim_due_runs():
                    task = asyncio.create_task(deliver_with_timeout(bot, run, pace=pace))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Auto post scheduler tick failed")
            # A slow broadcast does not prevent noticing another scheduled minute.
            await asyncio.sleep(10)
    finally:
        pending = list(tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
