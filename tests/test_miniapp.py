import asyncio
import base64
import time
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy import select, func

from miniapp_fixture import runtime, signed_data, TEST_TOKEN, PHOTO
from app import db, keyboards
from app.config import settings
from app.miniapp_auth import validate_init_data, safe_html
from app.miniapp_transport import web_context


class AuthTests(unittest.TestCase):
    def test_valid_signature_and_exact_user(self):
        self.assertEqual(validate_init_data(signed_data(42), TEST_TOKEN)["id"], 42)

    def test_modified_id_invalid_signature(self):
        with self.assertRaises(ValueError):
            validate_init_data(signed_data(42).replace("42", "43"), TEST_TOKEN)

    def test_old_future_and_duplicate_fields_rejected(self):
        for data in (signed_data(auth_date=int(time.time())-3601), signed_data(auth_date=int(time.time())+100), signed_data()+"&auth_date=1"):
            with self.assertRaises(ValueError):
                validate_init_data(data, TEST_TOKEN)

    def test_html_keeps_safe_formatting_and_removes_active_content(self):
        result = safe_html('<b>Баланс</b><img src=x onerror=alert(1)><a href="javascript:alert(1)">bad</a><a href="https://t.me/profitgeld">support</a>')
        self.assertIn('<b>Баланс</b>', result)
        for unsafe in ('<img', 'onerror', 'javascript:'):
            self.assertNotIn(unsafe, result)
        self.assertIn('https://t.me/profitgeld', result)


class MiniAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_sessions = db.SessionLocal
        self.original_settings = (settings.admin_ids, settings.bot_token, settings.mini_app_url)
        self.app, self.engine, self.bot, self.dp, self.fake = await runtime()
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.bot.session.close()
        await self.engine.dispose()
        db.SessionLocal = self.original_sessions
        for key, value in zip(('admin_ids', 'bot_token', 'mini_app_url'), self.original_settings):
            object.__setattr__(settings, key, value)

    async def login(self, uid=1):
        response = await self.client.post('/api/session', json={'init_data': signed_data(uid)})
        data = await response.json()
        self.assertEqual(response.status, 200, data)
        self.token = data['token']
        self.view = data
        return data

    @property
    def headers(self):
        return {'Authorization': 'MiniApp '+self.token}

    async def act(self, **body):
        response = await self.client.post('/api/action', headers=self.headers,
            json={**body, 'request_id': 'test-'+str(time.time_ns()), 'version': self.view['version']})
        data = await response.json()
        self.assertEqual(response.status, 202, data)
        if self.app['miniapp'].tasks:
            await asyncio.wait_for(asyncio.gather(*list(self.app['miniapp'].tasks)), 10)
        response = await self.client.get('/api/state', headers=self.headers)
        self.view = await response.json()
        self.assertFalse(self.view.get('busy'))
        return self.view

    def button(self, text):
        buttons = [b for m in self.view['messages'] for row in m['rows'] for b in row]
        match = next((b for b in buttons if text.lower() in b['label'].lower()), None)
        self.assertIsNotNone(match, f'{text}: {[b["label"] for b in buttons]}')
        return match['action']

    def text(self):
        return '\n'.join(m['html'] for m in self.view['messages'])

    async def test_dt_payments_migrates_only_automatic_tags_and_matches_post(self):
        from datetime import datetime
        from app import dt_payments_channel as channel

        async with db.SessionLocal() as session, session.begin():
            old = await session.get(db.User, 1)
            old.dt_payments_tag = 'DT-OLD42'
            chosen = await session.get(db.User, 2)
            chosen.dt_payments_tag = 'DT-WOLF'
            chosen.dt_payments_tag_changed_at = datetime.utcnow()

        await db._backfill_dt_payments_tags()
        automatic = (await db.get_user(1)).dt_payments_tag
        self.assertRegex(automatic, r'^anonim-[0-9]{5,}$')
        self.assertIsNone((await db.get_user(1)).dt_payments_tag_changed_at)
        self.assertEqual((await db.get_user(2)).dt_payments_tag, 'DT-WOLF')
        await db._backfill_dt_payments_tags()
        self.assertEqual((await db.get_user(1)).dt_payments_tag, automatic)
        new = await db.get_or_create_user(445566778, 'not_a_public_tag')
        self.assertRegex(new.dt_payments_tag, r'^anonim-[0-9]{5,}$')
        self.assertNotEqual(new.dt_payments_tag, automatic)

        await channel.set_channel(-1001234567890)
        async with db.SessionLocal() as session, session.begin():
            request = db.Request(user_id=1, amount=170, status='waiting_check')
            session.add(request)
            await session.flush()
            rid = request.id
        await db.confirm_payment(rid, 999)
        self.assertEqual((await db.get_dt_payments_feed(1))[0]['tag'], automatic)
        await self.login(1)
        await self.act(nav='dt_payments')
        self.assertIn(automatic, self.text())
        self.assertTrue(await channel.deliver_one(self.bot))
        self.assertIn(f"#аноним{automatic.removeprefix('anonim-')}", self.fake.calls[-1].caption)
        self.assertEqual((await db.change_dt_payments_tag(1, 'FOX'))['tag'], 'DT-FOX')
        await db._backfill_dt_payments_tags()
        self.assertEqual((await db.get_user(1)).dt_payments_tag, 'DT-FOX')

    async def test_dt_payments_channel_setup_preview_and_refund(self):
        from datetime import datetime
        from aiogram.types import Chat, ChatMemberAdministrator, User
        from app import dt_payments_channel as channel

        chat_id = -1001234567890
        telegram = self.fake.make_request
        access = False

        async def mock_telegram(bot, method, timeout=None):
            if method.__api_method__ == "getChat":
                return Chat(id=chat_id, type="channel", title="Test & Channel")
            if method.__api_method__ == "getChatMember":
                return ChatMemberAdministrator(
                    user=User(id=bot.id, is_bot=True, first_name="Bot"), can_be_edited=False,
                    is_anonymous=False, can_manage_chat=True, can_delete_messages=False,
                    can_manage_video_chats=False, can_restrict_members=False, can_promote_members=False,
                    can_change_info=False, can_invite_users=False, can_post_stories=False,
                    can_edit_stories=False, can_delete_stories=False, can_post_messages=access,
                    can_edit_messages=access,
                )
            return await telegram(bot, method, timeout=timeout)

        self.assertFalse(await channel.deliver_one(self.bot))
        with patch.object(self.fake, "make_request", side_effect=mock_telegram):
            await self.login(999)
            await self.act(nav='admin_home')
            await self.act(action=self.button('Пользователи и статистика'))
            await self.act(action=self.button('DT Payments'))
            await self.act(action=self.button('Канал DT Payments'))
            await self.act(action=self.button('Посмотреть пример'))
            self.assertIn("#аноним48271", self.text())
            self.assertTrue(any(m['photo'] and not m['photo']['is_banner'] for m in self.view['messages']))
            self.assertFalse(await channel.deliver_one(self.bot))

            await self.act(action=self.button('Подключить канал'))
            await self.act(input={'text':'@Test_payments'})
            self.assertIn('где бот может', self.text())
            self.assertEqual(await db.get_app_setting(db.DT_PAYMENTS_CHANNEL), "")
            access = True
            await self.act(input={'text':'@Test_payments'})
            self.assertIn('Test &amp; Channel', self.text())
        self.assertEqual(await db.get_app_setting(db.DT_PAYMENTS_CHANNEL), str(chat_id))

        async with db.SessionLocal() as session, session.begin():
            user = await session.get(db.User, 1)
            user.dt_payments_tag = 'DT-DESIGN'
            user.dt_payments_tag_changed_at = datetime.utcnow()
            checked = db.Request(user_id=1, amount=150, status="waiting_check")
            direct = db.Request(user_id=1, amount=250, status="paypal_issued")
            session.add_all([checked, direct])
            await session.flush()
            checked_id, direct_id = checked.id, direct.id

        self.assertIsNotNone(await db.confirm_payment(checked_id, 999))
        self.assertIsNone(await db.confirm_payment(checked_id, 999))
        self.assertIsNotNone(await db.confirm_working_payment(direct_id, 999))
        self.assertTrue(await channel.deliver_one(self.bot))
        photo_calls = [m for m in self.fake.calls if m.__api_method__ == 'sendPhoto' and m.chat_id == chat_id]
        self.assertEqual(len(photo_calls), 1)
        self.assertIn('Новый профит', photo_calls[0].caption)
        self.assertIn('Сумма: <b>150€</b>', photo_calls[0].caption)
        self.assertIn('REG EU', photo_calls[0].caption)
        self.assertIn('@DT_TEAM_PAYPAL_BOT', photo_calls[0].caption)
        self.assertIn('DT-DESIGN', photo_calls[0].caption)
        self.assertNotIn('МСК', photo_calls[0].caption)
        self.assertNotIn('demo_member', photo_calls[0].caption)

        # Pause drops the pending item and still corrects an existing post.
        await channel.set_channel(None)
        self.assertFalse(await channel.deliver_one(self.bot))
        self.assertEqual((await db.refund_confirmed_payment(checked_id, 999))[1], 'refunded')
        self.assertTrue(await channel.deliver_one(self.bot))
        self.assertFalse(await channel.deliver_one(self.bot))
        edits = [m for m in self.fake.calls if m.__api_method__ == 'editMessageCaption' and m.chat_id == chat_id]
        self.assertEqual(len(edits), 1)
        self.assertIn('Оплата возвращена', edits[0].caption)
        self.assertEqual(await channel.channel_counts(), {'refunded':1, 'skipped':1})

    async def test_happy_hours_edit_preview_confirm_and_stale_draft(self):
        from datetime import datetime, timedelta
        from app import handlers
        from zoneinfo import ZoneInfo
        start = datetime(2026, 11, 23, 14, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        end = start + timedelta(hours=2)
        window = (start, end, datetime.utcnow(), datetime.utcnow()+timedelta(hours=2))
        text = "Новый пост & новость\n{start}–{end} МСК. От {min_amount} € — {percent}%."
        await db.set_app_setting('happy_hours_text', '<b>Старый пост</b> {percent}%')
        await db.set_app_setting('happy_hours_photo', 'test-happy-photo')
        with patch.object(handlers, '_happy_hours_window', return_value=window):
            await self.login(999)
            await self.act(nav='admin_home')
            await self.act(action=self.button('HAPPY HOURS'))
            await self.act(action=self.button('Предпросмотр'))
            edit = await self.act(action=self.button('Изменить текст'))
            self.assertEqual(edit['form']['initial'], 'Старый пост {percent}%')
            await self.act(input={'text':edit['form']['initial']})
            self.assertEqual(await db.get_app_setting('happy_hours_text'), '<b>Старый пост</b> {percent}%')
            await self.act(action=self.button('К запуску'))
            self.assertIn('Старый пост', self.text())
            await self.act(action=self.button('Изменить текст'))
            await self.act(input={'text':text})
            rendered = "Новый пост &amp; новость\n14:00–16:00 МСК. От 100 € — 80%."
            self.assertIn(rendered, self.text())
            self.assertIsNotNone(self.view['messages'][0]['photo'])
            await self.act(action=self.button('К запуску'))
            self.assertIn(rendered, self.text())
            self.assertIsNone(await db.get_open_happy_hours_campaign())
            await db.set_app_setting('happy_hours_text', 'Другой пост {percent}%')
            await self.act(action=self.button('Запустить и разослать'))
            self.assertIsNone(await db.get_open_happy_hours_campaign())
            await self.act(action=self.button('Изменить текст'))
            await self.act(input={'text':text})
            await self.act(action=self.button('К запуску'))
            await self.act(action=self.button('Запустить и разослать'))
            campaign = await db.get_open_happy_hours_campaign()
            self.assertIn('{percent}', campaign.broadcast_text)
            sends = [m for m in self.fake.calls if m.__api_method__ == 'sendPhoto' and m.chat_id == 1]
            self.assertEqual([m.caption for m in sends], [rendered])
            await self.act(action=self.button('Пост следующей акции'))
            await self.act(input={'text':'Будущий пост'})
            self.assertFalse(any('К запуску' in b['label'] for m in self.view['messages'] for row in m['rows'] for b in row))
            self.assertEqual((await db.get_open_happy_hours_campaign()).broadcast_text, campaign.broadcast_text)

    async def test_happy_hours_chat_template_is_plain_and_old_code_pastes_are_unwrapped(self):
        from datetime import datetime, timezone
        from aiogram.types import CallbackQuery, Chat, Message, MessageEntity, Update, User
        from app.handlers import _render_happy_hours_text
        admin = User(id=999, is_bot=False, first_name="Admin")
        message = Message(message_id=81, date=datetime.now(timezone.utc), chat=Chat(id=999, type="private"),
                          from_user=admin, text="Меню")
        current = 'Сегодня {percent}% & дальше\nДо {end}'
        stored = 'Сегодня {percent}% &amp; дальше\nДо {end}'
        await db.set_app_setting('happy_hours_text', '<pre>'+stored+'</pre>')
        callback = CallbackQuery(id="edit-template", from_user=admin, chat_instance="test", message=message,
                                 data="happy_hours_edit_text")
        await self.dp.feed_update(self.bot, Update(update_id=81, callback_query=callback))
        sent = [m for m in self.fake.calls if m.__api_method__ == 'sendMessage' and m.chat_id == 999]
        self.assertEqual(sent[-1].text, current)
        self.assertIsNone(sent[-1].parse_mode)
        for wrapper in ('<pre>{}</pre>', '<code>{}</code>', '<pre><code class="language-text">{}</code></pre>'):
            self.assertEqual(_render_happy_hours_text(wrapper.format(stored), '13:00', '17:00', 100, 80),
                             'Сегодня 80% &amp; дальше\nДо 17:00')
        inline = '<b>Пост</b> <code>A</code> или <code>B</code>'
        self.assertEqual(_render_happy_hours_text(inline, '13:00', '17:00', 100, 80), inline)
        reply = message.model_copy(update={'text':current,'message_id':82,
                                           'entities':[MessageEntity(type='pre', offset=0, length=len(current))]})
        await self.dp.feed_update(self.bot, Update(update_id=82, message=reply))
        self.assertEqual(await db.get_app_setting('happy_hours_text'), stored)
        self.assertIsNone(await db.get_open_happy_hours_campaign())

    async def test_happy_hours_chat_post_preserves_telegram_formatting(self):
        from datetime import datetime, timezone
        from aiogram.types import Chat, Message, MessageEntity, Update, User
        from app.handlers import HappyHoursForm
        admin = User(id=999, is_bot=False, first_name="Admin")
        state = self.dp.fsm.get_context(bot=self.bot, chat_id=999, user_id=999)
        await state.set_state(HappyHoursForm.text)
        await state.update_data(happy_original='Старый')
        await db.set_app_setting('happy_hours_text', 'Старый')
        msg = Message(message_id=77, date=datetime.now(timezone.utc), chat=Chat(id=999, type="private"),
                      from_user=admin, text='Пост {percent}%!', entities=[MessageEntity(type='bold', offset=0, length=4)])
        await self.dp.feed_update(self.bot, Update(update_id=77, message=msg))
        self.assertEqual(await db.get_app_setting('happy_hours_text'), '<b>Пост</b> {percent}%!')
        sent = [m for m in self.fake.calls if m.__api_method__ == 'sendMessage' and m.chat_id == 999]
        self.assertEqual(sent[-1].text, '<b>Пост</b> 80%!')
        self.assertIn('happy_hours_edit_text', [b.callback_data for row in sent[-1].reply_markup.inline_keyboard for b in row])
        self.assertIsNone(await db.get_open_happy_hours_campaign())

    async def test_happy_hours_parallel_edit_preserves_newer_post(self):
        await db.set_app_setting('happy_hours_text', 'Общий черновик')
        await self.login(999)
        await self.act(nav='admin_home')
        await self.act(action=self.button('HAPPY HOURS'))
        await self.act(action=self.button('Изменить текст'))
        await db.set_app_setting('happy_hours_text', 'Правка другого админа')
        await self.act(input={'text':'Моя правка'})
        self.assertIn('Другой администратор изменил пост', self.text())
        await self.act(action=self.button('Изменить текст'))
        self.assertEqual(self.view['form']['initial'], 'Правка другого админа')

    async def test_admin_rope_trials_are_private_resumable_and_available_on_pause(self):
        url = '/api/rope/test'
        start = dict(action='start', request_id='test-admin-rope-start', previous_id=0)
        self.assertEqual((await self.client.get(url)).status, 401)
        await self.login()
        self.assertEqual((await self.client.get(url, headers=self.headers)).status, 403)
        self.assertEqual((await self.client.post(url, json=start, headers=self.headers)).status, 403)
        self.assertEqual((await self.client.post('/api/action', json={'nav':'rope_test'}, headers=self.headers)).status, 403)
        async with db.SessionLocal() as session, session.begin():
            (await session.get(db.User, 999)).status = 'pending'
        await self.login(999)
        view = await self.act(nav='rope_test')
        self.assertEqual(view['route'], 'rope_test')
        self.assertFalse(view['wheel']['enabled'])
        self.assertEqual((await (await self.client.get(url, headers=self.headers)).json())['remaining'], 3)
        denied = await self.client.post('/api/rope', json=start, headers=self.headers)
        self.assertEqual(denied.status, 403)
        result = await (await self.client.post(url, json=start, headers=self.headers)).json()
        self.assertEqual(result['remaining'], 2)
        await self.login(999)
        self.assertEqual(result, await (await self.client.get(url, headers=self.headers)).json())
        self.assertEqual(result, await (await self.client.post(url, json=start, headers=self.headers)).json())

    async def test_admin_wheel_trials_when_campaign_paused(self):
        path = '/api/wheel/test'
        self.assertEqual((await self.client.get(path)).status, 401)
        await self.login()
        self.assertEqual((await self.client.get(path, headers=self.headers)).status, 403)
        self.assertEqual((await self.client.post(path, json={'request_id':'demo-trial-request'}, headers=self.headers)).status, 403)
        self.assertEqual((await self.client.post('/api/action', json={'nav':'wheel_test'}, headers=self.headers)).status, 403)
        async with db.SessionLocal() as session, session.begin():
            (await session.get(db.User, 999)).status = 'pending'
        await self.login(999)
        view = await self.act(nav='wheel_test')
        self.assertFalse(view['wheel']['enabled'])
        self.assertEqual(view['trials']['remaining'], 3)
        for payload in ({'request_id':None}, {'request_id':'demo-trial-request', 'user_id':1}):
            self.assertEqual((await self.client.post(path, json=payload, headers=self.headers)).status, 400)
        for i in range(3):
            payload = {'request_id': f'admin-demo-request-{i}'}
            spin = await self.client.post(path, json=payload, headers=self.headers)
            self.assertEqual(spin.status, 200)
            self.assertEqual((await spin.json())['wheel']['remaining'], 2-i)
        await self.login(999)
        self.assertEqual((await self.act(nav='wheel_test'))['trials']['remaining'], 0)
        replay = await self.client.post(path, json=payload, headers=self.headers)
        self.assertEqual((await replay.json())['result']['id'], 3)
        self.assertEqual((await self.client.post(path, json={'request_id':'extra-demo-request'}, headers=self.headers)).status, 409)

    async def test_home_reads_real_balances_and_support_launcher_order(self):
        data = await self.login()
        self.assertEqual(data['summary']['held'], 70)
        self.assertEqual(data['summary']['available'], 105)
        rows = keyboards.main_menu().inline_keyboard
        self.assertIn('Поддержка', rows[-2][0].text)
        self.assertEqual(rows[-1][0].web_app.url, 'https://example.test/app')
        self.assertFalse(self.fake.calls)

    async def test_anonymous_forged_and_foreign_origin_blocked(self):
        self.assertEqual((await self.client.get('/api/state')).status, 401)
        self.assertEqual((await self.client.post('/api/session', json={'init_data': 'user=anything'})).status, 401)
        self.assertEqual((await self.client.post('/api/session', json={'init_data': signed_data()}, headers={'Origin':'https://evil.example'})).status, 403)

    async def test_member_cannot_open_admin_or_forge_callback(self):
        await self.login()
        response = await self.client.post('/api/action', headers=self.headers, json={'action':'admin_confirm_same:1','request_id':'unique-request-1234','version':self.view['version']})
        self.assertEqual(response.status, 409)
        response = await self.client.post('/api/action', headers=self.headers, json={'nav':'admin_home','request_id':'admin-request-1234','version':self.view['version']})
        self.assertEqual(response.status, 403)

    async def test_live_events_are_personal_and_do_not_reset_form(self):
        await self.login()
        await self.act(nav='paypal_request')
        response = await self.client.get('/api/updates', headers=self.headers)
        self.assertEqual(response.status, 200)
        data = await response.json()
        self.assertEqual(data['summary']['available'],105)
        self.assertTrue(any(e['title']=='Оплата подтверждена' for e in data['events']))
        self.assertTrue(any(e['title']=='Деньги выведены с PayPal' for e in data['events']))
        self.assertFalse(any('@test_paypal_3' in e['body'] for e in data['events']))
        mini=self.app['miniapp'].sessions[self.token]
        self.assertEqual(await self.app['miniapp'].fsm(mini).get_state(),'PaypalRequestForm:amount')
        self.assertFalse(self.fake.calls)
        await self.login(3)
        self.assertEqual((await self.client.get('/api/updates',headers=self.headers)).status,403)
        self.assertEqual((await self.client.get('/api/updates')).status,401)

    async def test_live_wait_withdrawal_and_refund_events_follow_database(self):
        await self.login()
        service=self.app['miniapp']
        async def events():
            service.sessions[self.token].updates_at=0
            response=await self.client.get('/api/updates',headers=self.headers)
            self.assertEqual(response.status,200)
            return await response.json()
        await db.wait_paypal_withdrawal(1,0)
        data=await events()
        self.assertTrue(any(e['title']=='Ждём 24 часа' and 'МСК' in e['body'] for e in data['events']))
        self.assertEqual(data['summary']['held'],70)
        await db.mark_paypal_withdrawn(1,999)
        data=await events()
        self.assertEqual(data['summary']['available'],175)
        self.assertTrue(any(e['id'].startswith('withdrawn:1:') for e in data['events']))
        self.assertFalse(any(e['title']=='Ждём 24 часа' for e in data['events']))
        await db.refund_confirmed_payment(1,999)
        data=await events()
        self.assertEqual(data['summary']['available'],105)
        self.assertTrue(any(e['title']=='Оплата возвращена' for e in data['events']))

    async def test_request_minimum_gender_photo_and_no_duplicate(self):
        await self.login()
        await self.act(nav='paypal_request')
        self.assertEqual(self.view['form']['kind'], 'number')
        self.assertEqual(self.view['journey']['step'], 1)
        self.assertEqual(self.view['section'], 'my_paypals')
        form_key = self.view['form']['key']
        await self.act(input={'text':'30'})
        self.assertIn('40', self.text())
        self.assertEqual(self.view['form']['kind'], 'number')
        self.assertEqual(self.view['form']['key'], form_key)
        await self.act(input={'text':'100'})
        self.assertEqual(self.view['journey']['step'], 2)
        self.assertEqual(self.view['journey']['amount'], 100)
        await self.act(action=self.button('ЖЕНСК'))
        self.assertEqual(self.view['form']['kind'], 'photo')
        self.assertEqual(self.view['journey']['step'], 3)
        self.assertEqual(self.view['journey']['gender'], 'female')
        old_version = self.view['version']
        body={'input':{'photo':base64.b64encode(PHOTO).decode()},'request_id':'photo-request-123456','version':old_version}
        first=await self.client.post('/api/action',headers=self.headers,json=body)
        self.assertEqual(first.status,202)
        await asyncio.gather(*list(self.app['miniapp'].tasks))
        again=await self.client.post('/api/action',headers=self.headers,json=body)
        self.assertEqual(again.status,200)
        async with db.SessionLocal() as session:
            count=await session.scalar(select(func.count(db.Request.id)).where(db.Request.user_id==1,db.Request.status=='waiting_issue'))
        self.assertEqual(count,1)
        self.assertEqual(len([m for m in self.fake.calls if m.__api_method__=='sendPhoto' and m.chat_id==1]),1)

    async def test_stop_and_blocked_user_cannot_issue(self):
        await self.login()
        await db.set_work_enabled(False)
        await self.act(nav='paypal_request')
        self.assertIn('STOP', ' '.join(self.view['notices']))
        self.assertFalse(self.view['work'])
        self.assertIsNone(self.view['form'])
        await self.login(3)
        self.assertEqual(self.view['user']['status'],'blocked')
        self.assertIsNone(self.view['form'])

    async def test_request_back_revalidates_steps_without_creating_request(self):
        await self.login()
        await self.act(nav='paypal_request')
        await self.act(input={'text':'100'})
        await self.act(action=self.button('ЖЕНСК'))
        await self.act(nav='request_back')
        self.assertEqual(self.view['journey']['step'], 2)
        self.assertEqual(self.view['journey']['amount'], 100)
        self.assertIsNone(self.view['journey']['gender'])
        await self.act(nav='request_back')
        self.assertEqual(self.view['journey']['step'], 1)
        self.assertEqual(self.view['form']['kind'], 'number')
        async with db.SessionLocal() as session:
            count=await session.scalar(select(func.count(db.Request.id)).where(db.Request.user_id==1,db.Request.status=='waiting_issue'))
        self.assertEqual(count,0)

    async def test_forms_are_separate_from_bot(self):
        await self.login()
        key=StorageKey(bot_id=self.bot.id,chat_id=1,user_id=1)
        await self.dp.storage.set_state(key,'BotOnly:state')
        await self.act(nav='paypal_request')
        self.assertEqual(await self.dp.storage.get_state(key),'BotOnly:state')
        mini=self.app['miniapp'].sessions[self.token]
        self.assertEqual(await self.app['miniapp'].fsm(mini).get_state(),'PaypalRequestForm:amount')

    async def test_wallet_switch_and_admin_provider_totals(self):
        await self.login()
        await self.act(nav='wallet')
        self.assertIn('105.00', self.text())
        await self.act(action=self.button('СПОСОБ'))
        await self.act(action=self.button('xRocket'))
        self.assertEqual(await db.get_user_payout_method(1),'xrocket')
        await self.login(999)
        await self.act(nav='admin_home')
        await self.act(action=self.button('ВЫПЛАТЫ'))
        self.assertEqual(self.view['payouts']['cryptobot_total'],0)
        self.assertEqual(self.view['payouts']['xrocket_total'],245)

    async def test_action_consumed_and_old_screen_rejected(self):
        await self.login()
        old=self.view['version']
        await self.act(nav='wallet')
        response=await self.client.post('/api/action',headers=self.headers,json={'nav':'profile','request_id':'stale-request-1234','version':old})
        self.assertEqual(response.status,409)

    async def test_reopen_revokes_previous_session(self):
        await self.login()
        old_headers=self.headers
        await self.login()
        self.assertEqual((await self.client.get('/api/state',headers=old_headers)).status,401)

    async def test_media_is_scoped_to_session_and_owner(self):
        await self.login()
        photo=next(m['photo'] for m in self.view['messages'] if m['photo'])
        response = await self.client.get('/api/media/'+photo['id'],headers=self.headers)
        self.assertEqual(response.status,200)
        await response.read()
        await self.login(2)
        self.assertEqual((await self.client.get('/api/media/'+photo['id'],headers=self.headers)).status,404)

    async def test_manual_receipt_is_real_telegram_message_and_held_stays_held(self):
        await self.login(999)
        await self.act(nav='admin_home')
        await self.act(action=self.button('ВЫПЛАТЫ'))
        await self.act(action=self.button('ID 1'))
        await self.act(action=self.button('ВЫПЛАТИТЬ ОБЩИЙ'))
        self.assertEqual(self.view['form']['kind'],'receipt')
        await self.act(input={'text':'https://t.me/CryptoBot?start=test_receipt_only'})
        self.assertIn('Выплата завершена',self.text())
        balance=await db.get_user_balance(1)
        self.assertEqual(balance['available'],0)
        self.assertEqual(balance['held'],70)
        payouts=await db.list_manual_payouts(1)
        self.assertEqual(len(payouts),1)
        self.assertGreater(payouts[0].source_message_id,0)
        self.assertEqual(float(payouts[0].total_amount),105)
        sent=[m for m in self.fake.calls if m.__api_method__=='sendMessage']
        self.assertTrue(any(m.chat_id==999 and 'test_receipt' in m.text for m in sent))
        self.assertTrue(any(m.chat_id==1 and 'test_receipt' in m.text for m in sent))

    async def test_changed_balance_does_not_send_receipt_to_recipient(self):
        await self.login(999)
        await self.act(nav='admin_home')
        await self.act(action=self.button('ВЫПЛАТЫ'))
        await self.act(action=self.button('ID 1'))
        await self.act(action=self.button('ВЫПЛАТИТЬ ОБЩИЙ'))
        await db.mark_paypal_withdrawn(1,999)
        await self.act(input={'text':'TEST CHECK MUST NOT REACH MEMBER'})
        self.assertIn('изменились',self.text())
        self.assertEqual(await db.list_manual_payouts(1),[])
        self.assertFalse(any(getattr(m,'chat_id',None)==1 for m in self.fake.calls))

    async def test_autopost_time_edit_and_photo_field(self):
        await self.login(999)
        await self.act(nav='admin_home')
        await self.act(action=self.button('АВТОПОСТЫ'))
        await self.act(action=self.button('18:00'))
        await self.act(action=self.button('Изменить время'))
        await self.act(input={'text':'18:30'})
        self.assertIn('18:30',self.text())
        await self.act(action=self.button('Изменить картинку'))
        self.assertEqual(self.view['form']['kind'],'photo')
        await self.act(input={'photo':base64.b64encode(PHOTO).decode()})
        self.assertFalse(self.view['notices'])

    async def test_admin_id_search_opens_user_without_username(self):
        await self.login(999)
        await self.act(nav='admin_home')
        await self.act(action=self.button('ПОЛЬЗОВАТЕЛЬ ПО ID'))
        await self.act(input={'text':'2'})
        self.assertIn('2',self.text())
        self.assertIn('не указан',self.text())
        await self.act(action=self.button('ID 2'))
        self.assertIn('2',self.text())
        self.assertTrue(any('ВЫПЛАТ' in b['label'].upper() for m in self.view['messages'] for r in m['rows'] for b in r))

    async def test_200_paid_history_is_paginated(self):
        async with db.SessionLocal() as session:
            session.add_all([db.Request(user_id=1,amount=100,status='paid_out') for _ in range(200)])
            await session.commit()
        await self.login()
        await self.act(nav='my_paypals')
        await self.act(action=self.button('Выплаченные'))
        self.assertIn('200',self.text())
        await self.act(action=self.button('Далее'))
        self.assertIn('Страница 2 из 50',self.text())

    async def test_wait_then_withdraw_then_refund_share_bot_ledger(self):
        await self.login(999)
        await self.act(nav='admin_home')
        await self.act(action=self.button('РАБОТА С PAYPAL'))
        await self.act(action=self.button('Вывести с PayPal'))
        await self.act(action=self.button('НЕ ВЫВЕДЕНО'))
        await self.act(action=self.button('Ждём 24 часа'))
        self.assertIsNotNone((await db.get_request(1)).withdrawal_retry_at)
        self.assertEqual((await db.get_user_balance(1))['held'],70)
        self.assertTrue(any('24 часа' in (getattr(m,'text','') or '') and getattr(m,'chat_id',None)==1 for m in self.fake.calls))
        await self.act(action=self.button('деньги выведены'))
        self.assertEqual((await db.get_user_balance(1))['available'],175)
        self.assertEqual((await db.get_user_balance(1))['held'],0)
        await self.act(action=self.button('Оплата возвращена'))
        await self.act(action=self.button('Да, отменить начисление'))
        self.assertEqual((await db.get_user_balance(1))['available'],105)
        self.assertEqual((await db.get_request(1)).status,'payment_refunded')

    async def test_wheel_admin_activation_visibility_and_stale_toggle(self):
        from app import wheel
        await self.login(1)
        self.assertFalse(self.view['wheel']['enabled'])
        await self.act(nav='wheel')
        self.assertFalse(self.view['wheel']['enabled'])
        self.assertIn('выключена',self.text())
        await self.login(999)
        await self.act(nav='admin_home')
        await self.act(action=self.button('Игры DT'))
        self.assertIn('ВЫКЛЮЧЕНА',self.text())
        await self.act(action=self.button('Включить акцию'))
        self.assertTrue((await wheel.state(1))['enabled'])
        self.assertIn('ВКЛЮЧЕНА',self.text())
        await self.login(1)
        self.assertTrue(self.view['wheel']['enabled'])
        self.assertEqual(self.view['wheel']['available'],0)  # historical fixture payments excluded
        await self.act(nav='wheel')
        self.assertEqual(self.view['wheel']['history'],[])
        await self.login(999)
        await self.act(nav='admin_home')
        await self.act(action=self.button('Игры DT'))
        await self.act(action=self.button('Выключить акцию'))
        await self.login(1)
        self.assertFalse(self.view['wheel']['enabled'])

    async def test_games_reports_private_and_rope_only_debits_on_start(self):
        from app import wheel
        await wheel.set_enabled(True,999,0)
        async with db.SessionLocal() as session, session.begin():
            req=db.Request(user_id=1,amount=250,status="waiting_check")
            session.add(req)
            await session.flush()
        await db.confirm_payment(req.id,999)
        await db.mark_paypal_withdrawn(req.id,999)
        self.assertEqual((await self.client.get('/api/games/statistics')).status,401)
        await self.login(1)
        self.assertEqual((await self.client.get('/api/games/statistics',headers=self.headers)).status,403)
        await self.act(nav='rope')
        self.assertEqual((self.view['route'], self.view['section'], self.view['wheel']['balance']), ('rope','rope',250))
        await self.act(nav='wheel')
        self.assertEqual((self.view['route'], self.view['wheel']['balance']), ('wheel',250))
        for _ in range(2):
            data=await (await self.client.get('/api/rope',headers=self.headers)).json()
            self.assertEqual(data['balance'],250)
        body={'action':'start','request_id':'paid-rope-request-123','previous_id':0}
        for _ in range(2):
            data=await (await self.client.post('/api/rope',headers=self.headers,json=body)).json()
            self.assertEqual(data['balance'],150)
        self.assertEqual((await self.client.post('/api/rope',headers=self.headers,json={
            'action':'bank','id':data['run']['id'],'version':0,'points':12})).status,409)
        await self.login(2)
        self.assertEqual((await self.client.post('/api/rope',headers=self.headers,json={
            'action':'arm','id':data['run']['id'],'version':0})).status,409)
        await self.login(999)
        result=await (await self.client.get('/api/games/statistics',headers=self.headers)).json()
        self.assertEqual((result['rows'][0]['uid'],result['stats']['spent']),(1,100))
        result=await (await self.client.get('/api/games/statistics?uid=1',headers=self.headers)).json()
        self.assertEqual(result['rows'][0]['status'],'ready')

    async def test_wheel_api_cash_credit_replay_ownership_and_disabled_access(self):
        from app import wheel
        await wheel.set_enabled(True,999,0)
        async with db.SessionLocal() as s, s.begin():
            req=db.Request(user_id=1,amount=150,status='waiting_check')
            s.add(req);await s.flush()
        await db.confirm_payment(req.id,999)
        await db.mark_paypal_withdrawn(req.id,999)
        await self.login(1)
        body={'request_id':'wheel-api-retry-nonce-123'}
        with patch.object(wheel,'choose_prize',return_value='cash'):
            response=await self.client.post('/api/wheel/spin',headers=self.headers,json=body)
        self.assertEqual(response.status,200)
        first=await response.json()
        self.assertEqual(first['result']['cash'],20)
        balance=(await db.get_user_balance(1))['available']
        # Reopening invalidates the old UI session, but the DB request ID survives.
        await self.login(1)
        response=await self.client.post('/api/wheel/spin',headers=self.headers,json=body)
        self.assertEqual((await response.json())['result']['id'],first['result']['id'])
        self.assertEqual((await db.get_user_balance(1))['available'],balance)
        response=await self.client.post('/api/wheel/spin',headers=self.headers,json={**body,'user_id':2})
        self.assertEqual(response.status,400)
        await self.login(2)
        response=await self.client.get('/api/wheel',headers=self.headers)
        self.assertEqual((await response.json())['history'],[])
        response=await self.client.post('/api/wheel/spin',headers=self.headers,json=body)
        self.assertEqual(response.status,409)
        await self.login(3)
        self.assertEqual((await self.client.get('/api/wheel',headers=self.headers)).status,403)
        self.assertEqual((await self.client.post('/api/wheel/spin',headers=self.headers,json=body)).status,403)
        self.assertEqual((await self.client.get('/api/wheel')).status,401)
        await self.login(1)
        await wheel.set_enabled(False,999,1)
        self.assertEqual((await self.client.post('/api/wheel/spin',headers=self.headers,json={'request_id':'new-disabled-nonce-123'})).status,409)
        response=await self.client.post('/api/wheel/spin',headers=self.headers,json=body)
        self.assertEqual((await response.json())['result']['id'],first['result']['id'])
        response=await self.client.get('/api/updates',headers=self.headers)
        events=(await response.json())['events']
        self.assertTrue(any(e['title']=='Приз DT Колеса' and '20 USDT' in e['body'] for e in events))


if __name__=='__main__':
    unittest.main()
