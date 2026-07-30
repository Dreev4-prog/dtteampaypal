from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Запросить PayPal", callback_data="paypal_request"),
            InlineKeyboardButton(text="📋 Мои заявки", callback_data="my_requests"),
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


def admin_main_menu(pending_count: int = 0) -> InlineKeyboardMarkup:
    pending_label = f"👥 Участники · {pending_count} ждут" if pending_count else "👥 Участники"
    return InlineKeyboardMarkup(inline_keyboard=[
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


def amounts_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="50 €", callback_data="amount:50"),
            InlineKeyboardButton(text="100 €", callback_data="amount:100"),
            InlineKeyboardButton(text="150 €", callback_data="amount:150"),
        ],
        [
            InlineKeyboardButton(text="200 €", callback_data="amount:200"),
            InlineKeyboardButton(text="300 €", callback_data="amount:300"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")],
    ])


def admin_request_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выдать PayPal", callback_data=f"admin_issue:{request_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject:{request_id}"),
        ]
    ])


def paid_button(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"user_paid:{request_id}")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="home")],
    ])


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
