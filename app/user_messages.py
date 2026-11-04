"""Admin-to-user text messages, addressed by a pinned Telegram ID."""
import asyncio
import secrets

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.db import get_user
from app.identity import user_id_query
from app.keyboards import user_identity_label

router = Router()
_locks: dict[tuple[int, int], asyncio.Lock] = {}
MAX_TEXT_UNITS = 3500


class UserMessageForm(StatesGroup):
    compose = State()
    confirm = State()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def _lock(state: FSMContext) -> asyncio.Lock:
    return _locks.setdefault((state.key.chat_id, state.key.user_id), asyncio.Lock())


def _draft_menu(nonce: str, confirm: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if confirm:
        rows.append([InlineKeyboardButton(text="📨 Отправить", callback_data=f"user_message_send:{nonce}")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"user_message_cancel:{nonce}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ К пользователю", callback_data=f"member_card:{user_id}")
    ]])


async def _show(callback: CallbackQuery, text: str, markup) -> None:
    # Plain text keeps both the recipient's name and the draft literal.
    if not callback.message.photo:
        try:
            await callback.message.edit_text(text, reply_markup=markup, parse_mode=None)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in exc.message.lower():
                return
    await callback.message.answer(text, reply_markup=markup, parse_mode=None)


@router.callback_query(F.data.startswith("user_message_start:"))
async def user_message_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, user_id = user_id_query(callback.data.split(":", 1)[1])
    user = await get_user(user_id) if user_id is not None else None
    if user is None:
        await callback.answer("Пользователь не найден в базе бота", show_alert=True)
        return
    await callback.answer()
    async with _lock(state):
        await state.clear()
        nonce = secrets.token_hex(8)
        await state.set_data({"recipient_id": user.id, "nonce": nonce})
        await state.set_state(UserMessageForm.compose)
        await _show(callback,
            f"💬 Сообщение через бота\n\nКому: {user_identity_label(user)}\n\n"
            "Пришлите текст сообщения. Затем появится предпросмотр с кнопкой отправки.\n"
            "Только текст, до 3500 символов (эмодзи могут занимать два).",
            _draft_menu(nonce))


@router.message(UserMessageForm.compose)
@router.message(UserMessageForm.confirm)
async def user_message_text(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    async with _lock(state):
        if await state.get_state() not in (UserMessageForm.compose.state, UserMessageForm.confirm.state):
            return
        data = await state.get_data()
        text = message.text or ""
        if not text.strip() or len(text.encode("utf-16-le")) // 2 > MAX_TEXT_UNITS:
            await message.answer("Пришлите непустой текст до 3500 символов. Для отмены используйте кнопку под черновиком.",
                                 reply_markup=_draft_menu(data["nonce"]))
            return
        user = await get_user(data["recipient_id"])
        if user is None:
            await state.clear()
            await message.answer("Пользователь больше не найден в базе. Отправка отменена.")
            return
        nonce = secrets.token_hex(8)
        await state.update_data(text=text, nonce=nonce)
        await state.set_state(UserMessageForm.confirm)
        await message.answer(
            f"📨 Предпросмотр\nКому: {user_identity_label(user)}\n\n"
            f"💬 Сообщение от администратора\n\n{text}\n\n"
            "Нажмите «Отправить» или пришлите новый текст, чтобы заменить черновик.",
            reply_markup=_draft_menu(nonce, confirm=True), parse_mode=None)


@router.callback_query(F.data.startswith("user_message_send:"))
async def user_message_send(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with _lock(state):
        data = await state.get_data()
        if (await state.get_state() != UserMessageForm.confirm.state
                or callback.data.split(":", 1)[1] != data.get("nonce")):
            await callback.answer("Этот черновик уже отправлен, отменён или заменён", show_alert=True)
            return
        recipient_id = data["recipient_id"]
        user = await get_user(recipient_id)
        if user is None:
            await state.clear()
            await callback.answer("Пользователь больше не найден в базе", show_alert=True)
            return
        await callback.answer()
        # Consume before network I/O: a timeout must never trigger an automatic resend.
        await state.clear()
        try:
            await callback.bot.send_message(
                recipient_id, "💬 Сообщение от администратора\n\n" + data["text"], parse_mode=None)
        except TelegramForbiddenError:
            result = "❌ Сообщение не отправлено. Telegram запретил доставку: пользователь мог заблокировать бота."
        except TelegramBadRequest:
            result = "❌ Telegram отклонил сообщение. Проверьте, что пользователь может открыть бота и нажать /start."
        except Exception:
            result = ("⚠️ Telegram не подтвердил отправку. Сообщение могло дойти. "
                      "Автоматического повтора не будет, чтобы не отправить его дважды.")
        else:
            result = "✅ Сообщение отправлено."
        await _show(callback, f"{result}\n\nПолучатель: {user_identity_label(user)}", _back_menu(recipient_id))


@router.callback_query(F.data.startswith("user_message_cancel:"))
async def user_message_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    async with _lock(state):
        data = await state.get_data()
        if (await state.get_state() not in (UserMessageForm.compose.state, UserMessageForm.confirm.state)
                or callback.data.split(":", 1)[1] != data.get("nonce")):
            await callback.answer("Этот черновик уже закрыт или заменён", show_alert=True)
            return
        await state.clear()
        await callback.answer("Отменено")
        await _show(callback, "Отправка отменена.", _back_menu(data["recipient_id"]))
