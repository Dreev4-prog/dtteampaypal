# DT Wheel

Admin → DT КОЛЕСО → Включить акцию / Выключить акцию. The migration starts
OFF. This release does not activate the promotion or send a broadcast.
The worker's Mini App home displays its wheel entry only while enabled.
The existing bot menu rows remain unchanged except for the new admin row.

## Eligibility and rewards

- Eligibility is recorded **inside confirmation**, only while enabled. Both
  standard and direct issued-PayPal confirmation paths use it. Issuance can
  predate launch; confirmation cannot. No historical payments are backfilled.
- Eligible principal EUR counts only when PayPal withdrawal is recorded. Each
  cumulative €150 earns one spin; remainder carries. 24-hour waits do not count.
- Turning OFF blocks new eligible confirmations and spins, preserving progress,
  prizes and the single global jackpot. Payments already confirmed during an
  active period still count when subsequently withdrawn, including during a pause.
- +1/+2/+4/+5/+10 are percentage points added to the effective next confirmed
  payment (including Happy Hours), one FIFO coupon per payment, without stacking.
  Earned coupons continue to apply during a pause and are visible in the wallet.
- Cash rewards shown as $20/$500 credit 20/500 USDT to the existing balance ledger.
  Rules explicitly state this settlement unit. They follow the user's current
  CryptoBot/xRocket preference and existing check/snapshot payout workflow.
- Refunds remove qualifying principal and restore the coupon used on the refunded
  payment. Awarded prizes stay intact; if already-used spins exceed the revised
  turnover, subsequent principal first covers the shortfall. The wheel shows this.
- History shows the latest 50 spins; all spins remain permanently in PostgreSQL.

## Accounting and concurrency

The server selects prizes with `secrets.randbelow`, never with browser input.
The display sectors are decorative; ordinary weights correspond to the 20-entry
server list. Jackpot draw uses one exact integer ticket out of 1,000,000,000,000.
That is the approved 0.0000000001 percent, not a floating-point approximation.
No numerical draw probabilities are displayed in the product.

A user row serializes confirmation, coupon use, withdrawal, spin, refund and
payout for that participant. A singleton campaign row serializes draws and
activation boundaries. The jackpot also has a unique partial database index.
A unique (user, request ID) persists spin idempotency across HTTP timeouts and
service restarts. The browser keeps an unresolved request ID for safe recovery.
The prize and any cash ledger entry commit together before animation begins.

Cash balance entries refer to wheel_spins, not invented PayPal requests. An
origin constraint, unique prize link and payout validation protect that link.
Existing totals, provider split, wallet, payout history, and check snapshots use
one ledger. No automated real transfer was introduced.

## Verification

Run `python -m unittest discover -s tests -q` with requirements-dev.txt installed.
`WHEEL_TEST_POSTGRES=1 python -m unittest discover -s tests -p test_wheel.py -q`
uses **only** a disposable localhost PostgreSQL at port 55439, user wheel_test,
database postgres. It drops its test tables and never reads the production
connection setting. Tests include concurrent same/different operation IDs,
global jackpot contention, confirmation/coupon races, refund/payout races,
failed inserts, additive migration, repeated full startup, and legacy exclusions.

`WHEEL_PREVIEW=1 PREVIEW_PORT=8775 python tests/miniapp_fixture.py` starts an
explicit local SQLite/fake Telegram preview with four fictitious spins. These
switches are confined to the test fixture; it is excluded from the Docker image.
No production endpoint accepts test identity, simulated payments or forced prizes.

## Backup and recovery

Pre-wheel code: commit 042bbc65a81c2f7494ddb7216a9a30d22e7d0aa9, branch
`backup/before-wheel-20261118`. Prior Railway deployment:
304328ff-7bc8-480b-b92c-898b1f5a242a.

Preferred emergency stop: disable the promotion in the admin menu. This preserves
payment processing and lets existing bonuses/cash prizes settle normally.
Migrations are additive; **never restore an old database snapshot over current
payments**, or drop wheel rows/columns during a code rollback. The pre-wheel
payout code does not support cash entries without a PayPal request: after any cash
prizes have been awarded, retain the wheel-aware ledger/payout code even if UI is
rolled back, or finish these payouts before reverting to that old build. Percentage
amounts already posted remain in the existing ledger and must not be recalculated.
