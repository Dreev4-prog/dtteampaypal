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
