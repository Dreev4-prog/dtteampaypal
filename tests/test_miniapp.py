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


if __name__=='__main__':
    unittest.main()
