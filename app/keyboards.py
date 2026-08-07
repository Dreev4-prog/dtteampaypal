from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 ПОЛУЧИТЬ PAYPAL", callback_data="paypal_request")],
        [InlineKeyboardButton(text="📂 МОИ PAYPAL", callback_data="my_paypals")],
        [InlineKeyboardButton(text="💰 КОШЕЛЁК", callback_data="wallet")],
        [InlineKeyboardButton(text="👤 ЛИЧНЫЙ КАБИНЕТ", callback_data="profile")],
        [InlineKeyboardButton(text="🛟 ПОДДЕРЖКА", callback_data="support")],
    ])


def membership_apply_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Подать заявку на вступление", callback_data="membership_apply")]
    ])


def membership_admin_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"membership_approve:{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"membership_reject:{user_id}"),
        ],
        [InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"membership_block:{user_id}")],
        [InlineKeyboardButton(text="👤 Открыть карточку", callback_data=f"member_card:{user_id}")],
    ])


def admin_main_menu(pending_count: int = 0, queue_count: int = 0) -> InlineKeyboardMarkup:
    queue_label = f"📥 ОЧЕРЕДЬ PAYPAL ({queue_count})"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=queue_label, callback_data="paypal_queue:0")],
        [
            InlineKeyboardButton(text="💳 РАБОТА С PAYPAL", callback_data="paypal_payments_hub"),
            InlineKeyboardButton(text="💼 ВЫПЛАТЫ", callback_data="payouts_v22"),
        ],
        [InlineKeyboardButton(text="👥 ПОЛЬЗОВАТЕЛИ И СТАТИСТИКА", callback_data="members_menu")],
        [InlineKeyboardButton(text="📣 КОНТЕНТ И РАССЫЛКИ", callback_data="content_menu")],
        [
            InlineKeyboardButton(text="⚙️ ПРОЦЕНТЫ", callback_data="rates_menu"),
            InlineKeyboardButton(text="▶️ START / ⏹ STOP", callback_data="work_control"),
        ],
        [InlineKeyboardButton(text="🔥 HAPPY HOURS", callback_data="happy_hours_menu")],
        [InlineKeyboardButton(text="🔍 ОБЩИЙ ПОИСК", callback_data="global_search")],
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="admin_home")],
    ])


def paypal_payments_hub_menu(
    payment_counts: dict[str, int] | None = None,
    database_counts: dict[str, int] | None = None,
) -> InlineKeyboardMarkup:
    payment_counts = payment_counts or {}
    database_counts = database_counts or {}
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"🟠 Проверка оплат ({payment_counts.get('check', 0)})",
                callback_data="payments_list:check:0",
            ),
            InlineKeyboardButton(
                text=f"🟡 PayPal в работе ({database_counts.get('issued', 0)})",
                callback_data="working_dates",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"💸 Вывести деньги ({payment_counts.get('payout', 0)})",
                callback_data="payments_list:payout:0",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"🟢 Свободные ({database_counts.get('available', 0)})",
                callback_data="paypal_db_list:available:0",
            ),
            InlineKeyboardButton(
                text=f"↩️ Возвраты ({database_counts.get('return_pending', 0)})",
                callback_data="returns_menu",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"🚫 Gestop ({database_counts.get('gestoppt', 0)})",
                callback_data="paypal_db_list:gestoppt:0",
            ),
            InlineKeyboardButton(
                text=f"🚫 GS ({database_counts.get('gs', 0)})",
                callback_data="paypal_db_list:gs:0",
            ),
        ],
        [
            InlineKeyboardButton(text="➕ Добавить PayPal", callback_data="paypal_add_single"),
            InlineKeyboardButton(text="📥 Массовое добавление", callback_data="paypal_add_bulk"),
        ],
        [
            InlineKeyboardButton(
                text=f"🗑 Корзина ({database_counts.get('deleted', 0)})",
                callback_data="paypal_db_list:deleted:0",
            ),
        ],
        [InlineKeyboardButton(text="📋 Вся база PayPal", callback_data="paypal_database")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")],
    ])


def members_menu(counts: dict[str, int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Подробная статистика", callback_data="statistics_menu")],
        [InlineKeyboardButton(text=f"📋 Все ({counts.get('all', 0)})", callback_data="members_list:all:0")],
        [
            InlineKeyboardButton(text=f"🟢 Активные ({counts.get('approved', 0)})", callback_data="members_list:approved:0"),
            InlineKeyboardButton(text=f"🟡 Ожидают ({counts.get('pending', 0)})", callback_data="members_list:pending:0"),
        ],
        [
            InlineKeyboardButton(text=f"❌ Отклонённые ({counts.get('rejected', 0)})", callback_data="members_list:rejected:0"),
            InlineKeyboardButton(text=f"🚫 Заблокированные ({counts.get('blocked', 0)})", callback_data="members_list:blocked:0"),
        ],
        [InlineKeyboardButton(text="🏷 Поиск по Telegram-тегу", callback_data="member_tag_search")],
        [InlineKeyboardButton(text="🔍 Расширенный поиск", callback_data="member_search")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")],
    ])


def members_list_menu(users: list, status: str, offset: int, page_size: int, has_next: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for user in users:
        username = f"@{user.username}" if user.username else str(user.id)
        rows.append([InlineKeyboardButton(text=username, callback_data=f"member_card:{user.id}")])

    navigation: list[InlineKeyboardButton] = []
    if offset > 0:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"members_list:{status}:{max(0, offset-page_size)}"))
    if has_next:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"members_list:{status}:{offset+page_size}"))
    if navigation:
        rows.append(navigation)

    rows.append([InlineKeyboardButton(text="⬅️ Участники", callback_data="members_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def member_card_menu(user_id: int, status: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if status != "approved":
        rows.append([InlineKeyboardButton(text="✅ Одобрить", callback_data=f"member_set:approved:{user_id}")])
    if status != "rejected":
        rows.append([InlineKeyboardButton(text="❌ Отклонить", callback_data=f"member_set:rejected:{user_id}")])
    if status != "blocked":
        rows.append([InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"member_set:blocked:{user_id}")])
    if status == "blocked":
        rows.append([InlineKeyboardButton(text="🔓 Разблокировать", callback_data=f"member_set:approved:{user_id}")])
    if status == "approved":
        rows.append([InlineKeyboardButton(text="↩️ Отозвать доступ", callback_data=f"member_set:pending:{user_id}")])
    rows.append([InlineKeyboardButton(text="💬 Написать пользователю", url=f"tg://user?id={user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ К участникам", callback_data="members_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_search_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="members_menu")]
    ])


def request_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить заявку", callback_data="request_cancel")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="home")],
    ])


def paypal_queue_menu(requests: list, offset: int, page_size: int, has_next: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for req in requests:
        rows.append([InlineKeyboardButton(
            text=f"#{req.id} · {req.amount} € · ID {req.user_id}",
            callback_data=f"queue_card:{req.id}"
        )])
    navigation: list[InlineKeyboardButton] = []
    if offset > 0:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"paypal_queue:{max(0, offset-page_size)}"))
    if has_next:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"paypal_queue:{offset+page_size}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data=f"paypal_queue:{offset}")])
    rows.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def queue_request_menu(request_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выдать PayPal", callback_data=f"admin_issue:{request_id}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"admin_reject:{request_id}"),
        ],
        [InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"queue_block:{request_id}:{user_id}")],
        [InlineKeyboardButton(text="💬 Написать", url=f"tg://user?id={user_id}")],
        [InlineKeyboardButton(text="⬅️ К очереди", callback_data="paypal_queue:0")],
    ])


def admin_request_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выдать PayPal", callback_data=f"admin_issue:{request_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject:{request_id}"),
        ]
    ])


def paid_button(request_id: int) -> InlineKeyboardMarkup:
    return paid_or_return_menu(request_id)


def admin_check_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm:{request_id}"),
            InlineKeyboardButton(text="❌ Денег нет", callback_data=f"admin_not_found:{request_id}"),
        ],
        [InlineKeyboardButton(text="🚫 GS (Goods & Services)", callback_data=f"admin_gs:{request_id}") ]
    ])


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="home")]
    ])


def payments_menu(counts: dict[str, int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🟠 Проверить оплату ({counts.get('check', 0)})", callback_data="payments_list:check:0")],
        [InlineKeyboardButton(text=f"💸 Вывести деньги ({counts.get('payout', 0)})", callback_data="payments_list:payout:0")],
        [InlineKeyboardButton(text=f"✅ Выплаченные ({counts.get('paidout', 0)})", callback_data="payments_list:paidout:0")],
        [InlineKeyboardButton(text=f"🕓 Ожидают оплаты ({counts.get('waiting', 0)})", callback_data="payments_list:waiting:0")],
        [InlineKeyboardButton(text=f"🔴 Оплата не найдена ({counts.get('notfound', 0)})", callback_data="payments_list:notfound:0")],
        [InlineKeyboardButton(text=f"📋 Все ({counts.get('all', 0)})", callback_data="payments_list:all:0")],
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="payments_menu")],
        [InlineKeyboardButton(text="⬅️ Работа с PayPal", callback_data="paypal_payments_hub")],
    ])


def payments_list_menu(requests: list, filter_name: str, offset: int, page_size: int, has_next: bool) -> InlineKeyboardMarkup:
    status_icons = {
        "paypal_issued": "🕓", "waiting_check": "🟠", "payout_pending": "🟢",
        "paid_out": "✅", "not_found": "🔴",
    }
    rows = []
    for req in requests:
        icon = status_icons.get(req.status, "•")
        username = getattr(req, "_display_username", f"ID {req.user_id}")
        paypal_tag = getattr(req, "_display_tag", "—")

        if filter_name == "payout":
            withdraw_icon = "🟢" if getattr(req, "paypal_withdrawn_at", None) else "🔴"
            withdraw_text = "ВЫВЕДЕНО" if getattr(req, "paypal_withdrawn_at", None) else "НЕ ВЫВЕДЕНО"
            button_text = (
                f"{withdraw_icon} {withdraw_text} · 👤 {username} · "
                f"💳 {paypal_tag} · 💶 {req.amount} €"
            )
        else:
            button_text = (
                f"{icon} 👤 {username} · 💳 {paypal_tag} · 💶 {req.amount} €"
            )

        rows.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"payment_card:{req.id}:{filter_name}:{offset}",
        )])
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"payments_list:{filter_name}:{max(0, offset-page_size)}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"payments_list:{filter_name}:{offset+page_size}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data=f"payments_list:{filter_name}:{offset}")])
    if filter_name in {"check", "payout"}:
        rows.append([
            InlineKeyboardButton(
                text="⬅️ Работа с PayPal",
                callback_data="paypal_payments_hub",
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="⬅️ К категориям платежей",
                callback_data="payments_menu",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_card_menu(
    request_id: int,
    user_id: int,
    status: str,
    filter_name: str = "all",
    offset: int = 0,
    paypal_withdrawn: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if status == "waiting_check":
        rows.append([
            InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"admin_confirm:{request_id}"),
            InlineKeyboardButton(text="❌ Не найдено", callback_data=f"admin_not_found:{request_id}"),
        ])
    elif status == "payout_pending":
        if not paypal_withdrawn:
            rows.append([
                InlineKeyboardButton(
                    text="✅ Сделано — деньги выведены",
                    callback_data=f"paypal_withdraw_done:{request_id}:{filter_name}:{offset}",
                )
            ])
        else:
            rows.append([
                InlineKeyboardButton(
                    text="🟢 Деньги уже выведены",
                    callback_data=f"paypal_withdraw_info:{request_id}",
                )
            ])
        rows.append([
            InlineKeyboardButton(
                text="💼 Открыть выплаты пользователя",
                callback_data=f"payout_user:{user_id}",
            )
        ])
    elif status == "not_found":
        rows.append([InlineKeyboardButton(text="↩️ Вернуть на проверку", callback_data=f"payment_recheck:{request_id}")])
    rows.append([InlineKeyboardButton(text="💬 Написать клиенту", url=f"tg://user?id={user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ К списку", callback_data=f"payments_list:{filter_name}:{offset}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payout_confirmation_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, выплатил", callback_data=f"payout_done:{request_id}")],
        [InlineKeyboardButton(text="↩️ Отмена", callback_data=f"payment_card:{request_id}:payout:0")],
    ])


def user_amount_confirmation_menu(request_id: int, amount: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Подтвердить {amount} €", callback_data=f"user_paid_confirm:{request_id}")],
        [InlineKeyboardButton(text="✏️ Изменить сумму", callback_data=f"user_paid_change:{request_id}")],
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="home")],
    ])


def admin_amount_confirmation_menu(request_id: int, amount: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Подтвердить {amount} €", callback_data=f"admin_confirm_same:{request_id}")],
        [InlineKeyboardButton(text="✏️ Изменить сумму", callback_data=f"admin_confirm_change:{request_id}")],
        [InlineKeyboardButton(text="↩️ Отмена", callback_data=f"payment_card:{request_id}:check:0")],
    ])


def rates_menu(rules: list) -> InlineKeyboardMarkup:
    rows = []
    for rule in rules:
        rows.append([
            InlineKeyboardButton(text=f"От {rule.min_amount} € — {rule.percent}%", callback_data=f"rate_edit:{rule.id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"rate_delete:{rule.id}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Добавить диапазон", callback_data="rate_add")])
    rows.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def happy_hours_menu(is_open: bool, has_photo: bool = False) -> InlineKeyboardMarkup:
    if is_open:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Завершить Happy Hours", callback_data="happy_hours_stop")],
            [InlineKeyboardButton(text="🔄 Обновить статистику", callback_data="happy_hours_menu")],
            [InlineKeyboardButton(text="📜 История акций", callback_data="happy_hours_history")],
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")],
        ])

    photo_label = "🖼 Картинка ✅" if has_photo else "🖼 Картинка"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить Happy Hours", callback_data="happy_hours_launch_ask")],
        [
            InlineKeyboardButton(text="🕐 Начало", callback_data="happy_hours_edit_start"),
            InlineKeyboardButton(text="🕔 Окончание", callback_data="happy_hours_edit_end"),
        ],
        [
            InlineKeyboardButton(text="💶 Минимальная сумма", callback_data="happy_hours_edit_min"),
            InlineKeyboardButton(text="📈 Процент", callback_data="happy_hours_edit_percent"),
        ],
        [
            InlineKeyboardButton(text="📝 Текст рассылки", callback_data="happy_hours_edit_text"),
            InlineKeyboardButton(text=photo_label, callback_data="happy_hours_edit_photo"),
        ],
        [InlineKeyboardButton(text="👁 Предпросмотр рассылки", callback_data="happy_hours_preview")],
        [InlineKeyboardButton(text="📜 История акций", callback_data="happy_hours_history")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")],
    ])


def happy_hours_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="happy_hours_menu")]
    ])


def happy_hours_photo_menu(has_photo: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_photo:
        rows.append([
            InlineKeyboardButton(
                text="🗑 Удалить картинку",
                callback_data="happy_hours_photo_delete",
            )
        ])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="happy_hours_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def happy_hours_launch_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Запустить и разослать", callback_data="happy_hours_launch_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="happy_hours_menu")],
    ])


def happy_hours_preview_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ К Happy Hours", callback_data="happy_hours_menu")]
    ])


def finance_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="finance_menu")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")],
    ])

def rate_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="rates_menu")]])


def my_paypals_menu(counts: dict[str, int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📨 Запросы на PayPal ({counts.get('requests', 0)})", callback_data="my_paypals_list:requests")],
        [InlineKeyboardButton(text=f"💳 Ожидают оплаты ({counts.get('waiting', 0)})", callback_data="my_paypals_list:waiting")],
        [InlineKeyboardButton(text=f"🟠 На проверке ({counts.get('check', 0)})", callback_data="my_paypals_list:check")],
        [InlineKeyboardButton(text=f"🟢 Ожидают выплату ({counts.get('payout', 0)})", callback_data="my_paypals_list:payout")],
        [InlineKeyboardButton(text=f"✅ Выплаченные ({counts.get('paid', 0)})", callback_data="my_paypals_list:paid")],
        [InlineKeyboardButton(text=f"❌ Не оплаченные/отклонённые ({counts.get('closed', 0)})", callback_data="my_paypals_list:closed")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="home")],
    ])


def my_paypals_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Мои PayPal", callback_data="my_paypals")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])


def my_paypals_waiting_list_menu(requests: list) -> InlineKeyboardMarkup:
    rows = []
    for req in requests:
        paypal_tag = getattr(req, "_display_tag", "—")
        rows.append([
            InlineKeyboardButton(
                text=(
                    f"{'🔥 ' if getattr(req, '_happy_hours_badge', False) else ''}"
                    f"💳 {paypal_tag} · 💶 {req.amount} €"
                ),
                callback_data=f"my_paypal_card:{req.id}",
            )
        ])

    rows.extend([
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="my_paypals_list:waiting")],
        [InlineKeyboardButton(text="⬅️ Мои PayPal", callback_data="my_paypals")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_paypal_waiting_card_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Я оплатил",
                callback_data=f"user_paid:{request_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="↩️ Вернуть PayPal",
                callback_data=f"return_start:{request_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ К ожидающим оплаты",
                callback_data="my_paypals_list:waiting",
            )
        ],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])


def paid_or_return_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"user_paid:{request_id}")],
        [InlineKeyboardButton(text="↩️ Вернуть PayPal", callback_data=f"return_start:{request_id}")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="home")],
    ])


def return_reasons_menu(request_id: int) -> InlineKeyboardMarkup:
    reasons = [
        ("❌ Передумал", "changed_mind"),
        ("🚫 Gestop", "gestop"),
        ("✍️ Другая причина", "other"),
    ]
    rows = [[InlineKeyboardButton(text=label, callback_data=f"return_reason:{request_id}:{code}")] for label, code in reasons]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="my_paypals")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def return_confirm_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить возврат", callback_data=f"return_confirm:{request_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="my_paypals")],
    ])


def returns_menu(items: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"↩️ {getattr(item, '_display_username', item.user_id)} · {getattr(item, '_display_tag', '—')} · {getattr(item, '_display_amount', 0)} €",
        callback_data=f"return_card:{item.id}",
    )] for item in items]
    rows += [[InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="returns_menu")], [InlineKeyboardButton(text="⬅️ Работа с PayPal", callback_data="paypal_payments_hub")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def return_card_menu(return_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Проверил PayPal", callback_data=f"return_checked:{return_id}")],
        [InlineKeyboardButton(text="💬 Написать пользователю", url=f"tg://user?id={user_id}")],
        [InlineKeyboardButton(text="⬅️ К возвратам", callback_data="returns_menu")],
    ])


def return_checked_menu(return_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Вернуть в работу", callback_data=f"return_release:{return_id}")],
        [InlineKeyboardButton(text="🚫 Gestop", callback_data=f"return_gestoppt:{return_id}")],
        [InlineKeyboardButton(text="🗑 Удалить PayPal", callback_data=f"return_delete:{return_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"return_card:{return_id}")],
    ])



def gender_choice_menu(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Мужской", callback_data=f"{prefix}:male"),
         InlineKeyboardButton(text="👩 Женский", callback_data=f"{prefix}:female")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="request_cancel" if prefix == "request_gender" else "paypal_add_cancel")],
    ])


def broadcast_photo_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Без картинки", callback_data="broadcast_no_photo")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
    ])


def broadcast_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Отправить всем", callback_data="broadcast_send")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")],
    ])


def gs_photo_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Без скриншота", callback_data=f"admin_gs_skip:{request_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"payment_card:{request_id}:check:0")],
    ])


def paypal_add_photo_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="paypal_add_skip_photo")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="paypal_add_cancel")],
    ])


def paypal_add_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить", callback_data="paypal_add_save")],
        [InlineKeyboardButton(text="✏️ Изменить", callback_data="paypal_add_restart")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="paypal_add_cancel")],
    ])


def paypal_add_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="paypal_add_cancel")],
    ])

def paypal_database_menu(counts: dict[str, int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить PayPal", callback_data="paypal_add_single"), InlineKeyboardButton(text="📥 Массовое добавление", callback_data="paypal_add_bulk")],
        [InlineKeyboardButton(text=f"🟢 Свободные ({counts.get('available', 0)})", callback_data="paypal_db_list:available:0")],
        [InlineKeyboardButton(text=f"👤 В работе ({counts.get('issued', 0)})", callback_data="working_dates")],
        [InlineKeyboardButton(text=f"↩️ Возвраты ({counts.get('return_pending', 0)})", callback_data="returns_menu")],
        [InlineKeyboardButton(text=f"🚫 Gestop ({counts.get('gestoppt', 0)})", callback_data="paypal_db_list:gestoppt:0")],
        [InlineKeyboardButton(text=f"🚫 GS ({counts.get('gs', 0)})", callback_data="paypal_db_list:gs:0")],
        [InlineKeyboardButton(text=f"🗑 Корзина ({counts.get('deleted', 0)})", callback_data="paypal_db_list:deleted:0")],
        [InlineKeyboardButton(text=f"📋 Все ({counts.get('all', 0)})", callback_data="paypal_db_list:all:0")],
        [InlineKeyboardButton(text="⬅️ Работа с PayPal", callback_data="paypal_payments_hub")],
    ])


def paypal_list_menu(tags: list, filter_name: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"💳 {tag.tag}", callback_data=f"paypal_card:{tag.id}:{filter_name}")] for tag in tags]
    rows.append([InlineKeyboardButton(text="⬅️ Работа с PayPal", callback_data="paypal_payments_hub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def paypal_card_admin_menu(
    tag_id: int,
    filter_name: str,
    status: str,
    restore_working_count: int = 0,
) -> InlineKeyboardMarkup:
    if status == "deleted":
        rows = []
        if restore_working_count == 1:
            rows.append([
                InlineKeyboardButton(
                    text="↩️ Вернуть прежнему пользователю",
                    callback_data=f"paypal_restore_working_ask:{tag_id}",
                )
            ])
        elif restore_working_count > 1:
            rows.append([
                InlineKeyboardButton(
                    text=f"👥 Выбрать пользователя ({restore_working_count})",
                    callback_data=f"paypal_restore_working_users:{tag_id}",
                )
            ])
        rows.append([
            InlineKeyboardButton(
                text="♻️ Восстановить свободным",
                callback_data=f"paypal_restore_ask:{tag_id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="⬅️ К корзине",
                callback_data="paypal_db_list:deleted:0",
            )
        ])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    rows = [
        [InlineKeyboardButton(text="🚫 Пометить Gestop", callback_data=f"paypal_mark_gestoppt:{tag_id}:{filter_name}")],
        [InlineKeyboardButton(text="🟢 Сделать свободным", callback_data=f"paypal_mark_available:{tag_id}:{filter_name}")],
    ]
    if status == "available":
        rows.append([InlineKeyboardButton(text="🗑 Удалить PayPal", callback_data=f"paypal_delete_ask:{tag_id}:{filter_name}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"paypal_db_list:{filter_name}:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def paypal_delete_confirm_menu(tag_id: int, filter_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"paypal_delete_confirm:{tag_id}:{filter_name}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"paypal_card:{tag_id}:{filter_name}")],
    ])


def paypal_restore_confirm_menu(tag_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, восстановить",
                callback_data=f"paypal_restore_confirm:{tag_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"paypal_card:{tag_id}:deleted",
            )
        ],
    ])


def paypal_restore_working_users_menu(
    tag_id: int,
    requests: list,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"👤 {getattr(req, '_display_username', req.user_id)}"
                    f" · {req.amount} €"
                ),
                callback_data=f"paypal_restore_working_ask:{tag_id}:{req.id}",
            )
        ]
        for req in requests
    ]
    rows.append([
        InlineKeyboardButton(
            text="⬅️ К карточке PayPal",
            callback_data=f"paypal_card:{tag_id}:deleted",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def paypal_restore_working_confirm_menu(
    tag_id: int,
    request_id: int | None = None,
) -> InlineKeyboardMarkup:
    suffix = f":{request_id}" if request_id is not None else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, вернуть в работу",
                callback_data=f"paypal_restore_working_confirm:{tag_id}{suffix}",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"paypal_card:{tag_id}:deleted",
            )
        ],
    ])


def working_dates_menu(rows: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"📅 {date_label} — {count}", callback_data=f"working_day:{date_label}")] for date_label, count in rows]
    buttons.append([InlineKeyboardButton(text="⬅️ Работа с PayPal", callback_data="paypal_payments_hub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def working_day_menu(date_label: str, requests: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=(
            ("⚠️ ДУБЛЬ · " if getattr(req, "_display_duplicate_count", 1) > 1 else "")
            + f"👤 {getattr(req, '_display_username', req.user_id)}"
            + f" · 💳 {getattr(req, '_display_tag', '—')}"
            + f" · 💶 {req.amount} €"
        ),
        callback_data=f"working_card:{req.id}:{date_label}",
    )] for req in requests[:50]]
    rows += [
        [InlineKeyboardButton(text="🔔 Уведомить: сбор через 30 минут", callback_data=f"collect_notify:{date_label}")],
        [InlineKeyboardButton(text="📥 Забрать PayPal в ожидании оплаты", callback_data=f"collect_take_ask:{date_label}")],
        [InlineKeyboardButton(text="🗑 Удалить все PayPal за день", callback_data=f"working_delete_day_ask:{date_label}")],
        [InlineKeyboardButton(text="📄 Экспорт Excel", callback_data=f"working_export:{date_label}")],
        [InlineKeyboardButton(text="⬅️ К датам", callback_data="working_dates")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)



def collect_take_confirm_menu(date_label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Забрать", callback_data=f"collect_take_confirm:{date_label}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"working_day:{date_label}")],
    ])

def working_card_menu(
    request_id: int,
    day: str,
    user_id: int,
    duplicate_count: int = 1,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✅ Деньги поступили", callback_data=f"working_money_received:{request_id}:{day}")],
        [InlineKeyboardButton(text="📣 Уведомить пользователя", callback_data=f"quick_notify_menu:{request_id}:{day}")],
    ]
    if duplicate_count > 1:
        rows.append([
            InlineKeyboardButton(
                text="❌ Отменить эту ошибочную выдачу",
                callback_data=f"duplicate_cancel_ask:{request_id}:{day}",
            )
        ])
    rows.extend([
        [InlineKeyboardButton(text="📥 Забрать в возвраты", callback_data=f"working_recall_ask:{request_id}:available:{day}")],
        [InlineKeyboardButton(text="🚫 Gestop", callback_data=f"working_recall_ask:{request_id}:gestoppt:{day}")],
        [InlineKeyboardButton(text="🗑 Удалить PayPal", callback_data=f"working_recall_ask:{request_id}:deleted:{day}")],
        [InlineKeyboardButton(text="👤 Открыть пользователя", url=f"tg://user?id={user_id}")],
        [InlineKeyboardButton(text="⬅️ К списку за день", callback_data=f"working_day:{day}")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def duplicate_cancel_confirm_menu(
    request_id: int,
    day: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, отменить эту выдачу",
                callback_data=f"duplicate_cancel_confirm:{request_id}:{day}",
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"working_card:{request_id}:{day}",
            )
        ],
    ])


def working_notify_confirm_menu(request_id: int, day: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить уведомление", callback_data=f"working_notify_confirm:{request_id}:{day}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"working_card:{request_id}:{day}")],
    ])


def collection_return_confirm_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, вернуть PayPal", callback_data=f"collect_return_confirm:{request_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"collect_return_cancel:{request_id}")],
    ])

def working_recall_confirm_menu(request_id: int, action: str, day: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"working_recall_confirm:{request_id}:{action}:{day}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"working_card:{request_id}:{day}")],
    ])


def working_delete_day_confirm_menu(day: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить все", callback_data=f"working_delete_day_confirm:{day}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"working_day:{day}")],
    ])


def working_search_results_menu(requests: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=(
            ("⚠️ ДУБЛЬ · " if getattr(req, "_display_duplicate_count", 1) > 1 else "")
            + f"👤 {getattr(req, '_display_username', req.user_id)}"
            + f" · 💳 {getattr(req, '_display_tag', '—')}"
            + f" · 💶 {req.amount} €"
        ),
        callback_data=f"working_card:{req.id}:search",
    )] for req in requests]
    rows.append([InlineKeyboardButton(text="🔍 Новый поиск", callback_data="working_search")])
    rows.append([InlineKeyboardButton(text="⬅️ К датам", callback_data="working_dates")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def collection_choice_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"user_paid:{request_id}")],
        [InlineKeyboardButton(text="🟢 Ещё нужен", callback_data=f"collect_keep:{request_id}")],
        [InlineKeyboardButton(text="↩️ Вернуть PayPal", callback_data=f"collect_return_ask:{request_id}")],
    ])


def working_search_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="working_dates")]
    ])


def work_control_menu(enabled: bool) -> InlineKeyboardMarkup:
    status = "🟢 Работа запущена" if enabled else "🔴 Работа остановлена"
    action = (
        InlineKeyboardButton(text="🛑 STOP WORK", callback_data="work_stop")
        if enabled else
        InlineKeyboardButton(text="🚀 START WORK", callback_data="work_start")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status, callback_data="work_control")],
        [action],
        [InlineKeyboardButton(text="✏️ Текст Start Work", callback_data="work_edit:start")],
        [InlineKeyboardButton(text="🖼 Картинка Start Work", callback_data="work_image:start")],
        [InlineKeyboardButton(text="✏️ Текст Stop Work", callback_data="work_edit:stop")],
        [InlineKeyboardButton(text="🖼 Картинка Stop Work", callback_data="work_image:stop")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")],
    ])


def work_edit_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="work_control")]
    ])


def work_image_edit_menu(kind: str, has_image: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_image:
        rows.append([InlineKeyboardButton(text="🗑 Удалить картинку", callback_data=f"work_image_delete:{kind}")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="work_control")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# v1.7.0 CRM keyboards
def global_search_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_home")]])


def global_search_results_menu(results: dict) -> InlineKeyboardMarkup:
    rows = []
    for user in results.get("users", [])[:10]:
        label = f"👤 @{user.username}" if user.username else f"👤 ID {user.id}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"crm_user:{user.id}")])
    for req in results.get("requests", [])[:10]:
        rows.append([InlineKeyboardButton(text=f"📄 Заявка #{req.id} · {req.amount} €", callback_data=f"payment_card:{req.id}:all:0")])
    for tag in results.get("tags", [])[:10]:
        rows.append([InlineKeyboardButton(text=f"💳 {tag.tag} · {tag.status}", callback_data=f"paypal_card:{tag.id}:all")])
    rows.append([InlineKeyboardButton(text="🔍 Новый поиск", callback_data="global_search")])
    rows.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def crm_user_menu(user_id: int, status: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💬 Написать", url=f"tg://user?id={user_id}")],
        [InlineKeyboardButton(text="💳 PayPal пользователя", callback_data=f"crm_user_paypals:{user_id}")],
    ]
    if status == "blocked":
        rows.append([InlineKeyboardButton(text="🔓 Разблокировать", callback_data=f"member_set:approved:{user_id}")])
    else:
        rows.append([InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"member_set:blocked:{user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def statistics_period_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сегодня", callback_data="stats_period:today"), InlineKeyboardButton(text="Вчера", callback_data="stats_period:yesterday")],
        [InlineKeyboardButton(text="7 дней", callback_data="stats_period:7d"), InlineKeyboardButton(text="30 дней", callback_data="stats_period:30d")],
        [InlineKeyboardButton(text="Всё время", callback_data="stats_period:all")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")],
    ])


def quick_notify_menu(request_id: int, day: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Заберу через 30 минут", callback_data=f"working_notify_ask:{request_id}:{day}")],
        [InlineKeyboardButton(text="⚠️ Только Friends & Family", callback_data=f"quick_notify:{request_id}:friends:{day}")],
        [InlineKeyboardButton(text="🔍 Платёж проверяется", callback_data=f"quick_notify:{request_id}:checking:{day}")],
        [InlineKeyboardButton(text="✅ Деньги поступили", callback_data=f"quick_notify:{request_id}:received:{day}")],
        [InlineKeyboardButton(text="✍️ Своё сообщение", callback_data=f"quick_notify_custom:{request_id}:{day}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"working_card:{request_id}:{day}")],
    ])


def content_menu(has_home_image: bool = False) -> InlineKeyboardMarkup:
    image_label = "🖼 Картинка приветствия ✅" if has_home_image else "🖼 Картинка приветствия"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Создать рассылку", callback_data="broadcast_start")],
        [InlineKeyboardButton(text="🏠 Текст приветствия", callback_data="content_edit:home")],
        [InlineKeyboardButton(text=image_label, callback_data="content_home_image")],
        [InlineKeyboardButton(text="💳 Текст Получить PayPal", callback_data="content_edit:paypal")],
        [InlineKeyboardButton(text="🆘 Текст поддержки", callback_data="content_edit:support")],
        [InlineKeyboardButton(text="♻️ Сбросить приветствие", callback_data="content_reset:home")],
        [InlineKeyboardButton(text="♻️ Сбросить Получить PayPal", callback_data="content_reset:paypal")],
        [InlineKeyboardButton(text="♻️ Сбросить поддержку", callback_data="content_reset:support")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")],
    ])


def content_cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="content_menu")]])


def content_image_menu(has_image: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_image:
        rows.append([InlineKeyboardButton(text="🗑 Удалить пользовательскую картинку", callback_data="content_home_image_delete")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="content_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==================== v2.2: БАЛАНС И РУЧНЫЕ ВЫПЛАТЫ ====================

def payout_method_menu(current: str) -> InlineKeyboardMarkup:
    crypto = "✅ CryptoBot" if current == "cryptobot" else "🤖 CryptoBot"
    rocket = "✅ xRocket" if current == "xrocket" else "🚀 xRocket"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=crypto, callback_data="set_payout_method:cryptobot")],
        [InlineKeyboardButton(text=rocket, callback_data="set_payout_method:xrocket")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="home")],
    ])



def wallet_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 ИЗМЕНИТЬ СПОСОБ ВЫПЛАТЫ", callback_data="payout_method")],
        [InlineKeyboardButton(text="📜 ИСТОРИЯ ВЫПЛАТ", callback_data="payout_history:0")],
        [InlineKeyboardButton(text="⬅️ ГЛАВНОЕ МЕНЮ", callback_data="home")],
    ])


def payout_method_wallet_menu(current: str) -> InlineKeyboardMarkup:
    crypto = "✅ CryptoBot" if current == "cryptobot" else "🤖 CryptoBot"
    rocket = "✅ xRocket" if current == "xrocket" else "🚀 xRocket"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=crypto, callback_data="set_payout_method:cryptobot")],
        [InlineKeyboardButton(text=rocket, callback_data="set_payout_method:xrocket")],
        [InlineKeyboardButton(text="⬅️ В КОШЕЛЁК", callback_data="wallet")],
    ])


def payout_history_menu(rows, offset: int, has_next: bool, page_size: int = 10) -> InlineKeyboardMarkup:
    buttons = []
    for payout in rows:
        provider = "🤖" if payout.provider == "cryptobot" else "🚀"
        date = getattr(payout, "_display_date", "—")
        buttons.append([InlineKeyboardButton(
            text=f"✅ {date} · {float(payout.total_amount):.2f} USDT · {provider}",
            callback_data=f"payout_history_card:{payout.id}",
        )])
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"payout_history:{max(0, offset-page_size)}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"payout_history:{offset+page_size}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="⬅️ В КОШЕЛЁК", callback_data="wallet")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payout_history_card_menu(payout_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎫 ПОЛУЧИТЬ ЧЕК ЕЩЁ РАЗ", callback_data=f"payout_receipt:{payout_id}")],
        [InlineKeyboardButton(text="⬅️ К ИСТОРИИ", callback_data="payout_history:0")],
    ])

def payouts_users_menu(rows, offset: int, has_next: bool, page_size: int = 10) -> InlineKeyboardMarkup:
    buttons = []
    for user, balance, entries in rows:
        name = f"@{user.username}" if user.username else str(user.id)
        buttons.append([InlineKeyboardButton(
            text=f"{name} · {float(balance):.2f} USDT · {entries} начисл.",
            callback_data=f"payout_user:{user.id}",
        )])
    nav=[]
    if offset > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"payouts_v22:{max(0, offset-page_size)}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"payouts_v22:{offset+page_size}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"payouts_v22:{offset}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="paypal_payments_hub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payout_user_menu(user_id: int, has_balance: bool) -> InlineKeyboardMarkup:
    rows=[]
    if has_balance:
        rows.append([InlineKeyboardButton(text="💸 ВЫПЛАТИТЬ ОБЩИЙ БАЛАНС", callback_data=f"manual_payout_start:{user_id}")])
    rows.append([InlineKeyboardButton(text="👤 Открыть пользователя", callback_data=f"member_card:{user_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ К выплатам", callback_data="payouts_v22:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manual_payout_cancel_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"payout_user:{user_id}")]
    ])
