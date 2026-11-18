"""Real ledger operations; optional dedicated local PostgreSQL concurrency suite.

WHEEL_TEST_POSTGRES=1 uses only 127.0.0.1:55439/postgres (disposable DB).
Never reads DATABASE_URL or production credentials for its test connection.
"""
import os
import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from collections import Counter

os.environ.setdefault("BOT_TOKEN", "123456:TEST_ONLY_NO_NETWORK")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1/test")
from sqlalchemy import select, func, event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app import db, wheel

POSTGRES = os.environ.get("WHEEL_TEST_POSTGRES") == "1"
LOCAL_PG = "postgresql+asyncpg://wheel_test@127.0.0.1:55439/postgres"


class WheelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(LOCAL_PG if POSTGRES else "sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            if POSTGRES:
                await conn.run_sync(db.Base.metadata.drop_all)
            await conn.run_sync(db.Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.patch = patch.object(db, 'SessionLocal', self.sessions)
        self.patch.start()
        async with self.sessions() as session, session.begin():
            session.add_all([db.User(id=1, status="approved"), db.User(id=2, status="approved", payout_method="xrocket"),
                             db.User(id=3, status="blocked"), db.RateRule(min_amount=40, percent=50),
                             db.RateRule(min_amount=50, percent=60), db.RateRule(min_amount=100, percent=70)])
        self.nonce = 0

    async def asyncTearDown(self):
        self.patch.stop()
        await self.engine.dispose()

    async def toggle(self, enabled):
        data = await wheel.state(1, admin=True)
        self.assertEqual(await wheel.set_enabled(enabled, 999, data['revision']), 'changed')

    async def request(self, amount=150, uid=1, direct=False, **extra):
        async with self.sessions() as session, session.begin():
            row = db.Request(user_id=uid, amount=amount, status='paypal_issued' if direct else 'waiting_check', **extra)
            session.add(row)
            await session.flush()
            return row

    async def confirm(self, amount=150, uid=1, direct=False, **extra):
        row = await self.request(amount, uid, direct, **extra)
        return await (db.confirm_working_payment(row.id,999) if direct else db.confirm_payment(row.id,999))

    async def earn(self, amount=150, uid=1):
        row = await self.confirm(amount,uid)
        self.assertEqual((await db.mark_paypal_withdrawn(row.id,999))[1], 'done')
        return row

    async def spin(self, prize='five', uid=1, nonce=None):
        self.nonce += 1
        with patch.object(wheel, 'choose_prize', return_value=prize):
            return await wheel.spin(uid, nonce or f'test-wheel-nonce-{self.nonce}')

    async def test_default_off_and_old_confirmations_excluded_even_if_withdrawn_after_launch(self):
        self.assertEqual(await wheel.state(1), {'enabled':False})
        old = await self.confirm(500)
        new_request = await self.request(150)  # issuance before launch is fine
        await self.toggle(True)
        await db.mark_paypal_withdrawn(old.id,999)
        self.assertEqual((await wheel.state(1))['qualified'],0)
        new = await db.confirm_payment(new_request.id,999)
        self.assertGreaterEqual(new.payment_confirmed_at, (await self._campaign()).started_at)
        await db.mark_paypal_withdrawn(new.id,999)
        self.assertEqual((await wheel.state(1))['available'],1)

    async def _campaign(self):
        async with self.sessions() as session:
            return await session.get(db.WheelCampaign,1)

    async def test_pause_excludes_new_confirmations_preserves_prior_eligibility_and_jackpot(self):
        await self.toggle(True)
        active = await self.confirm(150)
        await self.toggle(False)
        paused = await self.confirm(300)
        await db.mark_paypal_withdrawn(active.id,999)
        self.assertEqual(await wheel.state(1),{'enabled':False})
        with self.assertRaisesRegex(ValueError,'выключена'):
            await self.spin()
        await self.toggle(True)
        await db.mark_paypal_withdrawn(paused.id,999)
        data = await wheel.state(1)
        self.assertEqual((data['qualified'],data['available']),(150,1))
        await self.spin('jackpot')
        await self.toggle(False)
        await self.toggle(True)
        self.assertTrue((await wheel.state(1))['jackpot_claimed'])

    async def test_cumulative_progress_holds_retries_and_repeated_confirmation(self):
        await self.toggle(True)
        a = await self.confirm(100)
        b = await self.confirm(200,direct=True)
        self.assertIsNone(await db.confirm_payment(a.id,999))
        self.assertIsNone(await db.confirm_working_payment(b.id,999))
        await db.wait_paypal_withdrawal(a.id,0)
        self.assertEqual((await wheel.state(1))['waiting'],300)
        self.assertEqual((await wheel.state(1))['available'],0)
        await db.mark_paypal_withdrawn(a.id,999)
        self.assertEqual((await wheel.state(1))['progress'],100)
        await db.mark_paypal_withdrawn(b.id,999)
        self.assertEqual((await db.mark_paypal_withdrawn(b.id,999))[1],'already_done')
        self.assertEqual((await wheel.state(1))['available'],2)
        await self.spin('one')
        await self.spin('two')
        self.assertEqual((await wheel.state(1))['available'],0)
        with self.assertRaisesRegex(ValueError,'нет доступных'):
            await self.spin()

    async def test_fifo_coupons_once_plus_happy_hours_and_returned_coupon_restored(self):
        await self.toggle(True)
        await self.earn(450)
        for prize in ['one','two','four']:
            await self.spin(prize)
        async with self.sessions() as s,s.begin():
            happy=db.HappyHoursCampaign(start_at=datetime.utcnow()-timedelta(hours=1),end_at=datetime.utcnow()+timedelta(hours=1),
                 min_amount=100,percent=75,broadcast_text='test',activated_by=999)
            s.add(happy);await s.flush()
        a = await self.confirm(100,happy_hours_campaign_id=happy.id,happy_hours_percent=75)
        b = await self.confirm(100,direct=True)
        self.assertEqual((a.payout_percent,a.wheel_bonus_percent,a.payout_amount),(76,1,76))
        self.assertEqual((b.payout_percent,b.wheel_bonus_percent),(72,2))
        self.assertEqual((await db.refund_confirmed_payment(a.id,999))[1],'refunded')
        await self.toggle(False)
        c = await self.confirm(100)
        self.assertEqual((c.payout_percent,c.wheel_bonus_percent),(71,1))
        await self.toggle(True)
        data=await wheel.state(1)
        self.assertEqual([p['points'] for p in data['coupons']],[4])
        self.assertEqual((await db.get_payment_balance_entry(a.id)).status,'cancelled')

    async def test_refund_reduces_entitlement_without_deleting_awarded_prize(self):
        await self.toggle(True)
        a = await self.earn(300)
        await self.spin('cash')
        await self.spin('five')
        self.assertEqual((await db.refund_confirmed_payment(a.id,999))[1],'refunded')
        self.assertEqual((await db.refund_confirmed_payment(a.id,999))[1],'already_refunded')
        d=await wheel.state(1)
        self.assertEqual((d['available'],d['debt'],d['remaining']),(0,300,450))
        self.assertEqual((await db.get_user_balance(1))['available'],20)
        await self.earn(400)
        d=await wheel.state(1)
        self.assertEqual((d['available'],d['progress'],d['remaining']),(0,100,50))
        await self.earn(50)
        self.assertEqual((await wheel.state(1))['available'],1)

    async def test_cash_combines_with_payments_and_obeys_provider_snapshot(self):
        await self.toggle(True)
        await self.earn(150,uid=2)
        await self.spin('cash',uid=2)
        self.assertEqual((await db.get_user_balance(2))['available'],125)
        self.assertEqual((await db.get_payout_dashboard_counts())['xrocket_total'],125)
        details=await db.get_payout_user_details(2)
        self.assertEqual(len(details['entries']),2)
        snapshot=db.payout_entries_snapshot(details['entries'])
        self.assertIsNone(await db.complete_manual_payout(2,999,expected_entries=snapshot[:-1],expected_provider='xrocket'))
        payout=await db.complete_manual_payout(2,999,expected_entries=snapshot,expected_provider='xrocket')
        self.assertEqual((payout.total_amount,payout.provider),(125,'xrocket'))
        self.assertIsNone(await db.complete_manual_payout(2,999))
        self.assertEqual((await db.get_user_balance(2))['available'],0)

    async def test_cash_only_payout_and_no_fake_request(self):
        await self.toggle(True)
        req=await self.earn()
        await db.complete_manual_payout(1,999)
        await self.spin('cash')
        details=await db.get_payout_user_details(1)
        self.assertEqual(len(details['entries']),1)
        self.assertIsNone(details['entries'][0].request_id)
        payout=await db.complete_manual_payout(1,999)
        self.assertEqual(payout.total_amount,20)
        self.assertEqual((await db.get_request(req.id)).status,'paid_out')

    async def test_duplicate_nonce_replays_after_pause_and_new_session(self):
        await self.toggle(True)
        await self.earn(300)
        nonce='persistent-operation-123456'
        first=await self.spin('cash',nonce=nonce)
        await self.toggle(False)
        second=await wheel.spin(1,nonce)
        self.assertEqual(first,second)
        self.assertEqual((await db.get_user_balance(1))['available'],230)
        async with self.sessions() as s:
            self.assertEqual(await s.scalar(select(func.count(db.WheelSpin.id))),1)
        await self.toggle(True)
        self.assertEqual((await wheel.state(1))['available'],1)

    async def test_cash_insert_failure_rolls_back_spin_jackpot_and_ticket(self):
        await self.toggle(True)
        await self.earn()
        def fail(conn,cursor,statement,params,context,many):
            if statement.startswith('INSERT INTO balance_entries'):
                raise RuntimeError('simulated storage interruption')
        event.listen(self.engine.sync_engine,'before_cursor_execute',fail)
        try:
            with self.assertRaisesRegex(RuntimeError,'simulated'):
                await self.spin('jackpot')
        finally:
            event.remove(self.engine.sync_engine,'before_cursor_execute',fail)
        state=await wheel.state(1)
        self.assertEqual((state['available'],state['used'],state['jackpot_claimed']),(1,0,False))
        await self.spin('cash')
        self.assertEqual((await wheel.state(1))['available'],0)

    async def test_distribution_boundary_and_global_single_jackpot(self):
        self.assertEqual(Counter(wheel.ORDINARY),{'one':4,'two':4,'four':4,'five':4,'ten':3,'cash':1})
        with patch.object(wheel.secrets,'randbelow',return_value=0) as draw:
            self.assertEqual(wheel.choose_prize(False),'jackpot')
            draw.assert_called_once_with(1_000_000_000_000)
        with patch.object(wheel.secrets,'randbelow',side_effect=[999_999_999_999,8]) as draw:
            self.assertEqual(wheel.choose_prize(False),'cash')
        await self.toggle(True)
        await self.earn(150,1);await self.earn(150,2)
        with patch.object(wheel.secrets,'randbelow',return_value=0):
            a=await wheel.spin(1,'first-global-spin-123')
            b=await wheel.spin(2,'second-global-spin-123')
        self.assertEqual((a['prize'],b['prize']),('jackpot','one'))

    async def test_toggle_revision_and_access_no_new_spin_when_off_or_blocked(self):
        self.assertEqual(await wheel.set_enabled(True,999,0),'changed')
        self.assertEqual(await wheel.set_enabled(False,999,0),'stale')
        self.assertTrue((await wheel.state(1))['enabled'])
        with self.assertRaisesRegex(ValueError,'закрыт'):
            await wheel.spin(3,'blocked-attempt-12345')
        with self.assertRaises(ValueError):
            await wheel.spin(1,'short')
        self.assertNotIn('chance',str(await wheel.state(1)))
        self.assertEqual((await wheel.state(2))['history'],[])

    @unittest.skipUnless(POSTGRES,'requires dedicated local PostgreSQL')
    async def test_postgres_concurrent_duplicate_and_distinct_spins(self):
        await self.toggle(True)
        await self.earn(150)
        with patch.object(wheel,'choose_prize',return_value='cash'):
            same=await asyncio.gather(*(wheel.spin(1,'same-nonce-concurrent') for _ in range(16)))
        self.assertEqual(len({r['id'] for r in same}),1)
        await self.earn(150)
        with patch.object(wheel,'choose_prize',return_value='five'):
            results=await asyncio.gather(*(wheel.spin(1,f'different-nonce-{i:08}') for i in range(16)),return_exceptions=True)
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertEqual(sum(isinstance(r,ValueError) for r in results),15)

    @unittest.skipUnless(POSTGRES,'requires dedicated local PostgreSQL')
    async def test_postgres_one_global_jackpot_under_concurrent_users(self):
        await self.toggle(True)
        await self.earn(150,1);await self.earn(150,2)
        with patch.object(wheel.secrets,'randbelow',return_value=0):
            results=await asyncio.gather(wheel.spin(1,'global-race-nonce-one'),wheel.spin(2,'global-race-nonce-two'))
        self.assertEqual(Counter(r['prize'] for r in results),{'jackpot':1,'one':1})
        self.assertEqual(sum([(await db.get_user_balance(i))['available'] for i in [1,2]]),710)

    @unittest.skipUnless(POSTGRES,'requires dedicated local PostgreSQL')
    async def test_postgres_confirm_race_consumes_one_coupon_per_payment(self):
        await self.toggle(True)
        await self.earn(300)
        await self.spin('five');await self.spin('ten')
        a=await self.request(100);b=await self.request(100)
        result=await asyncio.gather(db.confirm_payment(a.id,999),db.confirm_payment(a.id,999),db.confirm_payment(b.id,999))
        self.assertEqual(sum(r is not None for r in result),2)
        confirmed=[r for r in result if r]
        self.assertEqual(sorted(r.wheel_bonus_percent for r in confirmed),[5,10])

    @unittest.skipUnless(POSTGRES,'requires dedicated local PostgreSQL')
    async def test_postgres_refund_withdraw_and_payout_races_leave_consistent_ledger(self):
        await self.toggle(True)
        req=await self.confirm(150)
        await asyncio.gather(db.mark_paypal_withdrawn(req.id,999),db.refund_confirmed_payment(req.id,999))
        self.assertEqual((await db.get_request(req.id)).status,'payment_refunded')
        self.assertEqual((await wheel.state(1))['qualified'],0)
        req=await self.earn(150)
        result=await asyncio.gather(db.complete_manual_payout(1,999),db.refund_confirmed_payment(req.id,999))
        row=await db.get_request(req.id)
        entry=await db.get_payment_balance_entry(req.id)
        self.assertIn((row.status,entry.status),{('paid_out','paid'),('payment_refunded','cancelled')})
        self.assertEqual((await db.get_user_balance(1))['available'],0)

    @unittest.skipUnless(POSTGRES,'requires dedicated local PostgreSQL')
    async def test_postgres_migration_is_additive_idempotent_and_never_backfills_eligibility(self):
        old=await self.earn(500)  # OFF
        # Reproduce the previous deployed schema before the wheel migration.
        async with self.engine.begin() as conn:
            await conn.execute(text('ALTER TABLE balance_entries DROP COLUMN wheel_spin_id'))
            await conn.execute(text('ALTER TABLE balance_entries ALTER COLUMN request_id SET NOT NULL'))
            await conn.execute(text('ALTER TABLE requests DROP COLUMN wheel_bonus_percent'))
            await wheel.migrate(conn)
            await wheel.migrate(conn)
        self.assertEqual((await db.get_request(old.id)).wheel_bonus_percent,0)
        self.assertEqual((await db.get_user_balance(1))['available'],350)
        await self.toggle(True)
        self.assertEqual((await wheel.state(1))['qualified'],0)
        async with self.engine.begin() as conn:
            await wheel.migrate(conn)
        self.assertTrue((await wheel.state(1))['enabled'])


    @unittest.skipUnless(POSTGRES,'requires dedicated local PostgreSQL')
    async def test_postgres_full_startup_twice_preserves_awards_progress_and_activation(self):
        await self.toggle(True)
        await self.earn(300)
        await self.spin('cash')
        await self.spin('five')
        before=await wheel.state(1)
        with patch.object(db,'engine',self.engine):
            await db.init_db()
            await db.init_db()
        after=await wheel.state(1)
        self.assertEqual((after['enabled'],after['revision'],after['used'],after['qualified']),
                         (before['enabled'],before['revision'],before['used'],before['qualified']))
        self.assertEqual((await db.get_user_balance(1))['available'],230)
        self.assertEqual((await db.get_user_balance(1))['wheel_next_bonus'],5)
