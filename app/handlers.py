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
    count_active_requests,
    count_waiting_requests,
    count_user_paypals,
    create_request,
    get_or_create_user,
    get_user,
    get_request,
    get_user_requests,
    get_user_requests_by_statuses,
    get_user_profit_summary,
    get_user_counts,
    list_users,
    list_waiting_requests,
    search_users,
    issue_paypal,
    mark_paid_by_user,
    set_request_status,
    set_user_access_status,
    submit_membership_application,
    get_paypal_tag,
    get_payment_counts,
    list_payment_requests,
    confirm_payment,
    mark_payment_not_found,
    return_to_payment_check,
    mark_payout_done,
    update_request_amount,
    get_rate_for_amount,
    list_rate_rules,
    upsert_rate_rule,
    delete_rate_rule,
    get_finance_summary,
    create_paypal_return, list_paypal_returns, get_paypal_return, resolve_paypal_return,
    get_paypal_database_counts, list_paypal_tags, set_paypal_tag_status, delete_free_paypal_tag,
    get_working_dates, get_working_requests_by_date, mark_collection_notified,
    confirm_paypal_keep, list_unconfirmed_collection,
)
from app.keyboards import (
    admin_check_menu,
    admin_main_menu,
    admin_request_menu,
    request_cancel_menu,
    paypal_queue_menu,
    queue_request_menu,
    back_home,
    main_menu,
    membership_admin_menu,
    membership_apply_menu,
    member_card_menu,
    members_list_menu,
    members_menu,
    cancel_search_menu,
    paid_button,
    payments_menu,
    payments_list_menu,
    payment_card_menu,
    payout_confirmation_menu,
    user_amount_confirmation_menu,
    admin_amount_confirmation_menu,
    rates_menu,
    finance_menu,
    rate_cancel_menu,
    my_paypals_menu,
    my_paypals_back_menu,
    paid_or_return_menu, return_reasons_menu, return_confirm_menu, returns_menu,
    return_card_menu, return_checked_menu, paypal_database_menu, paypal_list_menu,
    paypal_card_admin_menu, paypal_delete_confirm_menu, working_dates_menu, working_day_menu, collection_choice_menu,
)

router = Router()


class MemberSearch(StatesGroup):
    query = State()


class PaypalRequestForm(StatesGroup):
    amount = State()
    screenshot = State()


class PaymentAmountForm(StatesGroup):
    user_amount = State()
    admin_amount = State()
    admin_edit_amount = State()


class RateForm(StatesGroup):
    add_rule = State()
    edit_rule = State()


class ReturnForm(StatesGroup):
    custom_reason = State()
    reject_reason = State()
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
async def paypal_request(callback: CallbackQuery, state: FSMContext) -> None:
    if not await has_access(callback):
        return
    active = await count_active_requests(callback.from_user.id)
    if active >= 2:
        await callback.answer(
            "У вас уже есть 2 активные заявки. Дождитесь обработки одной из них.",
            show_alert=True,
        )
        return
    await state.clear()
    await state.set_state(PaypalRequestForm.amount)
    await render_screen(
        callback,
        "paypal",
        "<b>Новая заявка PayPal</b>\n\n"
        "Введите необходимую сумму в евро одним числом.\n"
        "Например: <code>75</code>",
        request_cancel_menu(),
    )
    await callback.answer()


@router.message(PaypalRequestForm.amount)
async def paypal_amount_input(message: Message, state: FSMContext) -> None:
    user = await get_user(message.from_user.id)
    if user is None or user.status != "approved":
        await state.clear()
        return
    raw = (message.text or "").strip().replace("€", "").replace(" ", "")
    if not raw.isdigit():
        await message.answer("Введите сумму целым числом, например: <code>75</code>", reply_markup=request_cancel_menu())
        return
    amount = int(raw)
    if amount < 1 or amount > 100000:
        await message.answer("Введите сумму от 1 до 100000 €.", reply_markup=request_cancel_menu())
        return
    active = await count_active_requests(message.from_user.id)
    if active >= 2:
        await state.clear()
        await message.answer("❌ У вас уже есть 2 активные заявки. Дождитесь обработки одной из них.", reply_markup=back_home())
        return
    await state.update_data(amount=amount)
    await state.set_state(PaypalRequestForm.screenshot)
    await message.answer(
        "📷 <b>Подтверждение</b>\n\n"
        "Пришлите скриншот, подтверждающий, что вы готовы оплатить через "
        "PayPal Friends & Family.\n\n"
        "Нужно отправить именно фотографию или изображение.",
        reply_markup=request_cancel_menu(),
    )


@router.message(PaypalRequestForm.screenshot, F.photo)
async def paypal_screenshot_input(message: Message, state: FSMContext) -> None:
    user = await get_user(message.from_user.id)
    if user is None or user.status != "approved":
        await state.clear()
        return
    active = await count_active_requests(message.from_user.id)
    if active >= 2:
        await state.clear()
        await message.answer("❌ У вас уже есть 2 активные заявки.", reply_markup=back_home())
        return
    data = await state.get_data()
    amount = int(data["amount"])
    screenshot_file_id = message.photo[-1].file_id
    req = await create_request(message.from_user.id, amount, screenshot_file_id)
    await state.clear()

    await message.answer(
        f"✅ <b>Заявка #{req.id} принята</b>\n\n"
        f"Сумма: <b>{amount} €</b>\n"
        "Скриншот получен. Ожидайте выдачи PayPal.",
        reply_markup=back_home(),
    )

    username = f"@{message.from_user.username}" if message.from_user.username else "без username"
    caption = (
        f"📥 <b>Новая заявка PayPal #{req.id}</b>\n\n"
        f"👤 {message.from_user.full_name}\n"
        f"Username: {username}\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"💶 Сумма: <b>{amount} €</b>\n"
        "📷 Подтверждение Friends & Family приложено."
    )
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_photo(
                admin_id,
                photo=screenshot_file_id,
                caption=caption,
                reply_markup=queue_request_menu(req.id, req.user_id),
            )
        except Exception:
            pass


@router.message(PaypalRequestForm.screenshot)
async def paypal_screenshot_invalid(message: Message) -> None:
    await message.answer(
        "Пришлите скриншот как фотографию/изображение. Документ или текст не подойдут.",
        reply_markup=request_cancel_menu(),
    )


@router.callback_query(F.data == "request_cancel")
async def request_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_home(callback)
    await callback.answer("Заявка отменена")


MY_PAYPAL_GROUPS = {
    "requests": (("waiting_issue",), "📨 Запросы на PayPal"),
    "waiting": (("paypal_issued",), "💳 Ожидают оплаты"),
    "check": (("waiting_check",), "🟠 На проверке"),
    "payout": (("payout_pending", "paid"), "🟢 Ожидают выплату"),
    "paid": (("paid_out",), "✅ Выплаченные"),
    "closed": (("not_found", "rejected"), "❌ Не оплаченные/отклонённые"),
}


def _user_request_line(req, paypal_tag: str | None = None) -> str:
    tag_line = f"\n💳 PayPal: <code>{paypal_tag}</code>" if paypal_tag else ""
    payout_line = ""
    if req.payout_amount is not None:
        payout_line = f"\n💸 К выплате: <b>{float(req.payout_amount):.2f} €</b>"
    return (
        f"<b>Заявка #{req.id}</b>\n"
        f"💶 Сумма: <b>{req.amount} €</b>"
        f"{tag_line}{payout_line}\n"
        f"🕒 Обновлено: {format_dt(req.updated_at)}"
    )


@router.callback_query(F.data.in_({"my_paypals", "my_requests"}))
async def my_paypals(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return

    counts: dict[str, int] = {}
    for key, (statuses, _) in MY_PAYPAL_GROUPS.items():
        counts[key] = len(await get_user_requests_by_statuses(callback.from_user.id, statuses, limit=1000))

    summary = await get_user_profit_summary(callback.from_user.id)
    text = (
        "<b>💳 Мои PayPal</b>\n\n"
        "Здесь отображаются все ваши заявки по этапам.\n\n"
        f"📨 Запросов, ожидающих выдачи: <b>{counts['requests']}</b> из 2\n"
        f"💰 Сейчас ожидает выплаты: <b>{summary['pending']:.2f} €</b>\n\n"
        "Лимит в 2 заявки учитывает только запросы, по которым PayPal ещё не выдан."
    )
    await render_screen(callback, "requests", text, my_paypals_menu(counts))
    await callback.answer()


@router.callback_query(F.data.startswith("my_paypals_list:"))
async def my_paypals_list(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    group = callback.data.split(":", 1)[1]
    config = MY_PAYPAL_GROUPS.get(group)
    if config is None:
        await callback.answer("Раздел не найден", show_alert=True)
        return

    statuses, title = config
    requests = await get_user_requests_by_statuses(callback.from_user.id, statuses, limit=8)
    if not requests:
        text = f"<b>{title}</b>\n\nВ этом разделе пока нет заявок."
    else:
        status_names = {
            "waiting_issue": "ожидает выдачи PayPal",
            "paypal_issued": "ожидает оплаты",
            "waiting_check": "платёж проверяется",
            "payout_pending": "ожидает выплаты",
            "paid": "ожидает выплаты",
            "paid_out": "выплачено",
            "not_found": "оплата не найдена",
            "rejected": "отклонено",
            "return_pending": "ожидает проверки возврата",
            "returned": "возвращён",
            "returned_gestoppt": "возвращён как Gestop",
        }
        blocks = [f"<b>{title}</b>", ""]
        for req in requests:
            tag = await get_paypal_tag(req.paypal_tag_id)
            blocks.append(_user_request_line(req, tag.tag if tag else None))
            blocks.append(f"📌 Статус: <b>{status_names.get(req.status, req.status)}</b>")
            blocks.append("━━━━━━━━━━━━")
        text = "\n".join(blocks)

    await render_screen(callback, "requests", text, my_paypals_back_menu())
    await callback.answer()


@router.callback_query(F.data == "my_profits")
async def my_profits(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    summary = await get_user_profit_summary(callback.from_user.id)
    paid_requests = await get_user_requests_by_statuses(callback.from_user.id, ("paid_out",), limit=10)
    last_payment = format_dt(summary["last_at"]) if summary["last_at"] else "пока не было"
    lines = [
        "<b>📈 Мои профиты</b>",
        "",
        f"💰 Выплачено всего: <b>{summary['total']:.2f} €</b>",
        f"📄 Всего выплат: <b>{summary['count']}</b>",
        f"💶 Средняя выплата: <b>{summary['average']:.2f} €</b>",
        f"🟢 Ожидает выплаты: <b>{summary['pending']:.2f} €</b>",
        f"📅 Последняя выплата: <b>{last_payment}</b>",
    ]
    if paid_requests:
        lines.extend(["", "<b>Последние выплаты:</b>"])
        for req in paid_requests:
            lines.append(f"• #{req.id} · <b>{float(req.payout_amount or 0):.2f} €</b> · {format_dt(req.payout_at)}")
    await render_screen(callback, "profile", "\n".join(lines), back_home())
    await callback.answer()


@router.callback_query(F.data == "my_requests_legacy")
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
            "payout_pending": "💸 ожидает выплаты",
            "paid_out": "✅ выплачено",
            "paid": "💸 ожидает выплаты",
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
    queue_count = await count_waiting_requests()
    payment_counts = await get_payment_counts()
    finance = await get_finance_summary()
    text = (
        "👨‍💼 <b>Админ-панель</b>\n\n"
        f"👥 Всего пользователей: <b>{counts['all']}</b>\n"
        f"🟡 Ожидают решения: <b>{counts['pending']}</b>\n"
        f"💳 Свободных PayPal: <b>{available}</b>\n"
        f"📥 В очереди PayPal: <b>{queue_count}</b>\n"
        f"🟠 Оплат на проверке: <b>{payment_counts['check']}</b>\n"
        f"🟢 Нужно выплатить: <b>{payment_counts['payout']}</b>\n"
        f"💸 Сумма к выплате: <b>{finance['pending']:.2f} €</b>\n"
        f"📈 Общая прибыль: <b>{finance['profit']:.2f} €</b>\n\n"
        "Добавление тегов пока доступно командой:\n"
        "<code>/addtags @tag1 @tag2 @tag3</code>"
    )
    markup = admin_main_menu(counts["pending"], queue_count)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
    else:
        if target.message.photo:
            try:
                await target.message.delete()
            except TelegramBadRequest:
                pass
            await target.bot.send_message(target.message.chat.id, text, reply_markup=markup)
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


@router.callback_query(F.data.startswith("paypal_queue:"))
async def paypal_queue_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    offset = max(0, int(callback.data.split(":", 1)[1]))
    page_size = 10
    requests, has_next = await list_waiting_requests(offset=offset, limit=page_size)
    page = offset // page_size + 1
    text = f"📥 <b>Очередь PayPal</b>\nСтраница: <b>{page}</b>\n\n"
    text += "Нажмите на заявку для просмотра скриншота и обработки." if requests else "Очередь пуста."
    markup = paypal_queue_menu(requests, offset, page_size, has_next)
    if callback.message.photo:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.bot.send_message(callback.message.chat.id, text, reply_markup=markup)
    else:
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("queue_card:"))
async def queue_card_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    request_id = int(callback.data.split(":", 1)[1])
    req = await get_request(request_id)
    if req is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    user = await get_user(req.user_id)
    username = f"@{user.username}" if user and user.username else "не указан"
    name = user.full_name if user and user.full_name else "не указано"
    caption = (
        f"📄 <b>Заявка PayPal #{req.id}</b>\n\n"
        f"👤 {name}\n"
        f"Username: {username}\n"
        f"🆔 <code>{req.user_id}</code>\n"
        f"💶 Сумма: <b>{req.amount} €</b>\n"
        f"Статус: <b>{req.status}</b>\n"
        f"Создана: {format_dt(req.created_at)}"
    )
    if req.screenshot_file_id:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.bot.send_photo(
            callback.message.chat.id,
            photo=req.screenshot_file_id,
            caption=caption,
            reply_markup=queue_request_menu(req.id, req.user_id),
        )
    else:
        await callback.message.edit_text(caption, reply_markup=queue_request_menu(req.id, req.user_id))
    await callback.answer()


@router.callback_query(F.data.startswith("queue_block:"))
async def queue_block_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, request_id_raw, user_id_raw = callback.data.split(":", 2)
    request_id = int(request_id_raw)
    user_id = int(user_id_raw)
    await set_user_access_status(user_id, "blocked", callback.from_user.id)
    req = await set_request_status(request_id, "rejected", callback.from_user.id)
    try:
        await callback.bot.send_message(user_id, "🚫 Ваш доступ заблокирован. Заявка PayPal отклонена.")
    except Exception:
        pass
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=(callback.message.html_text or callback.message.caption or "") + "\n\n🚫 Пользователь заблокирован")
        else:
            await callback.message.edit_text((callback.message.html_text or "") + "\n\n🚫 Пользователь заблокирован")
    except TelegramBadRequest:
        pass
    await callback.answer("Пользователь заблокирован")


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


@router.callback_query(F.data == "payments_menu")
async def payments_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    counts = await get_payment_counts()
    text = (
        "💰 <b>Платежи</b>\n\n"
        "Здесь сохраняются все заявки после выдачи PayPal. "
        "Откройте нужную категорию и обработайте карточку."
    )
    if callback.message.photo:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.bot.send_message(callback.message.chat.id, text, reply_markup=payments_menu(counts))
    else:
        await callback.message.edit_text(text, reply_markup=payments_menu(counts))
    await callback.answer()


@router.callback_query(F.data.startswith("payments_list:"))
async def payments_list_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, filter_name, offset_text = callback.data.split(":", 2)
    offset = max(0, int(offset_text))
    page_size = 10
    requests, has_next = await list_payment_requests(filter_name, offset, page_size)
    titles = {
        "check": "🟠 Ожидают проверки оплаты",
        "payout": "🟢 Нужно выплатить",
        "paidout": "✅ Выплаченные",
        "waiting": "🕓 Ожидают оплаты",
        "notfound": "🔴 Оплата не найдена",
        "all": "📋 Все платежные заявки",
    }
    text = f"{titles.get(filter_name, titles['all'])}\nСтраница: <b>{offset // page_size + 1}</b>\n\n"
    text += "Выберите заявку." if requests else "В этой категории заявок нет."
    markup = payments_list_menu(requests, filter_name, offset, page_size, has_next)
    if callback.message.photo:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.bot.send_message(callback.message.chat.id, text, reply_markup=markup)
    else:
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("payment_card:"))
async def payment_card_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    request_id = int(parts[1])
    filter_name = parts[2] if len(parts) > 2 else "all"
    offset = int(parts[3]) if len(parts) > 3 else 0
    req = await get_request(request_id)
    if req is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    user = await get_user(req.user_id)
    tag = await get_paypal_tag(req.paypal_tag_id)
    status_names = {
        "paypal_issued": "🕓 PayPal выдан — ожидается оплата",
        "waiting_check": "🟠 Ожидает проверки оплаты",
        "payout_pending": "🟢 Оплата получена — нужно выплатить клиенту",
        "paid_out": "✅ Выплачено клиенту",
        "not_found": "🔴 Оплата не найдена",
    }
    username = f"@{user.username}" if user and user.username else "не указан"
    text = (
        f"💰 <b>Платёжная заявка #{req.id}</b>\n\n"
        f"👤 {user.full_name if user and user.full_name else 'не указано'}\n"
        f"Username: {username}\n"
        f"🆔 <code>{req.user_id}</code>\n\n"
        f"💳 PayPal: <code>{tag.tag if tag else 'не найден'}</code>\n"
        f"💶 Сумма: <b>{req.amount} €</b>\n"
        + (f"📊 Процент: <b>{req.payout_percent}%</b>\n💸 К выплате: <b>{float(req.payout_amount):.2f} €</b>\n" if req.payout_percent is not None and req.payout_amount is not None else "")
        + f"\nСтатус: <b>{status_names.get(req.status, req.status)}</b>\n\n"
        f"📅 Создана: {format_dt(req.created_at)}\n"
        f"📤 PayPal выдан: {format_dt(req.processed_at)}\n"
        f"✅ Нажал «Я оплатил»: {format_dt(req.paid_clicked_at)}\n"
        f"🔎 Оплата подтверждена: {format_dt(req.payment_confirmed_at)}\n"
        f"💸 Выплата клиенту: {format_dt(req.payout_at)}"
    )
    markup = payment_card_menu(req.id, req.user_id, req.status, filter_name, offset)
    if callback.message.photo:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.bot.send_message(callback.message.chat.id, text, reply_markup=markup)
    else:
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("payment_amount_edit:"))
async def payment_amount_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    request_id = int(callback.data.split(":")[1])
    req = await get_request(request_id)
    if req is None or req.status not in {"payout_pending", "waiting_check"}:
        await callback.answer("Сумму этой заявки уже нельзя изменить", show_alert=True)
        return
    await state.set_state(PaymentAmountForm.admin_edit_amount)
    await state.update_data(payment_request_id=request_id)
    await callback.message.answer(
        f"✏️ Текущая сумма: <b>{req.amount} €</b>\n\nВведите новую актуальную сумму, например: <code>75</code>"
    )
    await callback.answer()


@router.message(PaymentAmountForm.admin_edit_amount)
async def payment_amount_edit_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip().replace("€", "").replace(" ", "")
    if not raw.isdigit():
        await message.answer("Введите сумму целым числом, например: <code>75</code>")
        return
    amount = int(raw)
    if amount < 1 or amount > 100000:
        await message.answer("Сумма должна быть от 1 до 100000 €.")
        return
    data = await state.get_data()
    request_id = int(data["payment_request_id"])
    req = await update_request_amount(request_id, amount)
    await state.clear()
    if req is None:
        await message.answer("Заявка не найдена.")
        return
    await message.answer(
        f"✅ Сумма заявки #{req.id} изменена на <b>{amount} €</b>.",
        reply_markup=payment_card_menu(req.id, req.user_id, req.status),
    )


@router.callback_query(F.data.startswith("payout_confirm:"))
async def payout_confirm_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    request_id = int(callback.data.split(":", 1)[1])
    req = await get_request(request_id)
    if req is None or req.status != "payout_pending":
        await callback.answer("Заявка уже обработана", show_alert=True)
        return
    user = await get_user(req.user_id)
    username = f"@{user.username}" if user and user.username else str(req.user_id)
    await callback.message.edit_text(
        "💸 <b>Подтверждение выплаты</b>\n\n"
        f"Клиент: {username}\n"
        f"Получено: <b>{req.amount} €</b>\n"
        f"К выплате: <b>{float(req.payout_amount or 0):.2f} €</b>\n\n"
        "Подтвердите, что деньги действительно отправлены клиенту.",
        reply_markup=payout_confirmation_menu(req.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("payout_done:"))
async def payout_done_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    request_id = int(callback.data.split(":", 1)[1])
    req = await mark_payout_done(request_id, callback.from_user.id)
    if req is None:
        await callback.answer("Заявка уже обработана или недоступна", show_alert=True)
        return
    try:
        await callback.bot.send_message(
            req.user_id,
            f"✅ <b>Выплата по заявке #{req.id} выполнена</b>\n\nСумма выплаты: <b>{float(req.payout_amount or 0):.2f} €</b>",
            reply_markup=back_home(),
        )
    except Exception:
        pass
    await callback.message.edit_text(
        f"✅ Выплата по заявке #{req.id} отмечена.\n\n"
        "Заявка удалена из списка «Нужно выплатить» и сохранена в архиве.",
        reply_markup=payments_menu(await get_payment_counts()),
    )
    await callback.answer("Выплата подтверждена")


@router.callback_query(F.data.startswith("payment_recheck:"))
async def payment_recheck_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    request_id = int(callback.data.split(":", 1)[1])
    req = await return_to_payment_check(request_id, callback.from_user.id)
    if req is None:
        await callback.answer("Нельзя вернуть эту заявку", show_alert=True)
        return
    await callback.message.edit_text(
        f"🟠 Заявка #{req.id} возвращена в список проверки оплаты.",
        reply_markup=payments_menu(await get_payment_counts()),
    )
    await callback.answer()


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
    await set_request_status(request_id, "paypal_issued", callback.from_user.id)

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
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=(callback.message.html_text or callback.message.caption or "") + f"\n\n✅ Выдан: <code>{tag.tag}</code>"
            )
        else:
            await callback.message.edit_text((callback.message.html_text or "") + f"\n\n✅ Выдан: <code>{tag.tag}</code>")
    except TelegramBadRequest:
        pass
    await callback.answer("PayPal выдан")


@router.callback_query(F.data.startswith("user_paid:"))
async def user_paid(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    request_id = int(callback.data.split(":")[1])
    req = await get_request(request_id)
    if req is None or req.user_id != callback.from_user.id or req.status != "paypal_issued":
        await callback.answer("Заявка уже обработана или недоступна", show_alert=True)
        return
    await callback.message.edit_caption(
        caption=(
            "💶 <b>Подтвердите сумму оплаты</b>\n\n"
            f"Текущая сумма: <b>{req.amount} €</b>\n\n"
            "Если оплатили другую сумму — нажмите «Изменить сумму»."
        ),
        reply_markup=user_amount_confirmation_menu(req.id, req.amount),
    )
    await callback.answer()


async def finish_user_paid(callback_or_message, request_id: int, user_id: int) -> bool:
    ok = await mark_paid_by_user(request_id, user_id)
    if not ok:
        return False
    req = await get_request(request_id)
    bot = callback_or_message.bot
    for admin_id in settings.admin_ids:
        await bot.send_message(
            admin_id,
            "💰 <b>Пользователь сообщил об оплате</b>\n\n"
            f"Заявка: #{request_id}\n"
            f"Пользователь ID: <code>{user_id}</code>\n"
            f"Сумма: <b>{req.amount} €</b>",
            reply_markup=admin_check_menu(request_id),
        )
    return True


@router.callback_query(F.data.startswith("user_paid_confirm:"))
async def user_paid_confirm(callback: CallbackQuery) -> None:
    request_id = int(callback.data.split(":")[1])
    if not await finish_user_paid(callback, request_id, callback.from_user.id):
        await callback.answer("Заявка уже обработана или недоступна", show_alert=True)
        return
    await render_screen(callback, "requests", "🔎 <b>Оплата отправлена на проверку</b>\n\nАдминистратор проверит поступление и подтвердит заявку.", back_home())
    await callback.answer()


@router.callback_query(F.data.startswith("user_paid_change:"))
async def user_paid_change(callback: CallbackQuery, state: FSMContext) -> None:
    request_id = int(callback.data.split(":")[1])
    req = await get_request(request_id)
    if req is None or req.user_id != callback.from_user.id or req.status != "paypal_issued":
        await callback.answer("Заявка недоступна", show_alert=True)
        return
    await state.set_state(PaymentAmountForm.user_amount)
    await state.update_data(payment_request_id=request_id)
    await callback.message.answer("✏️ Введите актуальную сумму оплаты в евро, только число. Например: <code>75</code>")
    await callback.answer()


@router.message(PaymentAmountForm.user_amount)
async def user_paid_amount_input(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace("€", "").replace(" ", "")
    if not raw.isdigit():
        await message.answer("Введите сумму целым числом, например: <code>75</code>")
        return
    amount = int(raw)
    if amount < 1 or amount > 100000:
        await message.answer("Сумма должна быть от 1 до 100000 €.")
        return
    data = await state.get_data()
    request_id = int(data["payment_request_id"])
    req = await update_request_amount(request_id, amount, message.from_user.id)
    if req is None:
        await state.clear()
        await message.answer("Заявка уже обработана или недоступна.")
        return
    if not await finish_user_paid(message, request_id, message.from_user.id):
        await state.clear()
        await message.answer("Заявка уже обработана или недоступна.")
        return
    await state.clear()
    await message.answer(
        f"🔎 <b>Оплата отправлена на проверку</b>\n\nСумма заявки обновлена: <b>{amount} €</b>.",
        reply_markup=back_home(),
    )


@router.callback_query(F.data.startswith("admin_confirm:"))
async def admin_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    request_id = int(callback.data.split(":")[1])
    req = await get_request(request_id)
    if req is None or req.status != "waiting_check":
        await callback.answer("Заявка уже обработана или не найдена", show_alert=True)
        return
    await callback.message.edit_text(
        "💶 <b>Подтвердите полученную сумму</b>\n\n"
        f"Сумма в заявке: <b>{req.amount} €</b>\n\n"
        "Если на PayPal поступила другая сумма — измените её.",
        reply_markup=admin_amount_confirmation_menu(req.id, req.amount),
    )
    await callback.answer()


async def finish_admin_confirm(callback_or_message, request_id: int, admin_id: int):
    req = await confirm_payment(request_id, admin_id)
    if req is None:
        return None
    try:
        await callback_or_message.bot.send_photo(
            req.user_id,
            photo=FSInputFile(BANNERS["issued"]),
            caption=(f"✅ <b>Платёж произведён успешно</b>\n\nСумма: <b>{req.amount} €</b>\nВаш процент: <b>{req.payout_percent}%</b>\nСумма к выплате: <b>{float(req.payout_amount or 0):.2f} €</b>\n\nОжидайте выплату от администрации."),
            reply_markup=back_home(),
        )
    except Exception:
        pass
    return req


@router.callback_query(F.data.startswith("admin_confirm_same:"))
async def admin_confirm_same(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    request_id = int(callback.data.split(":")[1])
    req = await finish_admin_confirm(callback, request_id, callback.from_user.id)
    if req is None:
        await callback.answer("Заявка уже обработана", show_alert=True)
        return
    await callback.message.edit_text(
        f"✅ Оплата по заявке #{req.id} подтверждена.\nСумма: <b>{req.amount} €</b>\nПроцент: <b>{req.payout_percent}%</b>\nК выплате: <b>{float(req.payout_amount or 0):.2f} €</b>\n\nЗаявка перемещена в «🟢 Нужно выплатить».",
        reply_markup=payments_menu(await get_payment_counts()),
    )
    await callback.answer("Оплата подтверждена")


@router.callback_query(F.data.startswith("admin_confirm_change:"))
async def admin_confirm_change(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    request_id = int(callback.data.split(":")[1])
    req = await get_request(request_id)
    if req is None or req.status != "waiting_check":
        await callback.answer("Заявка недоступна", show_alert=True)
        return
    await state.set_state(PaymentAmountForm.admin_amount)
    await state.update_data(payment_request_id=request_id)
    await callback.message.answer("✏️ Введите сумму, которая поступила на PayPal. Например: <code>75</code>")
    await callback.answer()


@router.message(PaymentAmountForm.admin_amount)
async def admin_paid_amount_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip().replace("€", "").replace(" ", "")
    if not raw.isdigit():
        await message.answer("Введите сумму целым числом, например: <code>75</code>")
        return
    amount = int(raw)
    if amount < 1 or amount > 100000:
        await message.answer("Сумма должна быть от 1 до 100000 €.")
        return
    data = await state.get_data()
    request_id = int(data["payment_request_id"])
    req = await update_request_amount(request_id, amount)
    if req is None or req.status != "waiting_check":
        await state.clear()
        await message.answer("Заявка уже обработана или недоступна.")
        return
    req = await finish_admin_confirm(message, request_id, message.from_user.id)
    await state.clear()
    if req is None:
        await message.answer("Заявка уже обработана или недоступна.")
        return
    await message.answer(
        f"✅ Оплата по заявке #{req.id} подтверждена.\nСумма: <b>{amount} €</b>\nПроцент: <b>{req.payout_percent}%</b>\nК выплате: <b>{float(req.payout_amount or 0):.2f} €</b>\n\nЗаявка перемещена в «🟢 Нужно выплатить».",
        reply_markup=payments_menu(await get_payment_counts()),
    )


@router.callback_query(F.data.startswith("admin_not_found:"))
async def admin_not_found(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    request_id = int(callback.data.split(":")[1])
    req = await mark_payment_not_found(request_id, callback.from_user.id)
    if req is None:
        await callback.answer("Заявка уже обработана или не найдена", show_alert=True)
        return
    try:
        await callback.bot.send_photo(
            req.user_id,
            photo=FSInputFile(BANNERS["requests"]),
            caption=f"⚠️ Оплата по заявке #{req.id} не найдена. Проверьте перевод и свяжитесь с поддержкой.",
            reply_markup=back_home(),
        )
    except Exception:
        pass
    await callback.message.edit_text(
        f"🔴 По заявке #{req.id} оплата не найдена.",
        reply_markup=payments_menu(await get_payment_counts()),
    )
    await callback.answer("Отмечено: оплата не найдена")


@router.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    request_id = int(callback.data.split(":")[1])
    req = await set_request_status(request_id, "rejected", callback.from_user.id)
    if req is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    await callback.bot.send_photo(
        req.user_id,
        photo=FSInputFile(BANNERS["requests"]),
        caption=f"❌ Заявка #{req.id} отклонена администратором.",
        reply_markup=back_home(),
    )
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=(callback.message.html_text or callback.message.caption or "") + "\n\n❌ Отклонено")
        else:
            await callback.message.edit_text((callback.message.html_text or "") + "\n\n❌ Отклонено")
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == "rates_menu")
async def rates_panel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    rules = await list_rate_rules()
    text = "⚙️ <b>Проценты выплат</b>\n\nБот выбирает самый высокий порог, который не превышает сумму.\nНапример: от 50 € — 60%, от 100 € — 70%."
    await callback.message.edit_text(text, reply_markup=rates_menu(rules))
    await callback.answer()


@router.callback_query(F.data == "rate_add")
async def rate_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(RateForm.add_rule)
    await callback.message.edit_text(
        "➕ <b>Новый диапазон</b>\n\nВведите минимальную сумму и процент через пробел.\nНапример: <code>150 80</code>",
        reply_markup=rate_cancel_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rate_edit:"))
async def rate_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    rule_id = int(callback.data.split(":")[1])
    rules = await list_rate_rules()
    rule = next((r for r in rules if r.id == rule_id), None)
    if rule is None:
        await callback.answer("Правило не найдено", show_alert=True)
        return
    await state.set_state(RateForm.edit_rule)
    await state.update_data(rate_min_amount=rule.min_amount)
    await callback.message.edit_text(
        f"✏️ Порог: <b>от {rule.min_amount} €</b>\nТекущий процент: <b>{rule.percent}%</b>\n\nВведите новый процент одним числом.",
        reply_markup=rate_cancel_menu(),
    )
    await callback.answer()


@router.message(RateForm.add_rule)
async def rate_add_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear(); return
    parts = (message.text or "").replace("€", "").replace("%", "").split()
    if len(parts) != 2 or not all(x.isdigit() for x in parts):
        await message.answer("Введите два числа, например: <code>150 80</code>", reply_markup=rate_cancel_menu()); return
    minimum, percent = map(int, parts)
    if minimum < 1 or minimum > 100000 or percent < 1 or percent > 100:
        await message.answer("Сумма: 1–100000 €, процент: 1–100.", reply_markup=rate_cancel_menu()); return
    await upsert_rate_rule(minimum, percent)
    await state.clear()
    await message.answer(f"✅ Добавлено: от <b>{minimum} €</b> — <b>{percent}%</b>.", reply_markup=rates_menu(await list_rate_rules()))


@router.message(RateForm.edit_rule)
async def rate_edit_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear(); return
    raw = (message.text or "").replace("%", "").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 100:
        await message.answer("Введите процент от 1 до 100.", reply_markup=rate_cancel_menu()); return
    data = await state.get_data()
    minimum, percent = int(data["rate_min_amount"]), int(raw)
    await upsert_rate_rule(minimum, percent)
    await state.clear()
    await message.answer(f"✅ Для суммы от <b>{minimum} €</b> установлен процент <b>{percent}%</b>.", reply_markup=rates_menu(await list_rate_rules()))


@router.callback_query(F.data.startswith("rate_delete:"))
async def rate_delete_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    ok = await delete_rate_rule(int(callback.data.split(":")[1]))
    if not ok:
        await callback.answer("Нельзя удалить последнее правило", show_alert=True); return
    await callback.message.edit_text("⚙️ <b>Проценты выплат</b>", reply_markup=rates_menu(await list_rate_rules()))
    await callback.answer("Диапазон удалён")


@router.callback_query(F.data == "finance_menu")
async def finance_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    data = await get_finance_summary()
    text = (
        "📊 <b>Финансы</b>\n\n"
        f"💶 Подтверждено: <b>{data['received']:.2f} €</b>\n"
        f"💸 Начислено клиентам: <b>{data['payout']:.2f} €</b>\n"
        f"🟢 Сейчас к выплате: <b>{data['pending']:.2f} €</b>\n"
        f"✅ Уже выплачено: <b>{data['paid']:.2f} €</b>\n"
        f"📈 Прибыль DT Team: <b>{data['profit']:.2f} €</b>"
    )
    await callback.message.edit_text(text, reply_markup=finance_menu())
    await callback.answer()


RETURN_REASON_LABELS = {
    "changed_mind": "❌ Передумал",
    "gestop": "🚫 Gestop",
    "other": "✍️ Другая причина",
}


@router.callback_query(F.data.startswith("return_start:"))
async def return_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    request_id = int(callback.data.split(":")[1])
    req = await get_request(request_id)
    if req is None or req.user_id != callback.from_user.id or req.status != "paypal_issued":
        await callback.answer("PayPal уже обработан или недоступен", show_alert=True)
        return
    await state.clear()
    await callback.message.answer("↩️ <b>Выберите причину возврата PayPal</b>", reply_markup=return_reasons_menu(request_id))
    await callback.answer()


@router.callback_query(F.data.startswith("return_reason:"))
async def return_reason_handler(callback: CallbackQuery, state: FSMContext) -> None:
    _, request_id_raw, reason_code = callback.data.split(":", 2)
    request_id = int(request_id_raw)
    req = await get_request(request_id)
    if req is None or req.user_id != callback.from_user.id or req.status != "paypal_issued":
        await callback.answer("PayPal недоступен", show_alert=True); return
    if reason_code == "other":
        await state.set_state(ReturnForm.custom_reason)
        await state.update_data(return_request_id=request_id, return_reason_code=reason_code)
        await callback.message.answer("✍️ Напишите причину возврата одним сообщением.")
        await callback.answer(); return
    reason_text = RETURN_REASON_LABELS.get(reason_code, reason_code)
    await state.update_data(return_request_id=request_id, return_reason_code=reason_code, return_reason_text=reason_text)
    await callback.message.answer(f"↩️ <b>Вернуть PayPal?</b>\n\nПричина: {reason_text}", reply_markup=return_confirm_menu(request_id))
    await callback.answer()


@router.message(ReturnForm.custom_reason)
async def return_custom_reason_handler(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    if len(reason) < 3:
        await message.answer("Опишите причину подробнее."); return
    data = await state.get_data(); request_id = int(data["return_request_id"])
    await state.update_data(return_reason_text=reason[:500])
    await message.answer(f"↩️ <b>Вернуть PayPal?</b>\n\nПричина: {reason[:500]}", reply_markup=return_confirm_menu(request_id))


@router.callback_query(F.data.startswith("return_confirm:"))
async def return_confirm_handler(callback: CallbackQuery, state: FSMContext) -> None:
    request_id = int(callback.data.split(":")[1]); data = await state.get_data()
    reason_code = data.get("return_reason_code"); reason_text = data.get("return_reason_text")
    if int(data.get("return_request_id", 0)) != request_id or not reason_code or not reason_text:
        await callback.answer("Выберите причину заново", show_alert=True); return
    item = await create_paypal_return(request_id, callback.from_user.id, reason_code, reason_text)
    if item is None:
        await callback.answer("PayPal уже обработан", show_alert=True); return
    req = await get_request(request_id); tag = await get_paypal_tag(req.paypal_tag_id if req else None)
    for admin_id in settings.admin_ids:
        await callback.bot.send_message(admin_id,
            "↩️ <b>Новый запрос на возврат</b>\n\n"
            f"Заявка: #{request_id}\nПользователь: <code>{callback.from_user.id}</code>\n"
            f"PayPal: <code>{tag.tag if tag else '—'}</code>\nСумма: <b>{req.amount if req else 0} €</b>\nПричина: {reason_text}",
            reply_markup=return_card_menu(item.id, callback.from_user.id))
    await state.clear()
    await callback.message.answer("✅ Запрос на возврат отправлен. PayPal будет проверен администратором.", reply_markup=back_home())
    await callback.answer("Запрос отправлен")


@router.callback_query(F.data == "returns_menu")
async def returns_panel_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    items = await list_paypal_returns()
    await render_screen(callback, "paypal", f"<b>↩️ Возвраты PayPal</b>\n\nОжидают проверки: <b>{len(items)}</b>", returns_menu(items))
    await callback.answer()


@router.callback_query(F.data.startswith("return_card:"))
async def return_card_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    item = await get_paypal_return(int(callback.data.split(":")[1]))
    if item is None: await callback.answer("Возврат не найден", show_alert=True); return
    req = await get_request(item.request_id); tag = await get_paypal_tag(item.paypal_tag_id)
    text = (f"<b>↩️ Возврат #{item.id}</b>\n\n👤 ID: <code>{item.user_id}</code>\n"
            f"💳 PayPal: <code>{tag.tag if tag else '—'}</code>\n💶 Сумма: <b>{req.amount if req else 0} €</b>\n"
            f"🕒 Выдан: {format_dt(tag.issued_at if tag else None)}\n📝 Причина: {item.reason_text}\n"
            f"📌 Статус: {item.status}")
    await callback.message.edit_text(text, reply_markup=return_card_menu(item.id, item.user_id)); await callback.answer()


@router.callback_query(F.data.startswith("return_checked:"))
async def return_checked_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    rid = int(callback.data.split(":")[1])
    await callback.message.edit_text("🔍 <b>PayPal проверен. Как поступить?</b>", reply_markup=return_checked_menu(rid)); await callback.answer()


async def _finish_return(callback: CallbackQuery, action: str, reason: str) -> None:
    rid = int(callback.data.split(":")[1]); item = await resolve_paypal_return(rid, action, callback.from_user.id, reason)
    if item is None: await callback.answer("Возврат уже обработан", show_alert=True); return
    messages = {"returned": "✅ PayPal проверен и возвращён в свободную базу.", "gestoppt": "🚫 PayPal отмечен как Gestop и исключён из выдачи.", "deleted": "🗑 PayPal удалён из активной базы."}
    try: await callback.bot.send_message(item.user_id, messages[action], reply_markup=back_home())
    except Exception: pass
    await callback.message.edit_text(messages[action], reply_markup=returns_menu(await list_paypal_returns())); await callback.answer("Готово")


@router.callback_query(F.data.startswith("return_release:"))
async def return_release_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    await _finish_return(callback, "returned", "PayPal пустой. Возвращён в базу.")


@router.callback_query(F.data.startswith("return_gestoppt:"))
async def return_gestoppt_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    await _finish_return(callback, "gestoppt", "PayPal отмечен Gestop. В выдачу не возвращён.")


@router.callback_query(F.data.startswith("return_delete:"))
async def return_delete_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await _finish_return(callback, "deleted", "PayPal удалён из активной базы после проверки возврата.")


@router.callback_query(F.data == "paypal_database")
async def paypal_database_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    counts = await get_paypal_database_counts()
    await render_screen(callback, "paypal", "<b>💳 База PayPal</b>\n\nПросмотр тегов, статусов и PayPal в работе по датам.", paypal_database_menu(counts)); await callback.answer()


@router.callback_query(F.data.startswith("paypal_db_list:"))
async def paypal_db_list_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    filter_name = callback.data.split(":")[1]; tags = await list_paypal_tags(filter_name)
    await callback.message.edit_caption(caption=f"<b>💳 PayPal: {filter_name}</b>\n\nНайдено: <b>{len(tags)}</b>", reply_markup=paypal_list_menu(tags, filter_name)); await callback.answer()


@router.callback_query(F.data.startswith("paypal_card:"))
async def paypal_card_admin_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    _, tid, filter_name = callback.data.split(":", 2); tag = await get_paypal_tag(int(tid))
    if tag is None: await callback.answer("Не найден", show_alert=True); return
    text=(f"<b>💳 {tag.tag}</b>\n\nСтатус: <b>{tag.status}</b>\nПользователь ID: <code>{tag.issued_to_user_id or '—'}</code>\n"
          f"Выдан: {format_dt(tag.issued_at)}\nДобавлен: {format_dt(tag.created_at)}")
    await callback.message.edit_caption(caption=text, reply_markup=paypal_card_admin_menu(tag.id, filter_name, tag.status)); await callback.answer()


@router.callback_query(F.data.startswith("paypal_delete_ask:"))
async def paypal_delete_ask_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    _, tid, filter_name = callback.data.split(":", 2)
    tag = await get_paypal_tag(int(tid))
    if tag is None or tag.status == "deleted":
        await callback.answer("PayPal не найден", show_alert=True); return
    if tag.status != "available":
        await callback.answer("Удалить можно только свободный PayPal", show_alert=True); return
    await callback.message.edit_caption(
        caption=f"<b>🗑 Удалить PayPal?</b>\n\n<code>{tag.tag}</code>\n\nПосле удаления он исчезнет из свободной базы и больше не будет выдаваться.",
        reply_markup=paypal_delete_confirm_menu(tag.id, filter_name),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("paypal_delete_confirm:"))
async def paypal_delete_confirm_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    _, tid, filter_name = callback.data.split(":", 2)
    ok, reason = await delete_free_paypal_tag(int(tid))
    if not ok:
        message = "Удалить можно только свободный PayPal" if reason == "not_available" else "PayPal уже удалён или не найден"
        await callback.answer(message, show_alert=True); return
    tags = await list_paypal_tags(filter_name)
    await callback.message.edit_caption(
        caption=f"<b>💳 PayPal: {filter_name}</b>\n\nНайдено: <b>{len(tags)}</b>",
        reply_markup=paypal_list_menu(tags, filter_name),
    )
    await callback.answer("PayPal удалён")


@router.callback_query(F.data.startswith("paypal_mark_"))
async def paypal_mark_status_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    parts=callback.data.split(":"); action=parts[0]; tid=int(parts[1]); filter_name=parts[2]
    status="gestoppt" if action=="paypal_mark_gestoppt" else "available"
    await set_paypal_tag_status(tid,status)
    tags = await list_paypal_tags(filter_name)
    await callback.message.edit_caption(caption=f"<b>💳 PayPal: {filter_name}</b>\n\nНайдено: <b>{len(tags)}</b>", reply_markup=paypal_list_menu(tags, filter_name))
    await callback.answer("Статус обновлён")


@router.callback_query(F.data == "working_dates")
async def working_dates_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    rows=await get_working_dates()
    await callback.message.edit_caption(caption="<b>👤 PayPal в работе по датам</b>\n\nВыберите дату выдачи:", reply_markup=working_dates_menu(rows)); await callback.answer()


@router.callback_query(F.data.startswith("working_day:"))
async def working_day_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    day=callback.data.split(":",1)[1]; reqs=await get_working_requests_by_date(day)
    total=sum(r.amount for r in reqs)
    await callback.message.edit_caption(caption=f"<b>📅 PayPal в работе за {day}</b>\n\nКоличество: <b>{len(reqs)}</b>\nОбщая сумма: <b>{total} €</b>", reply_markup=working_day_menu(day,reqs)); await callback.answer()


@router.callback_query(F.data.startswith("collect_notify:"))
async def collect_notify_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    day=callback.data.split(":",1)[1]; reqs=await get_working_requests_by_date(day); sent=0
    for req in reqs:
        marked=await mark_collection_notified(req.id)
        if not marked: continue
        tag=await get_paypal_tag(req.paypal_tag_id)
        try:
            await callback.bot.send_message(req.user_id,
                f"⚠️ <b>Через 30 минут администрация заберёт неподтверждённые PayPal</b>\n\n"
                f"Дата выдачи: <b>{day}</b>\nPayPal: <code>{tag.tag if tag else '—'}</code>\nСумма: <b>{req.amount} €</b>\n\n"
                "Выберите: он ещё нужен или его можно вернуть.", reply_markup=collection_choice_menu(req.id)); sent+=1
        except Exception: pass
    await callback.answer(f"Уведомлено: {sent}", show_alert=True)


@router.callback_query(F.data.startswith("collect_keep:"))
async def collect_keep_handler(callback: CallbackQuery) -> None:
    req=await confirm_paypal_keep(int(callback.data.split(":")[1]), callback.from_user.id)
    if req is None: await callback.answer("PayPal недоступен", show_alert=True); return
    await callback.message.edit_text("✅ Подтверждено: этот PayPal вам ещё нужен."); await callback.answer()


@router.callback_query(F.data.startswith("collect_take:"))
async def collect_take_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    day=callback.data.split(":",1)[1]; reqs=await list_unconfirmed_collection(day); created=0
    for req in reqs:
        item=await create_paypal_return(req.id, req.user_id, "collection_timeout", "Не подтверждён после уведомления о сборе")
        if item: created+=1
    items = await list_paypal_returns()
    await render_screen(callback, "paypal", f"<b>↩️ Возвраты PayPal</b>\n\nОжидают проверки: <b>{len(items)}</b>", returns_menu(items))
    await callback.answer(f"Передано в возвраты: {created}", show_alert=True)
