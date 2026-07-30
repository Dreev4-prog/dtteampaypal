from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Запросить PayPal", callback_data="paypal_request")],
        [
            InlineKeyboardButton(text="📂 Мои PayPal", callback_data="my_paypals"),
            InlineKeyboardButton(text="📈 Мои профиты", callback_data="my_profits"),
        ],
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="🔗 Наши ссылки", callback_data="links"),
        ],
        [InlineKeyboardButton(text="🛟 Поддержка", callback_data="support")],
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
    pending_label = f"👥 Участники · {pending_count} ждут" if pending_count else "👥 Участники"
    queue_label = f"📥 Очередь PayPal ({queue_count})"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Платежи", callback_data="payments_menu")],
        [InlineKeyboardButton(text="💳 База PayPal", callback_data="paypal_database"), InlineKeyboardButton(text="↩️ Возвраты", callback_data="returns_menu")],
        [InlineKeyboardButton(text="📊 Финансы", callback_data="finance_menu"), InlineKeyboardButton(text="⚙️ Проценты", callback_data="rates_menu")],
        [InlineKeyboardButton(text=queue_label, callback_data="paypal_queue:0")],
        [InlineKeyboardButton(text=pending_label, callback_data="members_menu")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_home")],
    ])


def members_menu(counts: dict[str, int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📋 Все ({counts.get('all', 0)})", callback_data="members_list:all:0")],
        [
            InlineKeyboardButton(text=f"🟢 Активные ({counts.get('approved', 0)})", callback_data="members_list:approved:0"),
            InlineKeyboardButton(text=f"🟡 Ожидают ({counts.get('pending', 0)})", callback_data="members_list:pending:0"),
        ],
        [
            InlineKeyboardButton(text=f"❌ Отклонённые ({counts.get('rejected', 0)})", callback_data="members_list:rejected:0"),
            InlineKeyboardButton(text=f"🚫 Заблокированные ({counts.get('blocked', 0)})", callback_data="members_list:blocked:0"),
        ],
        [InlineKeyboardButton(text="🔍 Поиск пользователя", callback_data="member_search")],
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
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"paypal_queue:{offset}")])
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
            InlineKeyboardButton(text="❌ Не найдено", callback_data=f"admin_not_found:{request_id}"),
        ]
    ])


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="home")]
    ])


def payments_menu(counts: dict[str, int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🟠 Проверить оплату ({counts.get('check', 0)})", callback_data="payments_list:check:0")],
        [InlineKeyboardButton(text=f"🟢 Нужно выплатить ({counts.get('payout', 0)})", callback_data="payments_list:payout:0")],
        [InlineKeyboardButton(text=f"✅ Выплаченные ({counts.get('paidout', 0)})", callback_data="payments_list:paidout:0")],
        [InlineKeyboardButton(text=f"🕓 Ожидают оплаты ({counts.get('waiting', 0)})", callback_data="payments_list:waiting:0")],
        [InlineKeyboardButton(text=f"🔴 Оплата не найдена ({counts.get('notfound', 0)})", callback_data="payments_list:notfound:0")],
        [InlineKeyboardButton(text=f"📋 Все ({counts.get('all', 0)})", callback_data="payments_list:all:0")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="payments_menu")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")],
    ])


def payments_list_menu(requests: list, filter_name: str, offset: int, page_size: int, has_next: bool) -> InlineKeyboardMarkup:
    status_icons = {
        "paypal_issued": "🕓", "waiting_check": "🟠", "payout_pending": "🟢",
        "paid_out": "✅", "not_found": "🔴",
    }
    rows = []
    for req in requests:
        icon = status_icons.get(req.status, "•")
        rows.append([InlineKeyboardButton(
            text=f"{icon} #{req.id} · {req.amount} € · ID {req.user_id}",
            callback_data=f"payment_card:{req.id}:{filter_name}:{offset}",
        )])
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"payments_list:{filter_name}:{max(0, offset-page_size)}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"payments_list:{filter_name}:{offset+page_size}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"payments_list:{filter_name}:{offset}")])
    rows.append([InlineKeyboardButton(text="⬅️ К платежам", callback_data="payments_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_card_menu(request_id: int, user_id: int, status: str, filter_name: str = "all", offset: int = 0) -> InlineKeyboardMarkup:
    rows = []
    if status == "waiting_check":
        rows.append([
            InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"admin_confirm:{request_id}"),
            InlineKeyboardButton(text="❌ Не найдено", callback_data=f"admin_not_found:{request_id}"),
        ])
    elif status == "payout_pending":
        rows.append([InlineKeyboardButton(text="💸 Я выплатил", callback_data=f"payout_confirm:{request_id}")])
        rows.append([InlineKeyboardButton(text="✏️ Изменить сумму", callback_data=f"payment_amount_edit:{request_id}")])
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


def finance_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="finance_menu")],
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
    rows = [[InlineKeyboardButton(text=f"↩️ #{item.id} · заявка #{item.request_id}", callback_data=f"return_card:{item.id}")] for item in items]
    rows += [[InlineKeyboardButton(text="🔄 Обновить", callback_data="returns_menu")], [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def return_card_menu(return_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Проверил PayPal", callback_data=f"return_checked:{return_id}")],
        [InlineKeyboardButton(text="💬 Написать пользователю", url=f"tg://user?id={user_id}")],
        [InlineKeyboardButton(text="⬅️ К возвратам", callback_data="returns_menu")],
    ])


def return_checked_menu(return_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Вернуть в базу", callback_data=f"return_release:{return_id}")],
        [InlineKeyboardButton(text="🚫 Gestop", callback_data=f"return_gestoppt:{return_id}")],
        [InlineKeyboardButton(text="🗑 Удалить PayPal", callback_data=f"return_delete:{return_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"return_card:{return_id}")],
    ])


def paypal_database_menu(counts: dict[str, int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🟢 Свободные ({counts.get('available', 0)})", callback_data="paypal_db_list:available:0")],
        [InlineKeyboardButton(text=f"👤 В работе ({counts.get('issued', 0)})", callback_data="working_dates")],
        [InlineKeyboardButton(text=f"↩️ Возвраты ({counts.get('return_pending', 0)})", callback_data="returns_menu")],
        [InlineKeyboardButton(text=f"🚫 Gestop ({counts.get('gestoppt', 0)})", callback_data="paypal_db_list:gestoppt:0")],
        [InlineKeyboardButton(text=f"📋 Все ({counts.get('all', 0)})", callback_data="paypal_db_list:all:0")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_home")],
    ])


def paypal_list_menu(tags: list, filter_name: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"💳 {tag.tag}", callback_data=f"paypal_card:{tag.id}:{filter_name}")] for tag in tags]
    rows.append([InlineKeyboardButton(text="⬅️ База PayPal", callback_data="paypal_database")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def paypal_card_admin_menu(tag_id: int, filter_name: str, status: str) -> InlineKeyboardMarkup:
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


def working_dates_menu(rows: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"📅 {date_label} — {count}", callback_data=f"working_day:{date_label}")] for date_label, count in rows]
    buttons.append([InlineKeyboardButton(text="⬅️ База PayPal", callback_data="paypal_database")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def working_day_menu(date_label: str, requests: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"#{req.id} · {req.amount} € · ID {req.user_id}", callback_data=f"payment_card:{req.id}:waiting:0")] for req in requests[:20]]
    rows += [
        [InlineKeyboardButton(text="🔔 Уведомить: сбор через 30 минут", callback_data=f"collect_notify:{date_label}")],
        [InlineKeyboardButton(text="📥 Забрать неподтверждённые", callback_data=f"collect_take:{date_label}")],
        [InlineKeyboardButton(text="⬅️ К датам", callback_data="working_dates")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def collection_choice_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ещё нужен", callback_data=f"collect_keep:{request_id}")],
        [InlineKeyboardButton(text="↩️ Вернуть", callback_data=f"return_start:{request_id}")],
    ])
