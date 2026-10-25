from __future__ import annotations
from datetime import datetime
from math import ceil
from zoneinfo import ZoneInfo


def withdrawal_wait_text(req, now: datetime | None = None) -> str:
    """Display-only deadline; expiry never releases funds."""
    retry_at = getattr(req, "withdrawal_retry_at", None)
    if retry_at is None:
        return "⏳ Ожидает вывода с PayPal"
    now = now or datetime.utcnow()
    if retry_at <= now:
        return "🔄 Ожидает повторной попытки вывода"
    minutes = ceil((retry_at - now).total_seconds() / 60)
    return f"⏳ До повторной попытки: {minutes // 60} ч {minutes % 60:02d} мин"


def withdrawal_retry_date(req) -> str:
    retry_at = getattr(req, "withdrawal_retry_at", None)
    if retry_at is None:
        return ""
    local = retry_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/Moscow"))
    return local.strftime("%d.%m.%Y %H:%M МСК")

DIVIDER = "━━━━━━━━━━━━━━━━━━"


def card(title: str, body: str, footer: str | None = None) -> str:
    parts = [DIVIDER, f"<b>{title}</b>", DIVIDER, "", body.strip()]
    if footer:
        parts.extend(["", footer.strip()])
    parts.extend(["", DIVIDER])
    return "\n".join(parts)


def user_home_caption(work_enabled: bool = True) -> str:
    status = "🟢 Сервис работает" if work_enabled else "🔴 Новые заявки временно закрыты"
    return card(
        "DT TEAM · PAYPAL SERVICE",
        "👋 Добро пожаловать в закрытый сервис DT Team.\n\n"
        "Получайте PayPal, отслеживайте заявки и выплаты в одном месте.",
        status,
    )


def admin_dashboard_caption(
    data: dict,
    work_enabled: bool,
    updated_at: str,
    auto_issue_enabled: bool = False,
) -> str:
    mode = "🟢 START WORK" if work_enabled else "🔴 STOP WORK"
    auto_mode = "🟢 ВКЛ" if auto_issue_enabled else "🔴 ВЫКЛ"
    body = (
        f"Режим: <b>{mode}</b>\n"
        f"🤖 Автовыдача: <b>{auto_mode}</b>\n\n"
        f"🟢 Свободно: <b>{data['available']}</b>\n"
        f"🔵 В работе: <b>{data['working']}</b>\n"
        f"📥 Новые заявки: <b>{data['queue']}</b>\n"
        f"🟠 На проверке: <b>{data['waiting_check']}</b>\n"
        f"⏳ Ожидают вывода: <b>{data.get('withdrawal_pending', 0)}</b>\n"
        f"🟣 К выплате: <b>{data['payout_pending']}</b>\n"
        f"✅ Выплачено сегодня: <b>{data['paid_today']}</b>\n"
        f"🔴 GS: <b>{data['gs']}</b>\n"
        f"👥 Пользователей: <b>{data['users']}</b>"
    )
    return card("⚙️ DT TEAM · CONTROL CENTER", body, f"🔄 Обновлено: <b>{updated_at}</b>")


def request_amount_caption() -> str:
    return card(
        "💳 НОВАЯ ЗАЯВКА",
        "Введите необходимую сумму в евро одним числом.\n\n"
        "Пример: <code>150</code>",
        "Следующий шаг — выбор типа PayPal",
    )


def support_caption() -> str:
    return (
        "🆘 <b>ПОДДЕРЖКА</b>\n\n"
        "Если у вас возникли вопросы,\n"
        "обратитесь в службу поддержки.\n\n"
        "💬 <b>Чат поддержки:</b>\n"
        "@workzin\n"
        "@profitgeld"
    )
