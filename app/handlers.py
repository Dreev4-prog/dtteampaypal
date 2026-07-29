from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message

from app.config import settings
from app.db import (
    add_paypal_tags,
    count_available_tags,
    create_request,
    get_or_create_user,
    get_request,
    get_user_requests,
    issue_paypal,
    mark_paid_by_user,
    set_request_status,
)
from app.keyboards import (
    admin_check_menu,
    admin_request_menu,
    amounts_menu,
    back_home,
    main_menu,
    paid_button,
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
    await render_screen(
        target,
        "home",
        "<b>DT TEAM</b>\n\n"
        "👋 Добро пожаловать!\n"
        "Выберите нужный раздел:",
        main_menu(),
    )


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
    await render_screen(
        callback,
        "support",
        "<b>Поддержка DT Team</b>\n\n"
        "По вопросам заявок напишите администратору:\n"
        "@your_support",
        back_home(),
    )
    await callback.answer()


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    available = await count_available_tags()
    await message.answer(
        "<b>Админ-панель</b>\n\n"
        f"Свободных PayPal: <b>{available}</b>\n\n"
        "Чтобы добавить теги, отправьте команду:\n"
        "<code>/addtags @tag1 @tag2 @tag3</code>"
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
