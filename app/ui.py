from __future__ import annotations

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
