from __future__ import annotations
from datetime import datetime
from math import ceil
from zoneinfo import ZoneInfo
import re


HOME_SUMMARY_TEMPLATE = (
    "<b>Твой рабочий день 👋</b>\n\n{status}\n\n"
    "💳 В работе: <b>{working} PayPal</b>\n"
    "⏳ Ожидают вывода: <b>{held} USDT</b>\n"
    "💰 Доступно к выплате: <b>{available} USDT</b>"
)


def remove_old_placeholder(template: str, token: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", template.replace("{" + token + "}", "")).strip()


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


def user_home_caption(
    work_enabled: bool = True, *, summary: dict | None = None,
    template: str = HOME_SUMMARY_TEMPLATE,
) -> str:
    summary = summary or {}
    values = {
        "status": "🟢 Работа открыта" if work_enabled else "🔴 Новые заявки временно закрыты",
        "working": str(int(summary.get("working", 0))),
        "held": f"{summary.get('held', 0):.2f}",
        "available": f"{summary.get('available', 0):.2f}",
    }
    template = remove_old_placeholder(template, "rates")
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


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
    return (
        "<b>💳 Получить PayPal</b>\n\n"
        "Введите ожидаемую сумму в евро целым числом.\n\n"
        "Пример: <code>100</code>\n\n"
        "Следующий шаг — выбор типа PayPal."
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
