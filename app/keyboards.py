from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Запросить PayPal", callback_data="paypal_request"), InlineKeyboardButton(text="📋 Мои заявки", callback_data="my_requests")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), InlineKeyboardButton(text="🔗 Наши ссылки", callback_data="links")],
        [InlineKeyboardButton(text="🛟 Поддержка", callback_data="support")],
    ])


def amounts_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="50 €", callback_data="amount:50"), InlineKeyboardButton(text="100 €", callback_data="amount:100"), InlineKeyboardButton(text="150 €", callback_data="amount:150")],
        [InlineKeyboardButton(text="200 €", callback_data="amount:200"), InlineKeyboardButton(text="300 €", callback_data="amount:300")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")],
    ])


def admin_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 PayPal", callback_data="admin:paypal"), InlineKeyboardButton(text="📥 Заявки", callback_data="admin:requests")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users"), InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin:settings")],
    ])


def admin_paypal_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить PayPal", callback_data="admin:paypal:add")],
        [InlineKeyboardButton(text="📋 Свободные", callback_data="admin:paypal:available"), InlineKeyboardButton(text="📦 Выданные", callback_data="admin:paypal:issued")],
        [InlineKeyboardButton(text="🔍 Поиск", callback_data="admin:paypal:search"), InlineKeyboardButton(text="🗑 Удалить", callback_data="admin:paypal:delete")],
        [InlineKeyboardButton(text="📊 Остаток", callback_data="admin:paypal:stock")],
        [InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin:home")],
    ])


def admin_requests_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Ожидают выдачи", callback_data="admin:requests:waiting_issue")],
        [InlineKeyboardButton(text="🔎 Проверка оплаты", callback_data="admin:requests:waiting_check")],
        [InlineKeyboardButton(text="✅ Оплаченные", callback_data="admin:requests:paid"), InlineKeyboardButton(text="📋 Все", callback_data="admin:requests:all")],
        [InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin:home")],
    ])


def request_list_menu(request_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"Открыть заявку #{rid}", callback_data=f"admin:request:{rid}")] for rid in request_ids]
    rows.append([InlineKeyboardButton(text="⬅️ Заявки", callback_data="admin:requests")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_request_menu(request_id: int, status: str = "waiting_issue") -> InlineKeyboardMarkup:
    rows = []
    if status == "waiting_issue":
        rows.append([InlineKeyboardButton(text="✅ Выдать PayPal", callback_data=f"admin_issue:{request_id}"), InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject:{request_id}")])
    elif status == "waiting_check":
        rows.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm:{request_id}"), InlineKeyboardButton(text="❌ Не найдено", callback_data=f"admin_not_found:{request_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Заявки", callback_data="admin:requests")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_admin_input() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel")]])


def admin_back(section: str = "home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:{section}")]])


def paid_button(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"user_paid:{request_id}")], [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="home")]])


def admin_check_menu(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm:{request_id}"), InlineKeyboardButton(text="❌ Не найдено", callback_data=f"admin_not_found:{request_id}")]])


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Главное меню", callback_data="home")]])
