"""Admin-only CRUD and private previews for daily posts."""
from html import escape
from types import SimpleNamespace
from uuid import uuid4

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app import autoposts as posts
from app.db import is_work_enabled

router = Router(name="auto_posts")


class AutoPostForm(StatesGroup):
    value = State()


def is_admin(user_id):
    return user_id in settings.admin_ids


def button(label, data):
    return InlineKeyboardButton(text=label, callback_data=data)


def markup(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def panel(target, text, keyboard):
    if hasattr(target, "message") and hasattr(target, "data"):
        if not target.message.photo:
            try:
                await target.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
                return
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    return
        await target.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")


async def show_list(target, page=0):
    data = await posts.list_posts(page)
    rows = [[button(f"{'🟢' if p.enabled else '⏸'} {posts.display_time(p.minute)} · {p.name}",
                    f"ap:card:{p.id}:{data['page']}")] for p in data["rows"]]
    nav = []
    if data["page"]:
        nav.append(button("⬅️", f"ap:list:{data['page'] - 1}"))
    if data["page"] < data["last"]:
        nav.append(button("➡️", f"ap:list:{data['page'] + 1}"))
    if nav:
        rows.append(nav)
    rows.extend([[button("➕ Добавить пост", "ap:new")],
                 [button("🔄 Обновить", f"ap:list:{data['page']}")],
                 [button("⬅️ В админ-панель", "admin_home")]])
    work = "🟢 START WORK" if await is_work_enabled() else "🔴 STOP WORK"
    await panel(target,
        "📅 <b>Автопосты</b>\n\n"
        f"Режим: <b>{work}</b>\n"
        f"Постов: <b>{data['total']}</b> · страница {data['page'] + 1}/{data['last'] + 1}\n\n"
        "Каждый включённый пост отправляется ежедневно в своё время по Москве, "
        "только при START WORK, одобренным участникам бота.\n\n"
        "При STOP WORK отправка пропускается. Пропущенные посты позже не догоняются. "
        "После включения или изменения времени — ближайшее будущее срабатывание; "
        "каждый пост отправляется не более одного раза за московский день.\n\n"
        "Откройте пост, чтобы изменить время, текст или картинку.", markup(rows))


def card_menu(post, page=0):
    suffix = f"{post.id}:{post.revision}"
    return markup([
        [button("👁 Предпросмотр только мне", f"ap:preview:{suffix}:{page}")],
        [button("🕒 Изменить время", f"ap:edit:{suffix}:minute:{page}"),
         button("✏️ Изменить текст", f"ap:edit:{suffix}:body:{page}")],
        [button("🖼 Изменить картинку", f"ap:edit:{suffix}:photo:{page}"),
         button("🏷 Название", f"ap:edit:{suffix}:name:{page}")],
        [button("⏸ Выключить" if post.enabled else "▶️ Включить", f"ap:toggle:{suffix}:{page}")],
        [button("🗑 Удалить пост", f"ap:delete:{suffix}:{page}")],
        [button("🔄 Обновить", f"ap:card:{post.id}:{page}")],
        [button("⬅️ К постам", f"ap:list:{page}")],
    ])


async def show_card(target, post_id, page=0):
    post = await posts.get_post(post_id)
    if not post:
        await show_list(target, page)
        return
    last = await posts.last_run(post.id)
    history = "Ещё не запускался."
    if last:
        names = {"sending": "Начат; завершение не подтверждено", "complete": "Завершён",
                 "partial": "Завершён с ошибками доставки", "skipped": "Пропущен", "stopped": "Остановлен",
                 "interrupted": "Прерван", "error": "Ошибка"}
        history = (f"{last.day} · {names.get(last.status, last.status)}\n"
                   f"Доставлено: {last.sent}/{last.total}. Ошибок: {last.failed}.")
        if last.reason:
            history += "\n" + escape(last.reason)
    await panel(target,
        f"📅 <b>{escape(post.name)}</b>\n\n"
        f"🕒 Ежедневно в <b>{posts.display_time(post.minute)} МСК</b>\n"
        f"Состояние: <b>{'🟢 Включён' if post.enabled else '⏸ Выключен'}</b>\n"
        f"Картинка: {'есть' if post.photo else 'без картинки'}\n\n"
        f"<b>Текст под картинкой:</b>\n{escape(post.body)}\n\n"
        f"<b>Последний запуск:</b>\n{history}", card_menu(post, page))


async def ask_value(target, state, field):
    await state.set_state(AutoPostForm.value)
    await state.update_data(ap_field=field)
    data = await state.get_data()
    back = f"ap:card:{data['ap_id']}:{data.get('ap_page', 0)}" if data.get("ap_mode") == "edit" else "ap:list:0"
    rows = []
    if field == "photo":
        rows.append([button("⏭ Без картинки", "ap:nophoto")])
    rows.append([button("❌ Отмена", back)])
    prompts = {
        "name": "🏷 Введите название поста для админки (до 80 символов). Пользователи его не видят.",
        "minute": "🕒 Введите время ежедневной отправки по Москве: <code>13:00</code>.\n\n"
                  "Новое время применяется к будущим отправкам. Уже отправленный сегодня пост второй раз не отправится.",
        "body": "✏️ Пришлите текст поста (до 1024 символов Telegram, с учётом эмодзи).\n\n"
                "Это подпись под картинкой. Переносы строк и эмодзи сохраняются; HTML-теги не нужны. "
                "Под постом будет кнопка «💳 Получить PayPal».",
        "photo": "🖼 Пришлите картинку как фото в Telegram или нажмите «Без картинки». Текст остаётся отдельной подписью.",
    }
    await panel(target, prompts[field], markup(rows))


async def accept_value(message, state, value, *, preview_user_id=None):
    data = await state.get_data()
    field = data.get("ap_field")
    try:
        value = posts.validate_field(field, value)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    if data.get("ap_mode") == "edit":
        post = await posts.edit_post(data["ap_id"], data["ap_revision"], field, value)
        await state.clear()
        if post is None:
            await message.answer("Пост уже изменён или удалён. Откройте карточку заново.")
            return
        await message.answer("✅ Изменение сохранено.")
        await show_card(message, post.id, data.get("ap_page", 0))
        return
    if data.get("ap_mode") != "new":
        await state.clear()
        await message.answer("Черновик недоступен. Откройте «Автопосты» заново.")
        return
    draft = dict(data.get("ap_draft", {}))
    draft[field] = value
    await state.update_data(ap_draft=draft)
    fields = ["name", "minute", "body", "photo"]
    next_index = fields.index(field) + 1
    if next_index < len(fields):
        await ask_value(message, state, fields[next_index])
        return
    await state.set_state(None)  # Retain draft until Save, but stop accepting ordinary messages.
    await message.answer("👁 Предпросмотр нового поста — видите только вы.")
    try:
        await posts.send_post(message.bot, preview_user_id or message.from_user.id, SimpleNamespace(**draft))
    except Exception:
        await message.answer("Не удалось показать картинку. Черновик сохранён; картинку можно заменить после сохранения.")
    await message.answer(
        f"<b>{escape(draft['name'])}</b>\nЕжедневно в <b>{posts.display_time(draft['minute'])} МСК</b>, только при START WORK.\n\n"
        "Сохранить и включить этот пост?",
        parse_mode="HTML", reply_markup=markup([[button("✅ Сохранить и включить", "ap:save")],
                                                [button("❌ Отмена", "ap:list:0")]]))


@router.callback_query(F.data.startswith("ap:"))
async def auto_post_callback(callback, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    parts = callback.data.split(":")
    try:
        action = parts[1]
        if action == "list" and len(parts) == 3:
            page = int(parts[2])
            await state.clear()
            await callback.answer()
            await show_list(callback, page)
            return
        if action == "card" and len(parts) == 4:
            post_id, page = map(int, parts[2:])
            await state.clear()
            await callback.answer()
            await show_card(callback, post_id, page)
            return
        if action == "new" and len(parts) == 2:
            await state.clear()
            await state.update_data(ap_mode="new", ap_draft={}, ap_creation_key=str(uuid4()))
            await callback.answer()
            await ask_value(callback, state, "name")
            return
        if action == "save" and len(parts) == 2:
            data = await state.get_data()
            if data.get("ap_mode") != "new" or not all(k in data.get("ap_draft", {}) for k in ("name", "body", "minute", "photo")):
                raise ValueError("Черновик уже сохранён или недоступен.")
            post = await posts.create_post(data["ap_draft"], data["ap_creation_key"])
            await state.clear()
            await callback.answer("Пост сохранён")
            await show_card(callback, post.id)
            return
        if action == "nophoto" and len(parts) == 2:
            data = await state.get_data()
            if data.get("ap_field") != "photo" or await state.get_state() != AutoPostForm.value.state:
                raise ValueError("Откройте изменение картинки заново.")
            await callback.answer()
            await accept_value(callback.message, state, "", preview_user_id=callback.from_user.id)
            return
        if action not in {"preview", "edit", "toggle", "delete", "remove"}:
            raise ValueError("Неизвестная кнопка.")
        if len(parts) != (6 if action == "edit" else 5):
            raise ValueError("Неверная кнопка.")
        post_id, revision = map(int, parts[2:4])
        page = max(0, int(parts[-1]))
        post = await posts.get_post(post_id)
        if post is None or post.revision != revision:
            raise ValueError("Карточка устарела. Обновите список постов.")
        if action == "edit":
            field = parts[4]
            if field not in {"name", "minute", "body", "photo"}:
                raise ValueError("Неизвестное поле.")
            await state.clear()
            await state.update_data(ap_mode="edit", ap_id=post_id, ap_revision=revision, ap_page=page)
            await callback.answer()
            await ask_value(callback, state, field)
        elif action == "preview":
            await callback.answer("Предпросмотр только вам")
            try:
                await posts.send_post(callback.bot, callback.from_user.id, post)
            except Exception:
                await callback.message.answer("Не удалось показать пост. Проверьте картинку и попробуйте ещё раз.")
        elif action == "toggle":
            updated = await posts.edit_post(post_id, revision, "enabled", 0 if post.enabled else 1)
            if updated is None:
                raise ValueError("Пост уже изменён. Обновите карточку.")
            await callback.answer("Выключен" if not updated.enabled else "Включён")
            await show_card(callback, post_id, page)
        elif action == "delete":
            await callback.answer()
            await panel(callback,
                f"🗑 Удалить <b>{escape(post.name)}</b> из расписания?\n\nБудущие отправки будут отменены. Уже доставленные сообщения сохранятся.",
                markup([[button("✅ Удалить", f"ap:remove:{post_id}:{revision}:{page}")],
                        [button("❌ Отмена", f"ap:card:{post_id}:{page}")]]))
        elif action == "remove":
            if not await posts.delete_post(post_id, revision):
                raise ValueError("Пост уже изменён. Обновите карточку.")
            await state.clear()
            await callback.answer("Пост удалён")
            await show_list(callback, page)
    except (ValueError, IndexError) as exc:
        await callback.answer(str(exc) if isinstance(exc, ValueError) else "Неверная кнопка", show_alert=True)


@router.message(AutoPostForm.value)
async def auto_post_value(message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    field = data.get("ap_field")
    if field == "photo":
        if not message.photo:
            await message.answer("Пришлите изображение как фото или нажмите «Без картинки».")
            return
        value = message.photo[-1].file_id
    elif field == "minute":
        try:
            value = posts.parse_time(message.text or "")
        except ValueError as exc:
            await message.answer(str(exc))
            return
    else:
        value = message.text or ""
    await accept_value(message, state, value)
