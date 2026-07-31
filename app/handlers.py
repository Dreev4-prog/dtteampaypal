from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO

from openpyxl import Workbook

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, InputMediaPhoto, Message

from app.config import settings
from app.ui import admin_dashboard_caption, request_amount_caption, support_caption, user_home_caption
from app.db import (
    add_paypal_tag,
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
    confirm_working_payment,
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
    confirm_paypal_keep, user_return_paypal_after_warning, list_unconfirmed_collection,
    admin_recall_working_request, bulk_delete_working_day, search_working_requests,
    get_app_setting, set_app_setting, is_work_enabled, set_work_enabled, list_approved_user_ids, mark_payment_gs,
    get_dashboard_summary, get_user_crm_stats, global_admin_search, get_period_statistics,
    get_user_payout_method, set_user_payout_method, get_user_balance,
    list_users_with_available_balance, get_payout_user_details, complete_manual_payout,
    list_manual_payouts, get_manual_payout, get_payout_dashboard_counts,
)
from app.keyboards import (
    admin_check_menu,
    paypal_payments_hub_menu,
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
    paypal_card_admin_menu, paypal_delete_confirm_menu, working_dates_menu, working_day_menu, collection_choice_menu, collect_take_confirm_menu,
    working_card_menu, working_notify_confirm_menu, collection_return_confirm_menu, working_recall_confirm_menu, working_delete_day_confirm_menu, working_search_results_menu,
    working_search_cancel_menu, work_control_menu, work_edit_cancel_menu, work_image_edit_menu,
    paypal_add_photo_menu, paypal_add_confirm_menu, paypal_add_cancel_menu, gender_choice_menu,
    broadcast_photo_menu, broadcast_confirm_menu, gs_photo_menu,
    global_search_cancel_menu, global_search_results_menu, crm_user_menu, statistics_period_menu, quick_notify_menu,
    content_menu, content_cancel_menu, content_image_menu,
    payout_method_menu, wallet_menu, payout_method_wallet_menu, payout_history_menu, payout_history_card_menu, payouts_users_menu, payout_user_menu, manual_payout_cancel_menu,
)

router = Router()


class MemberSearch(StatesGroup):
    query = State()


class PaypalRequestForm(StatesGroup):
    amount = State()
    gender = State()
    screenshot = State()


class PaymentAmountForm(StatesGroup):
    user_amount = State()
    admin_amount = State()
    admin_edit_amount = State()


class ManualPayoutForm(StatesGroup):
    check = State()


class RateForm(StatesGroup):
    add_rule = State()
    edit_rule = State()


class ReturnForm(StatesGroup):
    custom_reason = State()
    reject_reason = State()


class WorkingSearch(StatesGroup):
    query = State()


class WorkMessageForm(StatesGroup):
    text = State()
    image = State()


class BroadcastForm(StatesGroup):
    text = State()
    photo = State()


class GSForm(StatesGroup):
    screenshot = State()


class GlobalSearchForm(StatesGroup):
    query = State()


class QuickNotifyForm(StatesGroup):
    text = State()


class ContentForm(StatesGroup):
    text = State()
    image = State()


class PaypalAddForm(StatesGroup):
    gender = State()
    tag = State()
    photo = State()
    bulk = State()
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"

BANNERS = {
    "home": ASSETS_DIR / "home_v2.jpg",
    "paypal": ASSETS_DIR / "request_v2.jpg",
    "requests": ASSETS_DIR / "requests.jpg",
    "profile": ASSETS_DIR / "profile_v2.jpg",
    "links": ASSETS_DIR / "links.jpg",
    "support": ASSETS_DIR / "support_v2.jpg",
    "issued": ASSETS_DIR / "issued_v2.jpg",
    "admin": ASSETS_DIR / "admin_v2.jpg",
    "payments": ASSETS_DIR / "payments_v2.jpg",
    "database": ASSETS_DIR / "database_v2.jpg",
    "broadcast": ASSETS_DIR / "broadcast_v2.jpg",
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


async def render_custom_photo_screen(
    target: Message | CallbackQuery,
    default_banner: str,
    photo_file_id: str,
    caption: str,
    reply_markup=None,
) -> Message:
    """Render local banner or Telegram file_id stored in settings."""
    photo = photo_file_id or FSInputFile(BANNERS[default_banner])
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
    return await target.bot.send_photo(chat_id=message.chat.id, photo=photo, caption=caption, reply_markup=reply_markup)


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

    work_enabled = await is_work_enabled()
    default_home = user_home_caption(work_enabled)
    home_text = await get_app_setting("content_home_text", default_home)
    status = "🟢 Сервис работает" if work_enabled else "🔴 Новые заявки временно закрыты"
    if "{status}" in home_text:
        home_text = home_text.replace("{status}", status)
    home_image = await get_app_setting("content_home_image", "")
    await render_custom_photo_screen(target, "home", home_image, home_text, main_menu())


async def has_access(callback: CallbackQuery) -> bool:
    user = await get_user(callback.from_user.id)
    if user is not None and user.status == "approved":
        return True
    await show_home(callback)
    await callback.answer("Сначала дождитесь одобрения", show_alert=True)
    return False


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await show_home(message)


@router.message(Command("menu"))
async def menu_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await show_home(message)


@router.message(Command("paypal"))
async def paypal_command(message: Message, state: FSMContext) -> None:
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    user = await get_user(message.from_user.id)
    if user is None or user.status != "approved":
        await state.clear()
        await show_home(message)
        return
    if not await is_work_enabled():
        await state.clear()
        await message.answer(
            "🔴 <b>Сейчас STOP WORK</b>\n\n"
            "Новые заявки на PayPal временно отключены. Вы можете продолжить работу "
            "с PayPal, которые уже получили.",
            reply_markup=back_home(),
        )
        return
    active = await count_active_requests(message.from_user.id)
    if active >= 2:
        await state.clear()
        await message.answer(
            "❌ У вас уже есть 2 заявки, ожидающие выдачи. Дождитесь обработки одной из них.",
            reply_markup=back_home(),
        )
        return
    await state.clear()
    await state.set_state(PaypalRequestForm.amount)
    await message.answer_photo(
        photo=FSInputFile(BANNERS["paypal"]),
        caption=await get_app_setting("content_paypal_text", request_amount_caption()),
        reply_markup=request_cancel_menu(),
    )


@router.message(Command("support"))
async def support_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    user = await get_user(message.from_user.id)
    if user is None or user.status != "approved":
        await show_home(message)
        return
    await message.answer_photo(
        photo=FSInputFile(BANNERS["support"]),
        caption=await get_app_setting("content_support_text", support_caption()),
        reply_markup=back_home(),
    )


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
    if not await is_work_enabled():
        await callback.answer("Сейчас STOP WORK. Новые заявки временно отключены.", show_alert=True)
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
    paypal_text = await get_app_setting("content_paypal_text", request_amount_caption())
    await render_screen(
        callback,
        "paypal",
        paypal_text,
        request_cancel_menu(),
    )
    await callback.answer()


@router.message(PaypalRequestForm.amount)
async def paypal_amount_input(message: Message, state: FSMContext) -> None:
    user = await get_user(message.from_user.id)
    if user is None or user.status != "approved":
        await state.clear()
        return
    if not await is_work_enabled():
        await state.clear()
        await message.answer("🛑 Сейчас STOP WORK. Создание новых заявок остановлено.", reply_markup=back_home())
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
    await state.set_state(PaypalRequestForm.gender)
    await message.answer("🚻 <b>Какой PayPal вам нужен?</b>", reply_markup=gender_choice_menu("request_gender"))


@router.callback_query(PaypalRequestForm.gender, F.data.startswith("request_gender:"))
async def paypal_gender_choice(callback: CallbackQuery, state: FSMContext) -> None:
    gender = callback.data.split(":", 1)[1]
    await state.update_data(paypal_gender=gender)
    await state.set_state(PaypalRequestForm.screenshot)
    await callback.message.answer(
        "📷 <b>Подтверждение</b>\n\n"
        "Пришлите скриншот, подтверждающий, что вы готовы оплатить через "
        "PayPal Friends & Family.\n\n"
        "Нужно отправить именно фотографию или изображение.",
        reply_markup=request_cancel_menu(),
    )
    await callback.answer()


@router.message(PaypalRequestForm.screenshot, F.photo)
async def paypal_screenshot_input(message: Message, state: FSMContext) -> None:
    user = await get_user(message.from_user.id)
    if user is None or user.status != "approved":
        await state.clear()
        return
    if not await is_work_enabled():
        await state.clear()
        await message.answer("🛑 Сейчас STOP WORK. Создание новых заявок остановлено.", reply_markup=back_home())
        return
    active = await count_active_requests(message.from_user.id)
    if active >= 2:
        await state.clear()
        await message.answer("❌ У вас уже есть 2 активные заявки.", reply_markup=back_home())
        return
    data = await state.get_data()
    amount = int(data["amount"])
    screenshot_file_id = message.photo[-1].file_id
    gender = data.get("paypal_gender", "male")
    req = await create_request(message.from_user.id, amount, screenshot_file_id, gender)
    await state.clear()

    await message.answer(
        f"✅ <b>Заявка #{req.id} принята</b>\n\n"
        f"Сумма: <b>{amount} €</b>\n"
        f"Тип: {'👨 Мужской' if gender == 'male' else '👩 Женский'}\n"
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
        f"🚻 Тип: {'👨 Мужской' if gender == 'male' else '👩 Женский'}\n"
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


@router.callback_query(F.data == "support")
async def support(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    await render_screen(
        callback,
        "support",
        await get_app_setting("content_support_text", support_caption()),
        back_home(),
    )
    await callback.answer()


async def replace_photo_with_text(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    """Show a text admin screen even when the current screen is a photo message."""
    if callback.message.photo:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.bot.send_message(
            callback.message.chat.id,
            text,
            reply_markup=reply_markup,
        )
    else:
        await callback.message.edit_text(text, reply_markup=reply_markup)


async def show_admin_home(target: Message | CallbackQuery) -> None:
    data = await get_dashboard_summary()
    work_enabled = await is_work_enabled()
    updated_at = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%H:%M:%S")
    text = admin_dashboard_caption(data, work_enabled, updated_at)
    await render_screen(target, "admin", text, admin_main_menu(0, data["queue"]))


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
    await callback.answer("✅ Данные обновлены")


@router.callback_query(F.data == "paypal_payments_hub")
async def paypal_payments_hub_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    payment_counts = await get_payment_counts()
    database_counts = await get_paypal_database_counts()
    text = (
        "💳 <b>РАБОТА С PAYPAL</b>\n\n"
        "Проверка оплат, PayPal в работе, свободная база, возвраты, GS и Gestop.\n\n"
        "Для поиска пользователя или PayPal используйте общий поиск на главной админ-панели."
    )
    await render_screen(
        callback,
        "paypal",
        text,
        paypal_payments_hub_menu(payment_counts, database_counts),
    )
    await callback.answer()


@router.callback_query(F.data == "content_menu")
async def content_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    home_image = await get_app_setting("content_home_image", "")
    text = (
        "📣 <b>КОНТЕНТ И РАССЫЛКИ</b>\n\n"
        "Здесь можно создавать рассылки, менять основные тексты и картинку главного экрана без обновления кода.\n\n"
        "Подсказка: в приветствии можно использовать <code>{status}</code> — "
        "бот автоматически подставит статус работы."
    )
    await replace_photo_with_text(callback, text, content_menu(bool(home_image)))
    await callback.answer()


@router.callback_query(F.data.startswith("content_edit:"))
async def content_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    kind = callback.data.split(":", 1)[1]
    labels = {
        "home": "приветствия",
        "paypal": "экрана Получить PayPal",
        "support": "поддержки",
    }
    keys = {
        "home": "content_home_text",
        "paypal": "content_paypal_text",
        "support": "content_support_text",
    }
    defaults = {
        "home": user_home_caption(await is_work_enabled()),
        "paypal": request_amount_caption(),
        "support": support_caption(),
    }
    if kind not in keys:
        await callback.answer("Неизвестный раздел", show_alert=True)
        return
    await state.set_state(ContentForm.text)
    await state.update_data(content_key=keys[kind])
    current = await get_app_setting(keys[kind], defaults[kind])
    text = (
        f"✏️ <b>Изменение {labels[kind]}</b>\n\n"
        "Пришлите новый текст одним сообщением. HTML-разметка Telegram поддерживается.\n\n"
        f"<b>Сейчас:</b>\n{current}"
    )
    await replace_photo_with_text(callback, text, content_cancel_menu())
    await callback.answer()


@router.message(ContentForm.text)
async def content_text_save(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if not message.text or len(message.text) > 4000:
        await message.answer(
            "Текст должен быть обычным сообщением длиной до 4000 символов.",
            reply_markup=content_cancel_menu(),
        )
        return
    data = await state.get_data()
    await set_app_setting(data["content_key"], message.html_text)
    await state.clear()
    has_image = bool(await get_app_setting("content_home_image", ""))
    await message.answer(
        "✅ Контент сохранён и уже применяется.",
        reply_markup=content_menu(has_image),
    )


@router.callback_query(F.data == "content_home_image")
async def content_home_image_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(ContentForm.image)
    current = await get_app_setting("content_home_image", "")
    text = (
        "🖼 <b>Картинка главного экрана</b>\n\n"
        "Отправьте новую фотографию. Она сохранится через Telegram file_id и применится сразу."
    )
    await replace_photo_with_text(callback, text, content_image_menu(bool(current)))
    await callback.answer()


@router.message(ContentForm.image, F.photo)
async def content_home_image_save(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await set_app_setting("content_home_image", message.photo[-1].file_id)
    await state.clear()
    await message.answer(
        "✅ Новая картинка главного экрана сохранена.",
        reply_markup=content_menu(True),
    )


@router.message(ContentForm.image)
async def content_home_image_invalid(message: Message) -> None:
    current = bool(await get_app_setting("content_home_image", ""))
    await message.answer(
        "Пришлите изображение как фотографию.",
        reply_markup=content_image_menu(current),
    )


@router.callback_query(F.data == "content_home_image_delete")
async def content_home_image_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await set_app_setting("content_home_image", "")
    await state.clear()
    await replace_photo_with_text(
        callback,
        "✅ Пользовательская картинка удалена. Используется стандартный баннер.",
        content_menu(False),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("content_reset:"))
async def content_reset_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    kind = callback.data.split(":", 1)[1]
    defaults = {
        "home": user_home_caption(await is_work_enabled()),
        "paypal": request_amount_caption(),
        "support": support_caption(),
    }
    keys = {
        "home": "content_home_text",
        "paypal": "content_paypal_text",
        "support": "content_support_text",
    }
    if kind not in keys:
        await callback.answer("Неизвестный раздел", show_alert=True)
        return
    await set_app_setting(keys[kind], defaults[kind])
    await state.clear()
    has_image = bool(await get_app_setting("content_home_image", ""))
    await replace_photo_with_text(
        callback,
        "✅ Текст восстановлен по умолчанию.",
        content_menu(has_image),
    )
    await callback.answer()


@router.callback_query(F.data == "work_control")
async def work_control_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    enabled = await is_work_enabled()
    start_text = await get_app_setting("start_work_message")
    stop_text = await get_app_setting("stop_work_message")
    start_image = await get_app_setting("start_work_image")
    stop_image = await get_app_setting("stop_work_image")
    text = (
        "⚙️ <b>Управление работой</b>\n\n"
        f"Текущий режим: <b>{'🟢 START WORK' if enabled else '🔴 STOP WORK'}</b>\n\n"
        f"<b>Картинка Start Work:</b> {'✅ установлена' if start_image else '❌ нет'}\n"
        "<b>Сообщение Start Work:</b>\n" + start_text +
        f"\n\n<b>Картинка Stop Work:</b> {'✅ установлена' if stop_image else '❌ нет'}\n"
        "<b>Сообщение Stop Work:</b>\n" + stop_text
    )
    await replace_photo_with_text(callback, text, work_control_menu(enabled))
    await callback.answer()


async def _broadcast_work_message(callback: CallbackQuery, text: str, image_file_id: str = "") -> tuple[int, int]:
    sent = 0
    failed = 0
    for user_id in await list_approved_user_ids():
        try:
            if image_file_id:
                await callback.bot.send_photo(user_id, image_file_id, caption=text, reply_markup=main_menu())
            else:
                await callback.bot.send_message(user_id, text, reply_markup=main_menu())
            sent += 1
        except Exception:
            failed += 1
    return sent, failed


@router.callback_query(F.data == "work_start")
async def work_start_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await set_work_enabled(True)
    text = await get_app_setting("start_work_message")
    image_file_id = await get_app_setting("start_work_image")
    sent, failed = await _broadcast_work_message(callback, text, image_file_id)
    await callback.message.edit_text(
        f"🚀 <b>START WORK включён</b>\n\nУведомлено: <b>{sent}</b>\nНе доставлено: <b>{failed}</b>",
        reply_markup=work_control_menu(True),
    )
    await callback.answer("Приём заявок открыт")


@router.callback_query(F.data == "work_stop")
async def work_stop_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await set_work_enabled(False)
    text = await get_app_setting("stop_work_message")
    image_file_id = await get_app_setting("stop_work_image")
    sent, failed = await _broadcast_work_message(callback, text, image_file_id)
    await callback.message.edit_text(
        f"🛑 <b>STOP WORK включён</b>\n\nНовые заявки отключены. Уже выданные PayPal и текущие оплаты продолжают работать.\n\nУведомлено: <b>{sent}</b>\nНе доставлено: <b>{failed}</b>",
        reply_markup=work_control_menu(False),
    )
    await callback.answer("Приём новых заявок остановлен")


@router.callback_query(F.data.startswith("work_edit:"))
async def work_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    kind = callback.data.split(":", 1)[1]
    if kind not in {"start", "stop"}:
        await callback.answer("Неизвестный шаблон", show_alert=True)
        return
    await state.set_state(WorkMessageForm.text)
    await state.update_data(work_message_kind=kind)
    current = await get_app_setting(f"{kind}_work_message")
    await callback.message.edit_text(
        f"✏️ <b>Изменение текста {'Start Work' if kind == 'start' else 'Stop Work'}</b>\n\n"
        f"Текущий текст:\n{current}\n\nОтправьте новый текст одним сообщением. HTML-разметка поддерживается.",
        reply_markup=work_edit_cancel_menu(),
    )
    await callback.answer()


@router.message(WorkMessageForm.text)
async def work_edit_save(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст не может быть пустым.", reply_markup=work_edit_cancel_menu())
        return
    data = await state.get_data()
    kind = data.get("work_message_kind")
    image_file_id = await get_app_setting(f"{kind}_work_image") if kind in {"start", "stop"} else ""
    max_length = 1024 if image_file_id else 4000
    if len(text) > max_length:
        await message.answer(
            f"Текст слишком длинный. Максимум {max_length} символов" + (" при установленной картинке." if image_file_id else "."),
            reply_markup=work_edit_cancel_menu(),
        )
        return
    if kind not in {"start", "stop"}:
        await state.clear()
        return
    await set_app_setting(f"{kind}_work_message", text)
    await state.clear()
    await message.answer(
        f"✅ Текст {'Start Work' if kind == 'start' else 'Stop Work'} сохранён.",
        reply_markup=work_control_menu(await is_work_enabled()),
    )


@router.callback_query(F.data.startswith("work_image:"))
async def work_image_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    kind = callback.data.split(":", 1)[1]
    if kind not in {"start", "stop"}:
        await callback.answer("Неизвестный шаблон", show_alert=True)
        return
    current_image = await get_app_setting(f"{kind}_work_image")
    await state.set_state(WorkMessageForm.image)
    await state.update_data(work_message_kind=kind)
    await callback.message.edit_text(
        f"🖼 <b>Картинка {'Start Work' if kind == 'start' else 'Stop Work'}</b>\n\n"
        f"Сейчас: {'✅ установлена' if current_image else '❌ не установлена'}\n\n"
        "Отправьте новую картинку одним сообщением как фотографию.",
        reply_markup=work_image_edit_menu(kind, bool(current_image)),
    )
    await callback.answer()


@router.message(WorkMessageForm.image, F.photo)
async def work_image_save(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    kind = data.get("work_message_kind")
    if kind not in {"start", "stop"}:
        await state.clear()
        return
    current_text = await get_app_setting(f"{kind}_work_message")
    if len(current_text) > 1024:
        await message.answer(
            "Сначала сократите текст шаблона до 1024 символов — это лимит подписи к фотографии.",
            reply_markup=work_image_edit_menu(kind, bool(await get_app_setting(f"{kind}_work_image"))),
        )
        return
    file_id = message.photo[-1].file_id
    await set_app_setting(f"{kind}_work_image", file_id)
    await state.clear()
    await message.answer_photo(
        file_id,
        caption=f"✅ Картинка {'Start Work' if kind == 'start' else 'Stop Work'} сохранена.\n\n{current_text}",
        reply_markup=work_control_menu(await is_work_enabled()),
    )


@router.message(WorkMessageForm.image)
async def work_image_wrong_type(message: Message) -> None:
    await message.answer("Отправьте изображение именно как фотографию.")


@router.callback_query(F.data.startswith("work_image_delete:"))
async def work_image_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    kind = callback.data.split(":", 1)[1]
    if kind not in {"start", "stop"}:
        await callback.answer("Неизвестный шаблон", show_alert=True)
        return
    await set_app_setting(f"{kind}_work_image", "")
    await state.clear()
    await callback.message.edit_text(
        f"✅ Картинка {'Start Work' if kind == 'start' else 'Stop Work'} удалена.",
        reply_markup=work_control_menu(await is_work_enabled()),
    )
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
    stats = await get_period_statistics("all")
    await replace_photo_with_text(
        callback,
        "👥 <b>ПОЛЬЗОВАТЕЛИ И СТАТИСТИКА</b>\n\n"
        f"👥 Всего: <b>{counts.get('all', 0)}</b>\n"
        f"🟢 Одобрено: <b>{counts.get('approved', 0)}</b>\n"
        f"🟡 Ожидают: <b>{counts.get('pending', 0)}</b>\n"
        f"🚫 Заблокировано: <b>{counts.get('blocked', 0)}</b>\n\n"
        f"💳 Выдано PayPal: <b>{stats['issued']}</b>\n"
        f"✅ Успешных оплат: <b>{stats['successful']}</b>\n"
        f"↩️ Возвратов: <b>{stats['returns']}</b>\n"
        f"🚫 GS: <b>{stats['gs']}</b>\n"
        f"💸 Выплачено: <b>{stats['payout']:.2f}</b>\n\n"
        "Выберите список или найдите пользователя.",
        members_menu(counts),
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


async def _attach_request_display(requests) -> None:
    """Attach human-readable username and PayPal tag for admin list buttons."""
    for req in requests:
        user = await get_user(req.user_id)
        tag = await get_paypal_tag(req.paypal_tag_id) if getattr(req, "paypal_tag_id", None) else None
        if user and user.username:
            username = f"@{user.username}"
        elif user and user.full_name:
            username = user.full_name
        else:
            username = f"ID {req.user_id}"
        setattr(req, "_display_username", username)
        setattr(req, "_display_tag", tag.tag if tag else "—")


async def _attach_return_display(items) -> None:
    """Attach user, tag and amount to PayPal return rows."""
    for item in items:
        user = await get_user(item.user_id)
        tag = await get_paypal_tag(item.paypal_tag_id) if getattr(item, "paypal_tag_id", None) else None
        req = await get_request(item.request_id) if getattr(item, "request_id", None) else None
        if user and user.username:
            username = f"@{user.username}"
        elif user and user.full_name:
            username = user.full_name
        else:
            username = f"ID {item.user_id}"
        setattr(item, "_display_username", username)
        setattr(item, "_display_tag", tag.tag if tag else "—")
        setattr(item, "_display_amount", getattr(req, "amount", 0) or 0)


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


def normalize_paypal_tag(raw: str) -> str | None:
    tag = raw.strip().split()[0] if raw.strip() else ""
    if not tag:
        return None
    if not tag.startswith("@"):
        tag = "@" + tag
    if len(tag) < 3 or len(tag) > 255 or any(ch.isspace() for ch in tag):
        return None
    return tag


async def show_paypal_add_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    tag = data.get("paypal_add_tag")
    photo_file_id = data.get("paypal_add_photo")
    caption = (
        "<b>Проверьте данные</b>\n\n"
        f"💳 <code>{tag}</code>\n"
        f"🚻 Тип: <b>{'Мужской' if data.get('paypal_add_gender') == 'male' else 'Женский'}</b>\n"
        f"🖼 Фото: <b>{'Есть' if photo_file_id else 'Нет'}</b>"
    )
    if photo_file_id:
        await message.answer_photo(photo_file_id, caption=caption, reply_markup=paypal_add_confirm_menu())
    else:
        await message.answer(caption, reply_markup=paypal_add_confirm_menu())


@router.callback_query(F.data == "paypal_add_single")
async def paypal_add_single_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await state.set_state(PaypalAddForm.gender)
    await callback.message.answer("🚻 <b>Выберите тип добавляемого PayPal</b>", reply_markup=gender_choice_menu("paypal_add_gender"))
    await callback.answer()


@router.callback_query(PaypalAddForm.gender, F.data.startswith("paypal_add_gender:"))
async def paypal_add_gender_choice(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(paypal_add_gender=callback.data.split(":", 1)[1])
    await state.set_state(PaypalAddForm.tag)
    await callback.message.answer(
        "➕ <b>Добавить PayPal</b>\n\nВведите один PayPal-тег.\nНапример: <code>@MaxMuller123</code>",
        reply_markup=paypal_add_cancel_menu(),
    )
    await callback.answer()


@router.message(PaypalAddForm.tag)
async def paypal_add_tag_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    tag = normalize_paypal_tag(message.text or "")
    if not tag:
        await message.answer("Введите корректный PayPal-тег, например <code>@MaxMuller123</code>.", reply_markup=paypal_add_cancel_menu())
        return
    await state.update_data(paypal_add_tag=tag, paypal_add_photo=None)
    await state.set_state(PaypalAddForm.photo)
    await message.answer(
        f"💳 <code>{tag}</code>\n\n🖼 Прикрепите фотографию PayPal или нажмите «Пропустить».",
        reply_markup=paypal_add_photo_menu(),
    )


@router.message(PaypalAddForm.photo, F.photo)
async def paypal_add_photo_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await state.update_data(paypal_add_photo=message.photo[-1].file_id)
    await show_paypal_add_preview(message, state)


@router.message(PaypalAddForm.photo)
async def paypal_add_photo_wrong(message: Message) -> None:
    await message.answer("Отправьте изображение именно как фотографию или нажмите «Пропустить».", reply_markup=paypal_add_photo_menu())


@router.callback_query(F.data == "paypal_add_skip_photo")
async def paypal_add_skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    if not data.get("paypal_add_tag"):
        await callback.answer("Начните добавление заново", show_alert=True)
        return
    await state.update_data(paypal_add_photo=None)
    await show_paypal_add_preview(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "paypal_add_save")
async def paypal_add_save(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    tag = data.get("paypal_add_tag")
    if not tag:
        await callback.answer("Данные устарели. Начните заново.", show_alert=True)
        return
    item, duplicate = await add_paypal_tag(tag, data.get("paypal_add_photo"), data.get("paypal_add_gender", "male"))
    await state.clear()
    if duplicate:
        await callback.message.answer(f"⚠️ PayPal <code>{tag}</code> уже есть в базе.", reply_markup=paypal_database_menu(await get_paypal_database_counts()))
        await callback.answer("Дубликат", show_alert=True)
        return
    await callback.message.answer(f"✅ PayPal <code>{tag}</code> сохранён и добавлен в свободную базу.", reply_markup=paypal_database_menu(await get_paypal_database_counts()))
    await callback.answer("Сохранено")


@router.callback_query(F.data == "paypal_add_restart")
async def paypal_add_restart(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await state.set_state(PaypalAddForm.tag)
    await callback.message.answer("Введите PayPal заново:", reply_markup=paypal_add_cancel_menu())
    await callback.answer()


@router.callback_query(F.data == "paypal_add_cancel")
async def paypal_add_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.answer("Добавление отменено.", reply_markup=paypal_database_menu(await get_paypal_database_counts()))
    await callback.answer()


@router.callback_query(F.data == "paypal_add_bulk")
async def paypal_add_bulk_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await state.set_state(PaypalAddForm.gender)
    await state.update_data(paypal_add_bulk_mode=True)
    await callback.message.answer("🚻 <b>Выберите тип для всего списка</b>", reply_markup=gender_choice_menu("paypal_bulk_gender"))
    await callback.answer()


@router.callback_query(PaypalAddForm.gender, F.data.startswith("paypal_bulk_gender:"))
async def paypal_bulk_gender_choice(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(paypal_add_gender=callback.data.split(":", 1)[1])
    await state.set_state(PaypalAddForm.bulk)
    await callback.message.answer(
        "📥 <b>Массовое добавление</b>\n\nОтправьте PayPal-теги списком — каждый с новой строки или через пробел.\nФотографии при массовом добавлении не прикрепляются.",
        reply_markup=paypal_add_cancel_menu(),
    )
    await callback.answer()


@router.message(PaypalAddForm.bulk)
async def paypal_add_bulk_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    raw_items = (message.text or "").replace(",", " ").replace(";", " ").split()
    tags = []
    seen = set()
    invalid = 0
    for raw in raw_items:
        tag = normalize_paypal_tag(raw)
        if not tag:
            invalid += 1
            continue
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            tags.append(tag)
    if not tags:
        await message.answer("Не найдено ни одного корректного PayPal-тега.", reply_markup=paypal_add_cancel_menu())
        return
    data = await state.get_data()
    added, duplicates = await add_paypal_tags(tags, data.get("paypal_add_gender", "male"))
    await state.clear()
    await message.answer(
        "✅ <b>Массовое добавление завершено</b>\n\n"
        f"Добавлено: <b>{added}</b>\n"
        f"Уже были в базе: <b>{duplicates}</b>\n"
        f"Некорректных: <b>{invalid}</b>",
        reply_markup=paypal_database_menu(await get_paypal_database_counts()),
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
    await _attach_request_display(requests)
    titles = {
        "check": "🟠 Ожидают проверки оплаты",
        "payout": "🟢 Нужно выплатить",
        "paidout": "✅ Выплаченные за последние 24 часа",
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

    issued_caption = (
        "✅ <b>PayPal выдан</b>\n\n"
        f"Заявка: <b>#{req.id}</b>\n"
        f"Сумма: <b>{req.amount} €</b>\n"
        f"PayPal: <code>{tag.tag}</code>\n\n"
        "После оплаты нажмите кнопку ниже."
    )
    await callback.bot.send_photo(
        req.user_id,
        photo=tag.photo_file_id or FSInputFile(BANNERS["issued"]),
        caption=issued_caption,
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
    user = await get_user(user_id)
    tag = await get_paypal_tag(req.paypal_tag_id) if req and req.paypal_tag_id else None
    username = f"@{user.username}" if user and user.username else "без username"
    profile = f'<a href="tg://user?id={user_id}">Открыть профиль</a>'
    bot = callback_or_message.bot
    for admin_id in settings.admin_ids:
        await bot.send_message(
            admin_id,
            "💰 <b>Пользователь сообщил об оплате</b>\n\n"
            f"👤 Пользователь: {username}\n"
            f"🔗 {profile}\n"
            f"🆔 ID: <code>{user_id}</code>\n\n"
            f"💳 PayPal: <code>{tag.tag if tag else 'не найден'}</code>\n"
            f"🚻 Тип: {'👨 Мужской' if getattr(req, 'paypal_gender', 'male') == 'male' else '👩 Женский'}\n"
            f"💶 Сумма: <b>{req.amount} €</b>",
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
            photo=FSInputFile(BANNERS["issued"]),
            caption=(
                f"⚠️ <b>Оплата по заявке #{req.id} пока не найдена</b>\n\n"
                "PayPal остаётся у вас. Проверьте перевод и после этого снова "
                "нажмите кнопку «✅ Я оплатил», чтобы повторно отправить заявку на проверку."
            ),
            reply_markup=paid_button(req.id),
        )
    except Exception:
        pass
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=(
                    f"🔴 По заявке #{req.id} оплата не найдена.\n\n"
                    "Заявка возвращена пользователю для повторной отправки на проверку."
                ),
                reply_markup=payments_menu(await get_payment_counts()),
            )
        else:
            await callback.message.edit_text(
                f"🔴 По заявке #{req.id} оплата не найдена.\n\n"
                "Заявка возвращена пользователю для повторной отправки на проверку.",
                reply_markup=payments_menu(await get_payment_counts()),
            )
    except TelegramBadRequest:
        pass
    await callback.answer("Заявка возвращена пользователю")


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
    await replace_photo_with_text(callback, text, rates_menu(rules))
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
    await _attach_return_display(items)
    await render_screen(callback, "paypal", f"<b>↩️ Возвраты PayPal</b>\n\nОжидают проверки: <b>{len(items)}</b>", returns_menu(items))
    await callback.answer()


@router.callback_query(F.data.startswith("return_card:"))
async def return_card_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    item = await get_paypal_return(int(callback.data.split(":")[1]))
    if item is None: await callback.answer("Возврат не найден", show_alert=True); return
    req = await get_request(item.request_id); tag = await get_paypal_tag(item.paypal_tag_id); user = await get_user(item.user_id)
    username = f"@{user.username}" if user and user.username else (user.full_name if user and user.full_name else str(item.user_id))
    text = (f"<b>↩️ Возврат #{item.id}</b>\n\n👤 Пользователь: <b>{username}</b>\n🆔 ID: <code>{item.user_id}</code>\n"
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
    messages = {"returned": "✅ PayPal проверен и возвращён в работу.", "gestoppt": "🚫 PayPal отмечен как Gestop и исключён из выдачи.", "deleted": "🗑 PayPal удалён из активной базы."}
    try: await callback.bot.send_message(item.user_id, messages[action], reply_markup=back_home())
    except Exception: pass
    remaining_returns = await list_paypal_returns()
    await _attach_return_display(remaining_returns)
    await callback.message.edit_text(messages[action], reply_markup=returns_menu(remaining_returns)); await callback.answer("Готово")


@router.callback_query(F.data.startswith("return_release:"))
async def return_release_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id): return
    await _finish_return(callback, "returned", "PayPal пустой. Возвращён в работу.")


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
    await _attach_request_display(reqs)
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
                f"⚠️ <b>Через 30 минут администрация заберёт PayPal, которые ожидают оплаты</b>\n\n"
                f"Дата выдачи: <b>{day}</b>\nPayPal: <code>{tag.tag if tag else '—'}</code>\nСумма: <b>{req.amount} €</b>\n\n"
                "Выберите: он ещё нужен или его можно вернуть.", reply_markup=collection_choice_menu(req.id)); sent+=1
        except Exception: pass
    await callback.answer(f"Уведомлено: {sent}", show_alert=True)


@router.callback_query(F.data.startswith("collect_keep:"))
async def collect_keep_handler(callback: CallbackQuery) -> None:
    req=await confirm_paypal_keep(int(callback.data.split(":")[1]), callback.from_user.id)
    if req is None: await callback.answer("PayPal недоступен", show_alert=True); return
    await callback.message.edit_text("✅ Подтверждено: этот PayPal вам ещё нужен."); await callback.answer()


@router.callback_query(F.data.startswith("collect_take_ask:"))
async def collect_take_ask_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    day = callback.data.split(":", 1)[1]
    reqs = await get_working_requests_by_date(day)
    total = sum(req.amount for req in reqs)
    await callback.message.edit_caption(
        caption=(
            f"<b>⚠️ Забрать все PayPal в ожидании оплаты за {day}?</b>\n\n"
            f"Количество: <b>{len(reqs)}</b>\n"
            f"Общая сумма: <b>{total} €</b>\n\n"
            "Будут забраны только PayPal со статусом «ожидает оплаты». "
            "Заявки на проверке, ожидающие выплаты и завершённые заявки не затрагиваются."
        ),
        reply_markup=collect_take_confirm_menu(day),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("collect_take_confirm:"))
async def collect_take_confirm_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return
    day = callback.data.split(":", 1)[1]
    reqs = await get_working_requests_by_date(day)
    recalled = 0
    for req in reqs:
        item = await create_paypal_return(
            req.id, req.user_id, "admin_recall", "Забрал администратор для проверки",
        )
        if item is None:
            continue
        recalled += 1
        tag = await get_paypal_tag(req.paypal_tag_id)
        try:
            await callback.bot.send_message(
                req.user_id,
                f"ℹ️ Администратор забрал PayPal <code>{tag.tag if tag else '—'}</code> на проверку. "
                "До решения администратора он находится в разделе возвратов."
            )
        except Exception:
            pass
    remaining = await get_working_requests_by_date(day)
    await callback.message.edit_caption(
        caption=(
            f"<b>✅ PayPal переданы в возвраты для проверки</b>\n\n"
            f"Дата: <b>{day}</b>\n"
            f"Забрано: <b>{recalled}</b>\n"
            f"Осталось в ожидании оплаты: <b>{len(remaining)}</b>"
        ),
        reply_markup=working_day_menu(day, remaining),
    )
    await callback.answer(f"Забрано PayPal: {recalled}", show_alert=True)

@router.callback_query(F.data.startswith("working_card:"))
async def working_card_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, request_id_raw, day = callback.data.split(":", 2)
    req = await get_request(int(request_id_raw))
    if req is None or req.status != "paypal_issued" or req.paypal_tag_id is None:
        await callback.answer("Заявка уже не находится в работе", show_alert=True)
        return
    tag = await get_paypal_tag(req.paypal_tag_id)
    user = await get_user(req.user_id)
    username = f"@{user.username}" if user and user.username else "—"
    text = (
        f"<b>💳 PayPal в работе · заявка #{req.id}</b>\n\n"
        f"👤 Пользователь: <b>{username}</b>\n"
        f"🆔 Telegram ID: <code>{req.user_id}</code>\n"
        f"💳 PayPal: <code>{tag.tag if tag else '—'}</code>\n"
        f"💶 Сумма: <b>{req.amount} €</b>\n"
        f"🕒 Выдан: <b>{format_dt(tag.issued_at if tag else None)}</b>\n"
        f"📌 Статус: <b>выдан</b>"
    )
    await callback.message.edit_caption(
        caption=text,
        reply_markup=working_card_menu(req.id, day, req.user_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("working_money_received:"))
async def working_money_received_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, request_id_raw, day = callback.data.split(":", 2)
    req = await confirm_working_payment(int(request_id_raw), callback.from_user.id)
    if req is None:
        await callback.answer(
            "Не удалось подтвердить. Проверьте статус заявки и настройки процентов.",
            show_alert=True,
        )
        return
    tag = await get_paypal_tag(req.paypal_tag_id)
    user = await get_user(req.user_id)
    username = f"@{user.username}" if user and user.username else (user.full_name if user and user.full_name else str(req.user_id))
    balance = await get_user_balance(req.user_id)
    try:
        await callback.bot.send_message(
            req.user_id,
            "✅ <b>Платёж подтверждён</b>\n\n"
            f"💳 PayPal: <code>{tag.tag if tag else '—'}</code>\n"
            f"💶 Сумма: <b>{req.amount} €</b>\n"
            f"📊 Процент: <b>{req.payout_percent}%</b>\n"
            f"💰 Начислено в кошелёк: <b>{float(req.payout_amount or 0):.2f} USDT</b>\n"
            f"💼 Текущий баланс: <b>{balance['available']:.2f} USDT</b>",
            reply_markup=back_home(),
        )
    except Exception:
        pass
    remaining = await get_working_requests_by_date(day) if day != "search" else []
    text = (
        "✅ <b>Деньги подтверждены и начислены</b>\n\n"
        f"👤 Пользователь: <b>{username}</b>\n"
        f"💳 PayPal: <code>{tag.tag if tag else '—'}</code>\n"
        f"💶 Получено: <b>{req.amount} €</b>\n"
        f"📊 Процент: <b>{req.payout_percent}%</b>\n"
        f"💰 Начислено: <b>{float(req.payout_amount or 0):.2f} USDT</b>\n"
        f"💼 Баланс пользователя: <b>{balance['available']:.2f} USDT</b>"
    )
    if day == "search":
        await callback.message.edit_caption(caption=text, reply_markup=working_search_results_menu([]))
    else:
        await callback.message.edit_caption(caption=text, reply_markup=working_day_menu(day, remaining))
    await callback.answer("Начислено в кошелёк")


@router.callback_query(F.data.startswith("working_notify_ask:"))
async def working_notify_ask_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, request_id_raw, day = callback.data.split(":", 2)
    req = await get_request(int(request_id_raw))
    if req is None or req.status != "paypal_issued" or req.paypal_tag_id is None:
        await callback.answer("PayPal уже не находится в работе", show_alert=True)
        return
    tag = await get_paypal_tag(req.paypal_tag_id)
    await callback.message.edit_caption(
        caption=(
            "<b>⏳ Отправить индивидуальное предупреждение?</b>\n\n"
            f"PayPal: <code>{tag.tag if tag else '—'}</code>\n"
            f"Пользователь: <code>{req.user_id}</code>\n\n"
            "Пользователь получит сообщение, что PayPal будет забран через 30 минут."
        ),
        reply_markup=working_notify_confirm_menu(req.id, day),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("working_notify_confirm:"))
async def working_notify_confirm_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, request_id_raw, day = callback.data.split(":", 2)
    request_id = int(request_id_raw)
    req = await mark_collection_notified(request_id)
    if req is None or req.paypal_tag_id is None:
        await callback.answer("PayPal уже не находится в работе", show_alert=True)
        return
    tag = await get_paypal_tag(req.paypal_tag_id)
    try:
        await callback.bot.send_message(
            req.user_id,
            f"⚠️ <b>Внимание!</b>\n\n"
            f"Через <b>30 минут</b> PayPal <code>{tag.tag if tag else '—'}</code> будет возвращён в базу, "
            "если вы не завершите оплату.\n\n"
            "Если вы уже оплатили — нажмите <b>«✅ Я оплатил»</b>.\n"
            "Если PayPal больше не нужен — нажмите <b>«↩️ Вернуть PayPal»</b>.",
            reply_markup=collection_choice_menu(req.id),
        )
    except Exception:
        await callback.answer("Не удалось отправить уведомление", show_alert=True)
        return
    await callback.message.edit_caption(
        caption=(
            "<b>✅ Индивидуальное предупреждение отправлено</b>\n\n"
            f"PayPal: <code>{tag.tag if tag else '—'}</code>\n"
            f"Пользователь: <code>{req.user_id}</code>\n"
            "Срок: <b>30 минут</b>"
        ),
        reply_markup=working_card_menu(req.id, day, req.user_id),
    )
    await callback.answer("Пользователь уведомлён")


@router.callback_query(F.data.startswith("collect_return_ask:"))
async def collect_return_ask_handler(callback: CallbackQuery) -> None:
    request_id = int(callback.data.split(":")[1])
    req = await get_request(request_id)
    if req is None or req.user_id != callback.from_user.id or req.status != "paypal_issued":
        await callback.answer("PayPal уже обработан или недоступен", show_alert=True)
        return
    await callback.message.answer(
        "↩️ <b>Вернуть PayPal?</b>\n\nПосле подтверждения он сразу станет доступен другим пользователям.",
        reply_markup=collection_return_confirm_menu(request_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("collect_return_cancel:"))
async def collect_return_cancel_handler(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Действие отменено. PayPal остаётся у вас.")
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("collect_return_confirm:"))
async def collect_return_confirm_handler(callback: CallbackQuery) -> None:
    request_id = int(callback.data.split(":")[1])
    req, tag = await user_return_paypal_after_warning(request_id, callback.from_user.id)
    if req is None:
        await callback.answer("PayPal уже обработан или недоступен", show_alert=True)
        return
    user = await get_user(callback.from_user.id)
    username = f"@{user.username}" if user and user.username else "без username"
    await callback.message.edit_text(
        f"✅ PayPal <code>{tag.tag if tag else '—'}</code> возвращён в базу. Больше не переводите на него деньги."
    )
    for admin_id in settings.admin_ids:
        try:
            await callback.bot.send_message(
                admin_id,
                "🔄 <b>Пользователь самостоятельно вернул PayPal</b>\n\n"
                f"👤 Пользователь: <b>{username}</b>\n"
                f'🔗 Профиль: <a href="tg://user?id={req.user_id}">открыть пользователя</a>\n'
                f"🆔 Telegram ID: <code>{req.user_id}</code>\n"
                f"💳 PayPal: <code>{tag.tag if tag else '—'}</code>\n"
                f"💶 Сумма: <b>{req.amount} €</b>"
            )
        except Exception:
            pass
    await callback.answer("PayPal возвращён")


@router.callback_query(F.data.startswith("working_recall_ask:"))
async def working_recall_ask_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, request_id_raw, action, day = callback.data.split(":", 3)
    labels = {
        "available": "забрать PayPal и передать его в возвраты для проверки",
        "gestoppt": "пометить PayPal как Gestop",
        "deleted": "удалить PayPal из активной базы",
    }
    await callback.message.edit_caption(
        caption=(
            f"<b>⚠️ Подтверждение</b>\n\n"
            f"Вы действительно хотите {labels[action]}?\n\n"
            "PayPal будет сразу отозван у пользователя."
        ),
        reply_markup=working_recall_confirm_menu(int(request_id_raw), action, day),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("working_recall_confirm:"))
async def working_recall_confirm_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, request_id_raw, action, day = callback.data.split(":", 3)
    request_id = int(request_id_raw)
    if action == "available":
        source_req = await get_request(request_id)
        if source_req is None or source_req.status != "paypal_issued":
            await callback.answer("PayPal уже обработан или изменил статус", show_alert=True)
            return
        item = await create_paypal_return(
            request_id, source_req.user_id, "admin_recall", "Забрал администратор для проверки",
        )
        if item is None:
            await callback.answer("Не удалось передать PayPal в возвраты", show_alert=True)
            return
        req = source_req
        tag = await get_paypal_tag(source_req.paypal_tag_id)
    else:
        req, tag = await admin_recall_working_request(request_id, action, callback.from_user.id)
        if req is None:
            await callback.answer("PayPal уже обработан или изменил статус", show_alert=True)
            return
    user_messages = {
        "available": "ℹ️ Администратор забрал выданный вам PayPal на проверку. Он помещён в раздел возвратов.",
        "gestoppt": "ℹ️ Администратор забрал выданный вам PayPal и пометил его как Gestop.",
        "deleted": "ℹ️ Администратор забрал выданный вам PayPal и удалил его из активной базы.",
    }
    try:
        await callback.bot.send_message(
            req.user_id,
            f"{user_messages[action]}\n\n💳 <code>{tag.tag if tag else '—'}</code>",
            reply_markup=back_home(),
        )
    except Exception:
        pass
    reqs = await get_working_requests_by_date(day) if day != "search" else []
    await _attach_request_display(reqs)
    if day == "search":
        await callback.message.edit_caption(
            caption="✅ PayPal обработан. Выполните новый поиск или вернитесь к датам.",
            reply_markup=working_search_results_menu([]),
        )
    else:
        total = sum(r.amount for r in reqs)
        await callback.message.edit_caption(
            caption=f"<b>📅 PayPal в работе за {day}</b>\n\nКоличество: <b>{len(reqs)}</b>\nОбщая сумма: <b>{total} €</b>",
            reply_markup=working_day_menu(day, reqs),
        )
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("working_delete_day_ask:"))
async def working_delete_day_ask_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    day = callback.data.split(":", 1)[1]
    reqs = await get_working_requests_by_date(day)
    await callback.message.edit_caption(
        caption=(
            f"<b>⚠️ Удалить все PayPal за {day}?</b>\n\n"
            f"Будет удалено: <b>{len(reqs)}</b>\n\n"
            "Удаляются только PayPal, которые всё ещё имеют статус «выдан». "
            "Заявки на проверке оплаты, выплате и завершённые операции не затрагиваются."
        ),
        reply_markup=working_delete_day_confirm_menu(day),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("working_delete_day_confirm:"))
async def working_delete_day_confirm_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    day = callback.data.split(":", 1)[1]
    affected = await bulk_delete_working_day(day, callback.from_user.id)
    for user_id, paypal_tag in affected:
        try:
            await callback.bot.send_message(
                user_id,
                "ℹ️ Администратор отозвал и удалил выданный вам PayPal.\n\n"
                f"💳 <code>{paypal_tag}</code>\n\n"
                "Если вам нужен новый PayPal, создайте новую заявку.",
                reply_markup=back_home(),
            )
        except Exception:
            pass
    await callback.message.edit_caption(
        caption=f"✅ <b>Очистка за {day} завершена</b>\n\nУдалено PayPal: <b>{len(affected)}</b>",
        reply_markup=working_dates_menu(await get_working_dates()),
    )
    await callback.answer(f"Удалено: {len(affected)}", show_alert=True)


@router.callback_query(F.data.startswith("working_export:"))
async def working_export_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    day = callback.data.split(":", 1)[1]
    reqs = await get_working_requests_by_date(day)
    wb = Workbook()
    ws = wb.active
    ws.title = "PayPal в работе"
    ws.append(["Заявка", "PayPal", "Username", "Telegram ID", "Сумма EUR", "Дата выдачи", "Статус"])
    for req in reqs:
        tag = await get_paypal_tag(req.paypal_tag_id) if req.paypal_tag_id else None
        user = await get_user(req.user_id)
        ws.append([
            req.id,
            tag.tag if tag else "",
            f"@{user.username}" if user and user.username else "",
            req.user_id,
            req.amount,
            tag.issued_at.strftime("%d.%m.%Y %H:%M") if tag and tag.issued_at else "",
            "Выдан",
        ])
    for column in ws.columns:
        width = min(max(len(str(cell.value or "")) for cell in column) + 2, 35)
        ws.column_dimensions[column[0].column_letter].width = width
    buffer = BytesIO()
    wb.save(buffer)
    await callback.bot.send_document(
        callback.message.chat.id,
        document=BufferedInputFile(buffer.getvalue(), filename=f"paypal_working_{day}.xlsx"),
        caption=f"📄 PayPal в работе за {day}: {len(reqs)}",
    )
    await callback.answer("Экспорт готов")


@router.callback_query(F.data == "working_search")
async def working_search_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(WorkingSearch.query)
    await callback.message.edit_caption(
        caption=(
            "<b>🔍 Поиск PayPal в работе</b>\n\n"
            "Введите PayPal, username, имя пользователя или Telegram ID."
        ),
        reply_markup=working_search_cancel_menu(),
    )
    await callback.answer()


@router.message(WorkingSearch.query)
async def working_search_query_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    query = (message.text or "").strip()
    rows = await search_working_requests(query)
    await state.clear()
    await message.answer_photo(
        photo=FSInputFile(BANNERS["paypal"]),
        caption=f"<b>🔍 Результаты поиска</b>\n\nЗапрос: <code>{query}</code>\nНайдено: <b>{len(rows)}</b>",
        reply_markup=working_search_results_menu(rows),
    )


@router.callback_query(F.data == "broadcast_start")
async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    await state.clear(); await state.set_state(BroadcastForm.text)
    await replace_photo_with_text(
        callback,
        "📣 <b>НОВАЯ РАССЫЛКА</b>\n\nОтправьте текст сообщения.",
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]]),
    )
    await callback.answer()


@router.message(BroadcastForm.text)
async def broadcast_text(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): await state.clear(); return
    text_value=(message.html_text or message.text or '').strip()
    if not text_value: await message.answer("Введите текст сообщения."); return
    await state.update_data(broadcast_text=text_value); await state.set_state(BroadcastForm.photo)
    await message.answer("🖼 Прикрепите картинку или нажмите «Без картинки».", reply_markup=broadcast_photo_menu())


async def _broadcast_preview(message: Message, state: FSMContext):
    data=await state.get_data(); text_value=data.get('broadcast_text',''); photo=data.get('broadcast_photo')
    if photo: await message.answer_photo(photo, caption=text_value, reply_markup=broadcast_confirm_menu())
    else: await message.answer(text_value, reply_markup=broadcast_confirm_menu())


@router.message(BroadcastForm.photo, F.photo)
async def broadcast_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(broadcast_photo=message.photo[-1].file_id); await _broadcast_preview(message,state)


@router.callback_query(F.data == "broadcast_no_photo")
async def broadcast_no_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(broadcast_photo=None); await _broadcast_preview(callback.message,state); await callback.answer()


@router.callback_query(F.data == "broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    data=await state.get_data(); ids=await list_approved_user_ids(); sent=failed=0
    for uid in ids:
        try:
            if data.get('broadcast_photo'): await callback.bot.send_photo(uid, data['broadcast_photo'], caption=data.get('broadcast_text',''))
            else: await callback.bot.send_message(uid, data.get('broadcast_text',''))
            sent+=1
        except Exception: failed+=1
    await state.clear()
    has_image = bool(await get_app_setting("content_home_image", ""))
    await callback.message.answer(
        f"✅ Доставлено: <b>{sent}</b>\n❌ Не доставлено: <b>{failed}</b>",
        reply_markup=content_menu(has_image),
    )
    await callback.answer("Рассылка завершена")


@router.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    home_image = await get_app_setting("content_home_image", "")
    text = (
        "📣 <b>КОНТЕНТ И РАССЫЛКИ</b>\n\n"
        "Здесь можно создавать рассылки, менять основные тексты и картинку главного экрана без обновления кода.\n\n"
        "Подсказка: в приветствии можно использовать <code>{status}</code> — "
        "бот автоматически подставит статус работы."
    )
    await replace_photo_with_text(callback, text, content_menu(bool(home_image)))
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("admin_gs:"))
async def admin_gs_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id): await callback.answer("Нет доступа", show_alert=True); return
    request_id=int(callback.data.split(':')[1]); req=await get_request(request_id)
    if req is None or req.status != 'waiting_check': await callback.answer("Заявка недоступна", show_alert=True); return
    await state.set_state(GSForm.screenshot); await state.update_data(gs_request_id=request_id)
    await callback.message.answer("🚫 <b>GS (Goods & Services)</b>\n\nПрикрепите скриншот блокировки PayPal или пропустите.", reply_markup=gs_photo_menu(request_id)); await callback.answer()


async def _finish_gs(message_or_callback, state: FSMContext, screenshot: str | None):
    data = await state.get_data()
    request_id = int(data["gs_request_id"])
    admin_id = message_or_callback.from_user.id
    req = await mark_payment_gs(request_id, admin_id, screenshot)
    await state.clear()
    if req is None:
        return None

    notification = (
        "❌ <b>Платёж отправлен через Goods & Services.</b>\n\n"
        "Этот PayPal заблокирован и больше не используется. "
        "Не переводите на него деньги."
    )

    try:
        if screenshot:
            await message_or_callback.bot.send_photo(
                chat_id=req.user_id,
                photo=screenshot,
                caption=notification,
            )
        else:
            await message_or_callback.bot.send_message(
                chat_id=req.user_id,
                text=notification,
            )
    except Exception as exc:
        # Не прерываем обработку GS, если пользователь заблокировал бота
        # или Telegram временно не доставил сообщение.
        print(f"Failed to deliver GS notification to user {req.user_id}: {exc}")

    return req


@router.message(GSForm.screenshot, F.photo)
async def admin_gs_photo(message: Message, state: FSMContext) -> None:
    req=await _finish_gs(message,state,message.photo[-1].file_id)
    await message.answer("🚫 PayPal перемещён в раздел GS." if req else "Заявка уже обработана.", reply_markup=payments_menu(await get_payment_counts()))


@router.callback_query(F.data.startswith("admin_gs_skip:"))
async def admin_gs_skip(callback: CallbackQuery, state: FSMContext) -> None:
    req=await _finish_gs(callback,state,None)
    await callback.message.answer("🚫 PayPal перемещён в раздел GS." if req else "Заявка уже обработана.", reply_markup=payments_menu(await get_payment_counts())); await callback.answer()

# ==================== v1.7.0 CRM ====================
@router.callback_query(F.data == "global_search")
async def global_search_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    await state.clear()
    await state.set_state(GlobalSearchForm.query)
    await replace_photo_with_text(
        callback,
        "🔍 <b>Глобальный поиск</b>\n\nВведите PayPal-тег, @username, имя, Telegram ID, номер заявки или сумму:",
        global_search_cancel_menu(),
    )
    await callback.answer()


@router.message(GlobalSearchForm.query)
async def global_search_query_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    query = (message.text or "").strip()
    results = await global_admin_search(query)
    await state.clear()
    total = sum(len(v) for v in results.values())
    text = f"🔍 <b>Результаты поиска</b>\n\nЗапрос: <code>{query}</code>\nНайдено: <b>{total}</b>"
    if not total:
        text += "\n\nСовпадений нет."
    await message.answer(text, reply_markup=global_search_results_menu(results))


@router.callback_query(F.data.startswith("crm_user:"))
async def crm_user_card_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    user_id = int(callback.data.split(":")[1])
    user = await get_user(user_id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True); return
    stats = await get_user_crm_stats(user_id)
    username = f"@{user.username}" if user.username else "—"
    text = (
        "━━━━━━━━━━━━━━\n"
        "👤 <b>Карточка пользователя</b>\n\n"
        f"Username: <b>{username}</b>\n"
        f"Имя: <b>{user.full_name or '—'}</b>\n"
        f"Telegram ID: <code>{user.id}</code>\n"
        f"Статус: <b>{user.status}</b>\n\n"
        "📊 <b>Статистика</b>\n"
        f"Получено PayPal: <b>{stats['received']}</b>\n"
        f"Успешных оплат: <b>{stats['successful']}</b>\n"
        f"Возвратов: <b>{stats['returned']}</b>\n"
        f"GS: <b>{stats['gs']}</b>\n"
        f"Активных заявок: <b>{stats['active']}</b>\n"
        f"Общая сумма: <b>{stats['total_amount']:.2f} €</b>\n"
        "━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(text, reply_markup=crm_user_menu(user.id, user.status))
    await callback.answer()


@router.callback_query(F.data.startswith("crm_user_paypals:"))
async def crm_user_paypals_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    user_id = int(callback.data.split(":")[1])
    reqs = await get_user_requests(user_id)
    lines = ["💳 <b>PayPal пользователя</b>", ""]
    for req in reqs[:25]:
        tag = await get_paypal_tag(req.paypal_tag_id) if req.paypal_tag_id else None
        lines.append(f"#{req.id} · {req.amount} € · {tag.tag if tag else 'без PayPal'} · {req.status}")
    if len(lines) == 2: lines.append("Записей нет.")
    await callback.message.edit_text("\n".join(lines), reply_markup=crm_user_menu(user_id, (await get_user(user_id)).status))
    await callback.answer()


@router.callback_query(F.data == "statistics_menu")
async def statistics_menu_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    await replace_photo_with_text(
        callback,
        "📈 <b>Расширенная статистика</b>\n\nВыберите период:",
        statistics_period_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("stats_period:"))
async def statistics_period_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    period = callback.data.split(":")[1]
    data = await get_period_statistics(period)
    labels = {"today":"Сегодня", "yesterday":"Вчера", "7d":"7 дней", "30d":"30 дней", "all":"Всё время"}
    text = (
        f"📈 <b>Статистика · {labels.get(period, period)}</b>\n\n"
        f"📥 Заявок: <b>{data['requests']}</b>\n"
        f"💳 Выдано PayPal: <b>{data['issued']}</b>\n"
        f"✅ Успешных оплат: <b>{data['successful']}</b>\n"
        f"↩️ Возвратов: <b>{data['returns']}</b>\n"
        f"🚫 GS: <b>{data['gs']}</b>\n"
        f"💶 Оборот: <b>{data['turnover']:.2f} €</b>\n"
        f"💸 Выплаты: <b>{data['payout']:.2f} €</b>\n"
        f"👥 Активных пользователей: <b>{data['active_users']}</b>"
    )
    await callback.message.edit_text(text, reply_markup=statistics_period_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("quick_notify_menu:"))
async def quick_notify_menu_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    _, request_id, day = callback.data.split(":", 2)
    await callback.message.edit_caption(
        caption="📣 <b>Индивидуальное уведомление</b>\n\nВыберите готовое сообщение или напишите своё.",
        reply_markup=quick_notify_menu(int(request_id), day),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quick_notify:"))
async def quick_notify_send_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    _, request_id_raw, kind, day = callback.data.split(":", 3)
    req = await get_request(int(request_id_raw))
    if not req or req.status != "paypal_issued":
        await callback.answer("PayPal уже не в работе", show_alert=True); return
    tag = await get_paypal_tag(req.paypal_tag_id) if req.paypal_tag_id else None
    tag_text = tag.tag if tag else "этот PayPal"
    messages = {
        "friends": f"⚠️ Оплачивайте на <code>{tag_text}</code> только через <b>Friends & Family</b>.",
        "checking": f"🔍 Платёж на <code>{tag_text}</code> находится на проверке. Пожалуйста, ожидайте.",
        "received": f"✅ Деньги на <code>{tag_text}</code> поступили. Спасибо!",
    }
    try:
        await callback.bot.send_message(req.user_id, messages[kind])
    except Exception:
        await callback.answer("Не удалось отправить", show_alert=True); return
    await callback.answer("Уведомление отправлено", show_alert=True)


@router.callback_query(F.data.startswith("quick_notify_custom:"))
async def quick_notify_custom_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    _, request_id, day = callback.data.split(":", 2)
    await state.set_state(QuickNotifyForm.text)
    await state.update_data(request_id=int(request_id), day=day)
    await callback.message.answer("✍️ Введите сообщение для этого пользователя:")
    await callback.answer()


@router.message(QuickNotifyForm.text)
async def quick_notify_custom_send(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    req = await get_request(data["request_id"])
    if not req or req.status != "paypal_issued":
        await state.clear(); await message.answer("PayPal уже не находится в работе."); return
    try:
        await message.bot.send_message(req.user_id, message.text or "")
        await message.answer("✅ Индивидуальное сообщение отправлено.")
    except Exception:
        await message.answer("❌ Не удалось отправить сообщение.")
    await state.clear()


# ==================== v2.2: БАЛАНС И РУЧНЫЕ ВЫПЛАТЫ ====================

@router.callback_query(F.data.in_({"wallet", "my_balance"}))
async def wallet_handler(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    data = await get_user_balance(callback.from_user.id)
    provider = "🤖 CryptoBot" if data["method"] == "cryptobot" else "🚀 xRocket"
    last_text = "пока не было"
    if data["last"] is not None:
        last_text = f"{float(data['last'].total_amount):.2f} USDT · {format_dt(data['last'].created_at)}"
    text = (
        "💰 <b>КОШЕЛЁК</b>\n\n"
        f"💵 Доступно к выплате: <b>{data['available']:.2f} USDT</b>\n"
        f"💸 Способ получения: <b>{provider}</b>\n"
        f"✅ Выплачено всего: <b>{data['paid']:.2f} USDT</b>\n"
        f"📦 Количество выплат: <b>{data['count_paid']}</b>\n"
        f"📅 Последняя выплата: <b>{last_text}</b>"
    )
    await render_screen(callback, "profile", text, wallet_menu())
    await callback.answer()


@router.callback_query(F.data == "payout_method")
async def payout_method_handler(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    current = await get_user_payout_method(callback.from_user.id)
    provider = "🤖 CryptoBot" if current == "cryptobot" else "🚀 xRocket"
    await render_screen(
        callback, "profile",
        "💸 <b>СПОСОБ ПОЛУЧЕНИЯ ВЫПЛАТ</b>\n\n"
        f"Текущий способ: <b>{provider}</b>\n\n"
        "Вы можете изменить его в любой момент. Новый выбор применяется ко всем будущим выплатам.",
        payout_method_wallet_menu(current),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_payout_method:"))
async def set_payout_method_handler(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    method = callback.data.split(":", 1)[1]
    if not await set_user_payout_method(callback.from_user.id, method):
        await callback.answer("Не удалось изменить способ", show_alert=True)
        return
    provider = "🤖 CryptoBot" if method == "cryptobot" else "🚀 xRocket"
    await render_screen(
        callback, "profile",
        "✅ <b>Способ выплаты изменён</b>\n\n"
        f"Все последующие выплаты будут отправляться через: <b>{provider}</b>",
        payout_method_wallet_menu(method),
    )
    await callback.answer("Сохранено")


@router.callback_query(F.data.startswith("payout_history:"))
async def payout_history_handler(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    offset = int(callback.data.split(":", 1)[1])
    page_size = 10
    rows = await list_manual_payouts(callback.from_user.id, limit=page_size + 1, offset=offset)
    has_next = len(rows) > page_size
    rows = rows[:page_size]
    text = "💸 <b>ИСТОРИЯ ВЫПЛАТ</b>\n\n"
    text += "Все отправленные вам выплаты и чеки сохраняются здесь." if rows else "У вас пока нет выплат."
    await render_screen(callback, "profile", text, payout_history_menu(rows, offset, has_next, page_size))
    await callback.answer()


@router.callback_query(F.data.startswith("payout_history_card:"))
async def payout_history_card_handler(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    payout_id = int(callback.data.split(":", 1)[1])
    payout = await get_manual_payout(payout_id)
    if payout is None or payout.user_id != callback.from_user.id:
        await callback.answer("Выплата не найдена", show_alert=True)
        return
    provider = "🤖 CryptoBot" if payout.provider == "cryptobot" else "🚀 xRocket"
    text = (
        f"💸 <b>ВЫПЛАТА #{payout.id}</b>\n\n"
        f"💰 Сумма: <b>{float(payout.total_amount):.2f} USDT</b>\n"
        f"💳 Способ: <b>{provider}</b>\n"
        f"📅 Дата: <b>{format_dt(payout.created_at)}</b>\n"
        f"✅ Статус: <b>Выплачено</b>"
    )
    await render_screen(callback, "profile", text, payout_history_card_menu(payout.id))
    await callback.answer()


@router.callback_query(F.data.startswith("payout_receipt:"))
async def payout_receipt_handler(callback: CallbackQuery) -> None:
    if not await has_access(callback):
        return
    payout_id = int(callback.data.split(":", 1)[1])
    payout = await get_manual_payout(payout_id)
    if payout is None or payout.user_id != callback.from_user.id or not payout.source_message_id:
        await callback.answer("Чек недоступен", show_alert=True)
        return
    try:
        await callback.bot.copy_message(
            chat_id=callback.from_user.id,
            from_chat_id=payout.admin_id,
            message_id=payout.source_message_id,
        )
        await callback.answer("Чек отправлен повторно", show_alert=True)
    except Exception:
        await callback.answer("Не удалось открыть чек. Обратитесь в поддержку.", show_alert=True)


@router.callback_query(F.data.startswith("payouts_v22"))
async def payouts_v22_handler(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    parts = callback.data.split(":")
    offset = int(parts[1]) if len(parts) > 1 else 0
    rows, has_next = await list_users_with_available_balance(offset=offset, limit=10)
    totals = await get_payout_dashboard_counts()
    text = (
        "💼 <b>ЦЕНТР ВЫПЛАТ</b>\n\n"
        f"👥 Нужно выплатить: <b>{totals['users']}</b> пользователям\n"
        f"💰 Общий баланс: <b>{totals['total']:.2f} USDT</b>\n"
        f"✅ Выплат создано: <b>{totals['paid_count']}</b>\n"
        f"💵 Выплачено всего: <b>{totals['paid_total']:.2f} USDT</b>\n\n"
        "Выберите пользователя. Все его доступные начисления будут объединены в один чек."
    )
    await replace_photo_with_text(callback, text, payouts_users_menu(rows, offset, has_next))
    await callback.answer()


@router.callback_query(F.data.startswith("payout_user:"))
async def payout_user_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    await state.clear()
    user_id = int(callback.data.split(":")[1])
    data = await get_payout_user_details(user_id)
    if data is None:
        await callback.answer("Пользователь не найден", show_alert=True); return
    user = data["user"]
    name = f"@{user.username}" if user.username else (user.full_name or str(user.id))
    provider = "🤖 CryptoBot" if data["method"] == "cryptobot" else "🚀 xRocket"
    lines = [
        "👤 <b>ВЫПЛАТА ПОЛЬЗОВАТЕЛЮ</b>", "",
        f"Пользователь: <b>{name}</b>", f"ID: <code>{user.id}</code>",
        f"Способ: <b>{provider}</b>", "",
        f"💰 Общий баланс: <b>{data['total']:.2f} USDT</b>",
        f"🧾 Включено начислений: <b>{len(data['entries'])}</b>",
    ]
    if data["entries"]:
        lines.extend(["", "<b>Начисления:</b>"])
        for e in data["entries"][:15]:
            lines.append(f"• Заявка #{e.request_id} · {float(e.amount):.2f} USDT")
    await replace_photo_with_text(callback, "\n".join(lines), payout_user_menu(user_id, data["total"] > 0))
    await callback.answer()


@router.callback_query(F.data.startswith("manual_payout_start:"))
async def manual_payout_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True); return
    user_id = int(callback.data.split(":")[1])
    data = await get_payout_user_details(user_id)
    if data is None or data["total"] <= 0:
        await callback.answer("У пользователя нет доступного баланса", show_alert=True); return
    provider = "CryptoBot" if data["method"] == "cryptobot" else "xRocket"
    await state.set_state(ManualPayoutForm.check)
    await state.update_data(payout_user_id=user_id)
    await replace_photo_with_text(
        callback,
        "💸 <b>РУЧНАЯ ВЫПЛАТА</b>\n\n"
        f"Сумма: <b>{data['total']:.2f} USDT</b>\n"
        f"Способ: <b>{provider}</b>\n\n"
        f"Создайте общий чек на всю сумму в {provider} и пришлите его следующим сообщением. "
        "Можно отправить ссылку, текст, пересланное сообщение или изображение.\n\n"
        "После успешной отправки чека баланс станет нулевым, а все начисления перейдут в «Выплачено».",
        manual_payout_cancel_menu(user_id),
    )
    await callback.answer()


@router.message(ManualPayoutForm.check)
async def manual_payout_check_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    state_data = await state.get_data()
    user_id = int(state_data.get("payout_user_id", 0))
    details = await get_payout_user_details(user_id)
    if details is None or details["total"] <= 0:
        await state.clear(); await message.answer("❌ Баланс уже выплачен или пользователь не найден."); return
    try:
        await message.send_copy(chat_id=user_id)
    except Exception as exc:
        await message.answer(f"❌ Не удалось отправить чек пользователю: {exc}\nБаланс не списан.")
        return
    payout = await complete_manual_payout(user_id, message.from_user.id, message.message_id)
    if payout is None:
        await message.answer("❌ Не удалось завершить выплату. Баланс не списан.")
        return
    provider = "CryptoBot" if payout.provider == "cryptobot" else "xRocket"
    try:
        await message.bot.send_message(
            user_id,
            "✅ <b>ВЫПЛАТА ВЫПОЛНЕНА</b>\n\n"
            f"Сумма: <b>{float(payout.total_amount):.2f} USDT</b>\n"
            f"Способ: <b>{provider}</b>\n\n"
            "Чек отправлен сообщением выше. Все начисления включены в эту общую выплату.",
            reply_markup=back_home(),
        )
    except Exception:
        pass
    await state.clear()
    await message.answer(
        "✅ <b>Выплата завершена</b>\n\n"
        f"Пользователь ID: <code>{user_id}</code>\n"
        f"Сумма: <b>{float(payout.total_amount):.2f} USDT</b>\n"
        f"Способ: <b>{provider}</b>\n\n"
        "Баланс обнулён. Все связанные заявки перенесены в категорию «Выплачено»."
    )
