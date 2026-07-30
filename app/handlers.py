from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message

from app.config import settings
from app.db import (
    add_paypal_tags,
    count_available_tags,
    create_request,
    delete_paypal_tag,
    find_paypal_tag,
    get_admin_stats,
    get_or_create_user,
    get_paypal_tags,
    get_recent_users,
    get_request,
    get_requests,
    get_user,
    get_user_requests,
    issue_paypal,
    mark_paid_by_user,
    set_request_status,
)
from app.keyboards import (
    admin_back,
    admin_check_menu,
    admin_main_menu,
    admin_paypal_menu,
    admin_request_menu,
    admin_requests_menu,
    amounts_menu,
    back_home,
    cancel_admin_input,
    main_menu,
    paid_button,
    request_list_menu,
)

router = Router()
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"

BANNERS = {
    "home": ASSETS_DIR / "main_menu.jpg",
    "paypal": ASSETS_DIR / "paypal.jpg",
    "requests": ASSETS_DIR / "requests.jpg",
    "profile": ASSETS_DIR / "profile.jpg",
    "links": ASSETS_DIR / "links.jpg",
    "support": ASSETS_DIR / "support.jpg",
    "issued": ASSETS_DIR / "paypal_issued.jpg",
}

STATUS_NAMES = {
    "waiting_issue": "⏳ ожидает выдачи",
    "paypal_issued": "💳 PayPal выдан",
    "waiting_check": "🔎 проверка оплаты",
    "paid": "✅ оплачено",
    "not_found": "⚠️ оплата не найдена",
    "rejected": "❌ отклонено",
}


class AdminInput(StatesGroup):
    add_tags = State()
    search_tag = State()
    delete_tag = State()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


async def render_screen(target: Message | CallbackQuery, banner: str, caption: str, reply_markup=None) -> Message:
    photo = FSInputFile(BANNERS[banner])
    if isinstance(target, Message):
        return await target.answer_photo(photo=photo, caption=caption, reply_markup=reply_markup)

    message = target.message
    if message.photo:
        try:
            return await message.edit_media(InputMediaPhoto(media=photo, caption=caption), reply_markup=reply_markup)
        except TelegramBadRequest:
            pass
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    return await target.bot.send_photo(message.chat.id, photo=photo, caption=caption, reply_markup=reply_markup)


async def edit_admin(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=reply_markup)


async def show_home(target: Message | CallbackQuery) -> None:
    await render_screen(target, "home", "<b>DT TEAM</b>\n\n👋 Добро пожаловать!\nВыберите нужный раздел:", main_menu())


async def show_admin_home(target: Message | CallbackQuery) -> None:
    stats = await get_admin_stats()
    text = (
        "<b>👨‍💼 Админ-панель DT TEAM</b>\n\n"
        f"💳 Свободных PayPal: <b>{stats['available']}</b>\n"
        f"📥 Ожидают выдачи: <b>{stats['waiting_issue']}</b>\n"
        f"🔎 Ожидают проверки: <b>{stats['waiting_check']}</b>\n\n"
        "Выберите раздел:"
    )
    if isinstance(target, Message):
        await target.answer(text, reply_markup=admin_main_menu())
    else:
        await edit_admin(target, text, admin_main_menu())


@router.message(CommandStart())
async def start(message: Message) -> None:
    await get_or_create_user(message.from_user.id, message.from_user.username)
    await show_home(message)


@router.callback_query(F.data == "home")
async def home(callback: CallbackQuery) -> None:
    await show_home(callback)
    await callback.answer()


@router.callback_query(F.data == "paypal_request")
async def paypal_request(callback: CallbackQuery) -> None:
    await render_screen(callback, "paypal", "<b>Запросить PayPal</b>\n\nВыберите нужную сумму:", amounts_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("amount:"))
async def choose_amount(callback: CallbackQuery) -> None:
    amount = int(callback.data.split(":")[1])
    req = await create_request(callback.from_user.id, amount)
    await render_screen(callback, "requests", f"✅ Заявка <b>#{req.id}</b> создана.\n\nСумма: <b>{amount} €</b>\nСтатус: ⏳ ожидает выдачи PayPal.", back_home())
    username = f"@{callback.from_user.username}" if callback.from_user.username else "без username"
    for admin_id in settings.admin_ids:
        await callback.bot.send_message(admin_id, f"🆕 <b>Новая заявка #{req.id}</b>\nПользователь: {username}\nID: <code>{callback.from_user.id}</code>\nСумма: <b>{amount} €</b>", reply_markup=admin_request_menu(req.id))
    await callback.answer("Заявка создана")


@router.callback_query(F.data == "my_requests")
async def my_requests(callback: CallbackQuery) -> None:
    requests = await get_user_requests(callback.from_user.id)
    if not requests:
        text = "<b>Мои заявки</b>\n\nУ вас пока нет заявок."
    else:
        lines = ["<b>Мои заявки</b>", ""]
        for req in requests:
            lines.append(f"#{req.id} · {req.amount} € · {STATUS_NAMES.get(req.status, req.status)}")
        text = "\n".join(lines)
    await render_screen(callback, "requests", text, back_home())
    await callback.answer()


@router.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery) -> None:
    requests = await get_user_requests(callback.from_user.id, limit=100)
    paid = sum(1 for request in requests if request.status == "paid")
    username = f"@{callback.from_user.username}" if callback.from_user.username else "не указан"
    await render_screen(callback, "profile", f"<b>Профиль</b>\n\n🆔 ID: <code>{callback.from_user.id}</code>\n👤 Username: {username}\n📋 Всего заявок: <b>{len(requests)}</b>\n✅ Успешных оплат: <b>{paid}</b>", back_home())
    await callback.answer()


@router.callback_query(F.data == "links")
async def links(callback: CallbackQuery) -> None:
    await render_screen(callback, "links", "<b>Наши ссылки</b>\n\n📢 Telegram-канал: @your_channel\n🌐 Сайт: your-site.com\n💬 Чат поддержки: @your_support", back_home())
    await callback.answer()


@router.callback_query(F.data == "support")
async def support(callback: CallbackQuery) -> None:
    await render_screen(callback, "support", "<b>Поддержка DT Team</b>\n\nПо вопросам заявок напишите администратору:\n@your_support", back_home())
    await callback.answer()


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if is_admin(message.from_user.id):
        await show_admin_home(message)


@router.callback_query(F.data == "admin:home")
async def admin_home(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    await state.clear()
    await show_admin_home(callback)
    await callback.answer()


@router.callback_query(F.data == "admin:paypal")
async def admin_paypal(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    available = await count_available_tags()
    await edit_admin(callback, f"<b>💳 Управление PayPal</b>\n\nСвободных тегов: <b>{available}</b>\nВыберите действие:", admin_paypal_menu())
    await callback.answer()


@router.callback_query(F.data == "admin:paypal:add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    await state.set_state(AdminInput.add_tags)
    await edit_admin(callback, "<b>➕ Добавление PayPal</b>\n\nОтправьте теги одним сообщением — каждый с новой строки или через пробел.\n\nПример:\n<code>@tag1\n@tag2\n@tag3</code>", cancel_admin_input())
    await callback.answer()


@router.message(AdminInput.add_tags)
async def admin_add_receive(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    raw_items = message.text.replace(",", " ").split()
    tags = []
    for raw in raw_items:
        tag = raw.strip()
        if tag:
            tags.append(tag if tag.startswith("@") else "@" + tag)
    if not tags:
        await message.answer("Теги не найдены. Попробуйте ещё раз.", reply_markup=cancel_admin_input())
        return
    added, duplicates = await add_paypal_tags(tags)
    await state.clear()
    await message.answer(f"✅ <b>PayPal добавлены</b>\n\nДобавлено: <b>{added}</b>\nДубликатов: <b>{duplicates}</b>", reply_markup=admin_paypal_menu())


@router.callback_query(F.data.in_({"admin:paypal:available", "admin:paypal:issued"}))
async def admin_paypal_list(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    status = "available" if callback.data.endswith("available") else "issued"
    tags = await get_paypal_tags(status=status, limit=30)
    title = "📋 Свободные PayPal" if status == "available" else "📦 Выданные PayPal"
    lines = [f"<b>{title}</b>", ""]
    if not tags:
        lines.append("Список пуст.")
    else:
        for tag in tags:
            if status == "available":
                lines.append(f"• <code>{tag.tag}</code>")
            else:
                lines.append(f"• <code>{tag.tag}</code> → <code>{tag.issued_to_user_id}</code>")
        if len(tags) == 30:
            lines.append("\nПоказаны последние 30 записей.")
    await edit_admin(callback, "\n".join(lines), admin_back("paypal"))
    await callback.answer()


@router.callback_query(F.data == "admin:paypal:stock")
async def admin_stock(callback: CallbackQuery) -> None:
    stats = await get_admin_stats()
    await edit_admin(callback, f"<b>📊 Остаток PayPal</b>\n\n🟢 Свободные: <b>{stats['available']}</b>\n📦 Выданные: <b>{stats['issued']}</b>\n📚 Всего: <b>{stats['available'] + stats['issued']}</b>", admin_back("paypal"))
    await callback.answer()


@router.callback_query(F.data == "admin:paypal:search")
async def admin_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminInput.search_tag)
    await edit_admin(callback, "<b>🔍 Поиск PayPal</b>\n\nОтправьте тег для поиска.", cancel_admin_input())
    await callback.answer()


@router.message(AdminInput.search_tag)
async def admin_search_receive(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    tag = await find_paypal_tag(message.text)
    await state.clear()
    if tag is None:
        text = "❌ PayPal не найден."
    else:
        issued = f"\nПользователь: <code>{tag.issued_to_user_id}</code>" if tag.issued_to_user_id else ""
        text = f"<b>🔍 PayPal найден</b>\n\nТег: <code>{tag.tag}</code>\nСтатус: <b>{tag.status}</b>{issued}"
    await message.answer(text, reply_markup=admin_paypal_menu())


@router.callback_query(F.data == "admin:paypal:delete")
async def admin_delete_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminInput.delete_tag)
    await edit_admin(callback, "<b>🗑 Удаление PayPal</b>\n\nОтправьте тег. Удалить можно только свободный PayPal.", cancel_admin_input())
    await callback.answer()


@router.message(AdminInput.delete_tag)
async def admin_delete_receive(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    ok, reason = await delete_paypal_tag(message.text)
    await state.clear()
    if ok:
        text = "✅ PayPal успешно удалён."
    elif reason == "issued":
        text = "⚠️ Выданный PayPal удалить нельзя."
    else:
        text = "❌ PayPal не найден."
    await message.answer(text, reply_markup=admin_paypal_menu())


@router.callback_query(F.data == "admin:cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_admin(callback, "<b>💳 Управление PayPal</b>\n\nДействие отменено.", admin_paypal_menu())
    await callback.answer("Отменено")


@router.callback_query(F.data == "admin:requests")
async def admin_requests(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    stats = await get_admin_stats()
    await edit_admin(callback, f"<b>📥 Заявки</b>\n\n⏳ Ожидают выдачи: <b>{stats['waiting_issue']}</b>\n🔎 Проверка оплаты: <b>{stats['waiting_check']}</b>\n✅ Оплачено: <b>{stats['paid']}</b>", admin_requests_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:requests:"))
async def admin_requests_list(callback: CallbackQuery) -> None:
    key = callback.data.rsplit(":", 1)[1]
    status = None if key == "all" else key
    requests = await get_requests(status=status, limit=20)
    lines = ["<b>📋 Список заявок</b>", ""]
    for req in requests:
        lines.append(f"#{req.id} · {req.amount} € · {STATUS_NAMES.get(req.status, req.status)}")
    if not requests:
        lines.append("Заявок нет.")
    await edit_admin(callback, "\n".join(lines), request_list_menu([r.id for r in requests]))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:request:"))
async def admin_request_card(callback: CallbackQuery) -> None:
    request_id = int(callback.data.rsplit(":", 1)[1])
    req = await get_request(request_id)
    if req is None:
        return await callback.answer("Заявка не найдена", show_alert=True)
    user = await get_user(req.user_id)
    username = f"@{user.username}" if user and user.username else "без username"
    text = f"<b>📄 Заявка #{req.id}</b>\n\n👤 {username}\n🆔 <code>{req.user_id}</code>\n💶 <b>{req.amount} €</b>\nСтатус: {STATUS_NAMES.get(req.status, req.status)}"
    await edit_admin(callback, text, admin_request_menu(req.id, req.status))
    await callback.answer()


@router.callback_query(F.data == "admin:users")
async def admin_users(callback: CallbackQuery) -> None:
    users = await get_recent_users(20)
    lines = ["<b>👥 Последние пользователи</b>", ""]
    for user in users:
        username = f"@{user.username}" if user.username else "без username"
        lines.append(f"• {username} · <code>{user.id}</code>")
    if not users:
        lines.append("Пользователей пока нет.")
    await edit_admin(callback, "\n".join(lines), admin_back("home"))
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery) -> None:
    stats = await get_admin_stats()
    text = (
        "<b>📊 Статистика</b>\n\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"🟢 Свободных PayPal: <b>{stats['available']}</b>\n"
        f"📦 Выданных PayPal: <b>{stats['issued']}</b>\n"
        f"⏳ Ожидают выдачи: <b>{stats['waiting_issue']}</b>\n"
        f"🔎 Ожидают проверки: <b>{stats['waiting_check']}</b>\n"
        f"✅ Всего оплачено: <b>{stats['paid']}</b>\n"
        f"🕐 Оплачено за 24 часа: <b>{stats['paid_24h']}</b>"
    )
    await edit_admin(callback, text, admin_back("home"))
    await callback.answer()


@router.callback_query(F.data.in_({"admin:broadcast", "admin:settings"}))
async def admin_coming_soon(callback: CallbackQuery) -> None:
    title = "📢 Рассылка" if callback.data.endswith("broadcast") else "⚙️ Настройки"
    await edit_admin(callback, f"<b>{title}</b>\n\nРаздел будет добавлен в следующем обновлении.", admin_back("home"))
    await callback.answer()


@router.message(Command("addtags"))
async def add_tags_legacy(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()[1:]
    tags = [(p if p.startswith("@") else "@" + p) for p in parts if p.strip()]
    if not tags:
        return await message.answer("После команды укажите PayPal-теги.")
    added, duplicates = await add_paypal_tags(tags)
    await message.answer(f"✅ Добавлено: {added}\n⚠️ Дубликатов: {duplicates}")


@router.callback_query(F.data.startswith("admin_issue:"))
async def admin_issue(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return await callback.answer("Нет доступа", show_alert=True)
    request_id = int(callback.data.split(":")[1])
    req, tag = await issue_paypal(request_id)
    if req is None:
        return await callback.answer("Заявка не найдена", show_alert=True)
    if tag is None:
        return await callback.answer("Нет свободных PayPal или заявка уже обработана", show_alert=True)
    await callback.bot.send_photo(req.user_id, photo=FSInputFile(BANNERS["issued"]), caption=f"✅ <b>PayPal выдан</b>\n\nЗаявка: <b>#{req.id}</b>\nСумма: <b>{req.amount} €</b>\nPayPal: <code>{tag.tag}</code>\n\nПосле оплаты нажмите кнопку ниже.", reply_markup=paid_button(req.id))
    await edit_admin(callback, callback.message.html_text + f"\n\n✅ Выдан: <code>{tag.tag}</code>", admin_back("requests"))
    await callback.answer("PayPal выдан")


@router.callback_query(F.data.startswith("user_paid:"))
async def user_paid(callback: CallbackQuery) -> None:
    request_id = int(callback.data.split(":")[1])
    if not await mark_paid_by_user(request_id, callback.from_user.id):
        return await callback.answer("Заявка уже обработана или недоступна", show_alert=True)
    req = await get_request(request_id)
    for admin_id in settings.admin_ids:
        await callback.bot.send_message(admin_id, f"💰 <b>Пользователь сообщил об оплате</b>\n\nЗаявка: #{request_id}\nПользователь ID: <code>{callback.from_user.id}</code>\nСумма: <b>{req.amount} €</b>", reply_markup=admin_check_menu(request_id))
    await render_screen(callback, "requests", "🔎 <b>Оплата отправлена на проверку</b>\n\nАдминистратор проверит поступление и подтвердит заявку.", back_home())
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm:"))
async def admin_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    request_id = int(callback.data.split(":")[1])
    req = await set_request_status(request_id, "paid")
    if req is None:
        return await callback.answer("Заявка не найдена", show_alert=True)
    await callback.bot.send_photo(req.user_id, photo=FSInputFile(BANNERS["issued"]), caption=f"✅ <b>Оплата подтверждена</b>\n\nЗаявка #{req.id} успешно оплачена.", reply_markup=back_home())
    await edit_admin(callback, callback.message.html_text + "\n\n✅ Подтверждено", admin_back("requests"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_not_found:"))
async def admin_not_found(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    request_id = int(callback.data.split(":")[1])
    req = await set_request_status(request_id, "not_found")
    if req is None:
        return await callback.answer("Заявка не найдена", show_alert=True)
    await callback.bot.send_photo(req.user_id, photo=FSInputFile(BANNERS["requests"]), caption=f"⚠️ Оплата по заявке #{req.id} пока не найдена. Свяжитесь с поддержкой.", reply_markup=back_home())
    await edit_admin(callback, callback.message.html_text + "\n\n⚠️ Оплата не найдена", admin_back("requests"))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    request_id = int(callback.data.split(":")[1])
    req = await set_request_status(request_id, "rejected")
    if req is None:
        return await callback.answer("Заявка не найдена", show_alert=True)
    await callback.bot.send_photo(req.user_id, photo=FSInputFile(BANNERS["requests"]), caption=f"❌ Заявка #{req.id} отклонена администратором.", reply_markup=back_home())
    await edit_admin(callback, callback.message.html_text + "\n\n❌ Отклонено", admin_back("requests"))
    await callback.answer()
