from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message

from app.config import settings
from app.db import (
    add_paypal_tags,
    count_available_tags,
    count_user_paypals,
    create_request,
    get_or_create_user,
    get_user,
    get_request,
    get_user_requests,
    get_user_counts,
    list_users,
    search_users,
    issue_paypal,
    mark_paid_by_user,
    set_request_status,
    set_user_access_status,
    submit_membership_application,
)
from app.keyboards import (
    admin_check_menu,
    admin_main_menu,
    admin_request_menu,
    amounts_menu,
    back_home,
    main_menu,
    membership_admin_menu,
    membership_apply_menu,
    member_card_menu,
    members_list_menu,
    members_menu,
    cancel_search_menu,
    paid_button,
)

router = Router()


class MemberSearch(StatesGroup):
    query = State()
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


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


async def render_screen(
    target: Message | CallbackQuery,
    banner: str,
    caption: str,
    reply_markup=None,
) -> Message:
    """Показывает экран с баннером. При переходах заменяет текущее сообщение."""
    photo = FSInputFile(BANNERS[banner])

    if isinstance(target, Message):
        return await target.answer_photo(photo=photo, caption=caption, reply_markup=reply_markup)

    message = target.message
    if message.photo:
        media = InputMediaPhoto(media=photo, caption=caption)
        try:
            return await message.edit_media(media=media, reply_markup=reply_markup)
        except TelegramBadRequest:
            pass

    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    return await target.bot.send_photo(
        chat_id=message.chat.id,
        photo=photo,
        caption=caption,
        reply_markup=reply_markup,
    )


async def show_home(target: Message | CallbackQuery) -> None:
    user_id = target.from_user.id
    user = await get_user(user_id)

    if user is None:
        username = target.from_user.username
        user = await get_or_create_user(user_id, username, target.from_user.full_name)

    if user.status == "blocked":
        await render_screen(
            target,
            "home",
            "🚫 <b>Доступ заблокирован</b>\n\n"
            "Вы не можете пользоваться сервисом.",
        )
        return

    if user.status == "rejected":
        await render_screen(
            target,
            "home",
            "❌ <b>Заявка отклонена</b>\n\n"
            "Доступ к сервису не предоставлен. По вопросам обратитесь в поддержку.",
        )
        return

    if user.status != "approved":
        if user.applied_at is None:
            caption = (
                "<b>DT TEAM</b>\n\n"
                "🔐 Это закрытый сервис.\n"
                "Для доступа к PayPal необходимо подать заявку на вступление."
            )
            markup = membership_apply_menu()
        else:
            caption = (
                "⏳ <b>Заявка отправлена</b>\n\n"
                "Ожидайте решения администратора. После одобрения вам откроется главное меню."
            )
            markup = None
        await render_screen(target, "home", caption, markup)
        return

    await render_screen(
        target,
        "home",
        "<b>DT TEAM</b>\n\n"
        "👋 Добро пожаловать!\n"
        "Выберите нужный раздел:",
        main_menu(),
    )


async def has_access(callback: CallbackQuery) -> bool:
    user = await get_user(callback.from_user.id)
    if user is not None and user.status == "approved":
        return True
    await show_home(callback)
    await callback.answer("Сначала дождитесь одобрения", show_alert=True)
    return False


@router.message(CommandStart())
async def start(message: Message) -> None:
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await show_home(message)


@router.callback_query(F.data == "home")
async def home(callback: CallbackQuery) -> None:
    await show_home(callback)
    await callback.answer()


@router.callback_query(F.data == "membership_apply")
async def membership_apply(callback: CallbackQuery) -> None:
    user = await submit_membership_application(callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    if user.status == "approved":
        await show_home(callback)
        await callback.answer("Доступ уже одобрен")
        return
    if user.status == "blocked":
        await show_home(callback)
        await callback.answer("Доступ заблокирован", show_alert=True)
        return

    username = f"@{callback.from_user.username}" if callback.from_user.username else "не указан"
    full_name = callback.from_user.full_name or "не указано"
    for admin_id in settings.admin_ids:
        await callback.bot.send_message(
            admin_id,
            "📥 <b>Новая заявка на вступление</b>\n\n"
            f"👤 Имя: {full_name}\n"
            f"📛 Username: {username}\n"
            f"🆔 ID: <code>{callback.from_user.id}</code>",
            reply_markup=membership_admin_menu(callback.from_user.id),
        )

    await show_home(callback)
    await callback.answer("Заявка отправлена")


@router.callback_query(F.data.startswith("membership_approve:"))
async def membership_approve(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    user_id = int(callback.data.split(":", 1)[1])
    user = await set_user_access_status(user_id, "approved", callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    await callback.bot.send_photo(
        user_id,
        photo=FSInputFile(BANNERS["home"]),
        caption=(
            "🎉 <b>Ваша заявка одобрена!</b>\n\n"
            "Добро пожаловать в DT Team. Теперь вам доступны все функции сервиса."
        ),
        reply_markup=main_menu(),
    )
    await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>Одобрено</b>")
    await callback.answer("Пользователь одобрен")


@router.callback_query(F.data.startswith("membership_reject:"))
async def membership_reject(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    user_id = int(callback.data.split(":", 1)[1])
    user = await set_user_access_status(user_id, "rejected", callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    await callback.bot.send_photo(
        user_id,
        photo=FSInputFile(BANNERS["home"]),
        caption=(
            "❌ <b>Ваша заявка отклонена</b>\n\n"
            "По вопросам обратитесь в поддержку."
        ),
    )
    await callback.message.edit_text(callback.message.html_text + "\n\n❌ <b>Отклонено</b>")
    await callback.answer("Заявка отклонена")


@router.callback_query(F.data.startswith("membership_block:"))
async def membership_block(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    user_id = int(callback.data.split(":", 1)[1])
    user = await set_user_access_status(user_id, "blocked", callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    await callback.bot.send_message(user_id, "🚫 Ваш доступ к сервису заблокирован.")
    await callback.message.edit_text(callback.message.html_text + "\n\n🚫 <b>Заблокирован</b>")
    await callback.answer("Пользователь заблокирован")


@router.callback_query(F.data == "paypal_request")
async def paypal_request(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    await render_screen(
        callback,
        "paypal",
        "<b>Запросить PayPal</b>\n\n"
        "Выберите сумму, на которую хотите запросить PayPal:",
        amounts_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("amount:"))
async def choose_amount(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    amount = int(callback.data.split(":")[1])
    req = await create_request(callback.from_user.id, amount)

    await render_screen(
        callback,
        "requests",
        f"✅ Заявка <b>#{req.id}</b> создана.\n\n"
        f"Сумма: <b>{amount} €</b>\n"
        "Статус: ⏳ ожидает выдачи PayPal.",
        back_home(),
    )

    username = f"@{callback.from_user.username}" if callback.from_user.username else "без username"
    for admin_id in settings.admin_ids:
        await callback.bot.send_message(
            admin_id,
            f"🆕 <b>Новая заявка #{req.id}</b>\n"
            f"Пользователь: {username}\n"
            f"ID: <code>{callback.from_user.id}</code>\n"
            f"Сумма: <b>{amount} €</b>",
            reply_markup=admin_request_menu(req.id),
        )
    await callback.answer("Заявка создана")


@router.callback_query(F.data == "my_requests")
async def my_requests(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    requests = await get_user_requests(callback.from_user.id)
    if not requests:
        text = "<b>Мои заявки</b>\n\nУ вас пока нет заявок."
    else:
        status_names = {
            "waiting_issue": "⏳ ожидает выдачи",
            "paypal_issued": "💳 PayPal выдан",
            "waiting_check": "🔎 ожидает проверки",
            "paid": "✅ оплачено",
            "rejected": "❌ отклонено",
            "not_found": "⚠️ оплата не найдена",
        }
        lines = ["<b>Мои заявки</b>", ""]
        for req in requests:
            lines.append(f"#{req.id} · {req.amount} € · {status_names.get(req.status, req.status)}")
        text = "\n".join(lines)

    await render_screen(callback, "requests", text, back_home())
    await callback.answer()


@router.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    requests = await get_user_requests(callback.from_user.id)
    paid = sum(1 for request in requests if request.status == "paid")
    username = f"@{callback.from_user.username}" if callback.from_user.username else "не указан"

    await render_screen(
        callback,
        "profile",
        "<b>Профиль</b>\n\n"
        f"🆔 ID: <code>{callback.from_user.id}</code>\n"
        f"👤 Username: {username}\n"
        f"📋 Всего заявок: <b>{len(requests)}</b>\n"
        f"✅ Успешных оплат: <b>{paid}</b>",
        back_home(),
    )
    await callback.answer()


@router.callback_query(F.data == "links")
async def links(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    await render_screen(
        callback,
        "links",
        "<b>Наши ссылки</b>\n\n"
        "📢 Telegram-канал: @your_channel\n"
        "🌐 Сайт: your-site.com\n"
        "💬 Чат поддержки: @your_support",
        back_home(),
    )
    await callback.answer()


@router.callback_query(F.data == "support")
async def support(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    await render_screen(
        callback,
        "support",
        "<b>Поддержка DT Team</b>\n\n"
        "По вопросам заявок напишите администратору:\n"
        "@your_support",
        back_home(),
    )
    await callback.answer()


async def show_admin_home(target: Message | CallbackQuery) -> None:
    available = await count_available_tags()
    counts = await get_user_counts()
    text = (
        "👨‍💼 <b>Админ-панель</b>\n\n"
        f"👥 Всего пользователей: <b>{counts['all']}</b>\n"
        f"🟡 Ожидают решения: <b>{counts['pending']}</b>\n"
        f"💳 Свободных PayPal: <b>{available}</b>\n\n"
        "Добавление тегов пока доступно командой:\n"
        "<code>/addtags @tag1 @tag2 @tag3</code>"
    )
    markup = admin_main_menu(counts["pending"])
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
    else:
        await target.message.edit_text(text, reply_markup=markup)


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await show_admin_home(message)


@router.callback_query(F.data == "admin_home")
async def admin_home(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await show_admin_home(callback)
    await callback.answer()


@router.callback_query(F.data == "members_menu")
async def members_panel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    counts = await get_user_counts()
    await callback.message.edit_text(
        "👥 <b>Участники</b>\n\n"
        "Выберите список или найдите пользователя по ID, username либо имени.",
        reply_markup=members_menu(counts),
    )
    await callback.answer()


STATUS_TITLES = {
    "all": "Все участники",
    "approved": "Активные участники",
    "pending": "Ожидают решения",
    "rejected": "Отклонённые",
    "blocked": "Заблокированные",
}


@router.callback_query(F.data.startswith("members_list:"))
async def members_list_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, status, offset_raw = callback.data.split(":", 2)
    if status not in STATUS_TITLES:
        await callback.answer("Неизвестный фильтр", show_alert=True)
        return
    offset = max(0, int(offset_raw))
    page_size = 10
    users, has_next = await list_users(status=status, offset=offset, limit=page_size)
    page = offset // page_size + 1
    text = f"👥 <b>{STATUS_TITLES[status]}</b>\nСтраница: <b>{page}</b>\n\n"
    if not users:
        text += "Пользователи не найдены."
    else:
        text += "Нажмите на пользователя, чтобы открыть карточку."
    await callback.message.edit_text(
        text,
        reply_markup=members_list_menu(users, status, offset, page_size, has_next),
    )
    await callback.answer()


def format_dt(value) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


async def show_member_card(callback: CallbackQuery, user_id: int) -> None:
    user = await get_user(user_id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    issued_count = await count_user_paypals(user_id)
    status_names = {
        "pending": "🟡 Ожидает",
        "approved": "🟢 Активен",
        "rejected": "❌ Отклонён",
        "blocked": "🚫 Заблокирован",
    }
    username = f"@{user.username}" if user.username else "не указан"
    name = user.full_name or "не указано"
    approver = f"<code>{user.decided_by}</code>" if user.decided_by else "—"
    text = (
        "👤 <b>Карточка участника</b>\n\n"
        f"Имя: <b>{name}</b>\n"
        f"Username: {username}\n"
        f"Telegram ID: <code>{user.id}</code>\n"
        f"Статус: <b>{status_names.get(user.status, user.status)}</b>\n\n"
        f"Регистрация: {format_dt(user.created_at)}\n"
        f"Заявка подана: {format_dt(user.applied_at)}\n"
        f"Решение принято: {format_dt(user.decided_at)}\n"
        f"Администратор: {approver}\n\n"
        f"Выдано PayPal: <b>{issued_count}</b>"
    )
    await callback.message.edit_text(text, reply_markup=member_card_menu(user.id, user.status))


@router.callback_query(F.data.startswith("member_card:"))
async def member_card_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    user_id = int(callback.data.split(":", 1)[1])
    await show_member_card(callback, user_id)
    await callback.answer()


@router.callback_query(F.data.startswith("member_set:"))
async def member_set_status_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, status, user_id_raw = callback.data.split(":", 2)
    user_id = int(user_id_raw)
    user = await set_user_access_status(user_id, status, callback.from_user.id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    notifications = {
        "approved": ("🎉 <b>Доступ одобрен</b>\n\nДобро пожаловать в DT Team!", main_menu()),
        "pending": ("↩️ Ваш доступ временно отозван. Ожидайте решения администратора.", None),
        "rejected": ("❌ Ваша заявка отклонена. По вопросам обратитесь в поддержку.", None),
        "blocked": ("🚫 Ваш доступ к сервису заблокирован.", None),
    }
    text, markup = notifications[status]
    try:
        await callback.bot.send_message(user_id, text, reply_markup=markup)
    except Exception:
        pass
    await show_member_card(callback, user_id)
    await callback.answer("Статус обновлён")


@router.callback_query(F.data == "member_search")
async def member_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(MemberSearch.query)
    await callback.message.edit_text(
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Отправьте Telegram ID, @username или имя пользователя.",
        reply_markup=cancel_search_menu(),
    )
    await callback.answer()


@router.message(MemberSearch.query)
async def member_search_result(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введите ID, username или имя.", reply_markup=cancel_search_menu())
        return
    users = await search_users(query)
    await state.clear()
    if not users:
        await message.answer(
            "🔍 Пользователь не найден.",
            reply_markup=members_menu(await get_user_counts()),
        )
        return
    await message.answer(
        f"🔍 <b>Результаты поиска</b>\n\nНайдено: <b>{len(users)}</b>",
        reply_markup=members_list_menu(users, "all", 0, 10, False),
    )


@router.message(Command("addtags"))
async def add_tags_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()[1:]
    tags = []
    for raw in parts:
        tag = raw.strip()
        if not tag:
            continue
        if not tag.startswith("@"):
            tag = "@" + tag
        tags.append(tag)
    if not tags:
        await message.answer("После команды укажите PayPal-теги.")
        return
    added, duplicates = await add_paypal_tags(tags)
    await message.answer(f"✅ Добавлено: {added}\n⚠️ Дубликатов: {duplicates}")


@router.callback_query(F.data.startswith("admin_issue:"))
async def admin_issue(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    request_id = int(callback.data.split(":")[1])
    req, tag = await issue_paypal(request_id)
    if req is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if tag is None:
        await callback.answer("Нет свободных PayPal или заявка уже обработана", show_alert=True)
        return

    await callback.bot.send_photo(
        req.user_id,
        photo=FSInputFile(BANNERS["issued"]),
        caption=(
            "✅ <b>PayPal выдан</b>\n\n"
            f"Заявка: <b>#{req.id}</b>\n"
            f"Сумма: <b>{req.amount} €</b>\n"
            f"PayPal: <code>{tag.tag}</code>\n\n"
            "После оплаты нажмите кнопку ниже."
        ),
        reply_markup=paid_button(req.id),
    )
    await callback.message.edit_text(
        callback.message.html_text + f"\n\n✅ Выдан: <code>{tag.tag}</code>"
    )
    await callback.answer("PayPal выдан")


@router.callback_query(F.data.startswith("user_paid:"))
async def user_paid(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    request_id = int(callback.data.split(":")[1])
    ok = await mark_paid_by_user(request_id, callback.from_user.id)
    if not ok:
        await callback.answer("Заявка уже обработана или недоступна", show_alert=True)
        return

    req = await get_request(request_id)
    for admin_id in settings.admin_ids:
        await callback.bot.send_message(
            admin_id,
            "💰 <b>Пользователь сообщил об оплате</b>\n\n"
            f"Заявка: #{request_id}\n"
            f"Пользователь ID: <code>{callback.from_user.id}</code>\n"
            f"Сумма: <b>{req.amount} €</b>",
            reply_markup=admin_check_menu(request_id),
        )

    await render_screen(
        callback,
        "requests",
        "🔎 <b>Оплата отправлена на проверку</b>\n\n"
        "Администратор проверит поступление и подтвердит заявку.",
        back_home(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm:"))
async def admin_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    request_id = int(callback.data.split(":")[1])
    req = await set_request_status(request_id, "paid")
    if req is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await callback.bot.send_photo(
        req.user_id,
        photo=FSInputFile(BANNERS["issued"]),
        caption=f"✅ <b>Оплата подтверждена</b>\n\nЗаявка #{req.id} успешно оплачена.",
        reply_markup=back_home(),
    )
    await callback.message.edit_text(callback.message.html_text + "\n\n✅ Подтверждено")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_not_found:"))
async def admin_not_found(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    request_id = int(callback.data.split(":")[1])
    req = await set_request_status(request_id, "not_found")
    if req is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await callback.bot.send_photo(
        req.user_id,
        photo=FSInputFile(BANNERS["requests"]),
        caption=f"⚠️ Оплата по заявке #{req.id} пока не найдена. Свяжитесь с поддержкой.",
        reply_markup=back_home(),
    )
    await callback.message.edit_text(callback.message.html_text + "\n\n⚠️ Оплата не найдена")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    request_id = int(callback.data.split(":")[1])
    req = await set_request_status(request_id, "rejected")
    if req is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await callback.bot.send_photo(
        req.user_id,
        photo=FSInputFile(BANNERS["requests"]),
        caption=f"❌ Заявка #{req.id} отклонена администратором.",
        reply_markup=back_home(),
    )
    await callback.message.edit_text(callback.message.html_text + "\n\n❌ Отклонено")
    await callback.answer()
