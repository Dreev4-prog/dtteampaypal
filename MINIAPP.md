# DT TEAM Mini App

The approved black/graphite/gold interface is served by the same process as the bot.
It uses the existing registered handlers and PostgreSQL database; there is no second
ledger or copied set of payment operations. The bot menu keeps its previous rows,
with **Открыть Mini App** added directly below **Поддержка**.

## Running

- Existing `BOT_TOKEN`, `ADMIN_IDS`, `DATABASE_URL` remain unchanged.
- Set `MINI_APP_URL=https://<service-domain>/app` and `PORT=8080`.
- `python main.py` starts the HTTP server, bot polling, autoposts and stock warmup.
- Route the Railway HTTPS domain to port 8080. `/healthz` checks the database.
- Keep one service replica: Mini App sessions and FSM drafts use process memory,
  as the existing bot did. A restart invalidates Web App sessions and unfinished
  forms; committed business records remain in PostgreSQL. Reopen from the bot.

Telegram provides the real iPhone/WebView chrome; the app does not draw a fake
status bar, chat window or pretend system controls. New default ALF images are
shared with the ordinary bot; custom images configured in the bot keep precedence.

## Authorization and operation safety

- `initData` is verified with Telegram's HMAC-SHA256 procedure and a one-hour
  authentication timestamp limit. See [Telegram's specification](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).
- Only server-verified Telegram IDs are used. Browser-provided role/user IDs are
  never accepted. Access status is checked again before actions and media reads.
- The browser receives opaque button IDs bound to the current server-side screen.
  Arbitrary callback strings, foreign record IDs and stale screen versions cannot
  be submitted as actions.
- Per-user serialization, single-use screen versions and request-ID deduplication
  prevent double clicks from executing the same operation twice. An ambiguous
  failure is not automatically replayed.
- Forms in Telegram and Mini App have separate FSM namespaces. Opening another
  Mini App window revokes the previous session to avoid concurrent stale forms.
- Screens and previews are captured for the active Web App user. Notifications
  to other participants still go through the bot's existing Telegram handlers.
- Explicit photo uploads are saved in the uploading user's Telegram conversation
  to obtain durable file IDs. Payout receipt text/photos are likewise saved with a
  real Telegram message ID before the existing snapshot-checked payout operation.
  Receipt retrieval sends the stored original to the Telegram chat.
- Excel exports use authenticated downloads. No bot token appears in asset URLs.

## Verification

Install `requirements-dev.txt` and run `python -m unittest discover -s tests -q`.
The integration fixture uses SQLite and fake Telegram only. Its preview is started
explicitly with `python tests/miniapp_fixture.py` at `http://127.0.0.1:8773/app`;
`?admin=1` selects a fictitious admin. The fixture is excluded from the container.
Production never enables this fixture or accepts its test signatures.

Checks cover authorization, duplicate/stale submissions, minimum amount, STOP,
photo submission, cross-surface form isolation, provider switching and totals,
manual receipt persistence, changed-balance rejection, withdrawal/24-hour/refund
transitions, ID search, paginated 200-payment history, and autopost editing, in
addition to the bot's previous regression and startup-recovery tests.

Real transfers and broadcasts are not sent merely to test a release. Functional
tests use fake delivery; production checks validate startup, health and access
boundaries. External Telegram availability remains an external dependency.

## Rollback

The version before Mini App is commit
`5d4c79f151f25b9bc8eb219b5e6a1c78eab992ea`, retained at
[`backup/before-miniapp-20261117`](https://github.com/Dreev4-prog/dtteampaypal/tree/backup/before-miniapp-20261117).
The prior Railway deployment is `f99474ab-9aca-4d17-ad6b-146a3053f8d5`.
Redeploy that saved build or the backup branch on the same service. The old bot
has no HTTP endpoint, so remove any dashboard-level `/healthz` healthcheck when
rolling it back. Preserve the current database and its connection setting: rolling
back code must not erase payments or users recorded after this release.

## In-app usability and updates

- Request wizard: amount, PayPal type, screenshot; Back rechecks availability and
  moves one step back. Forms precede cancellation controls. Typed text and selected
  photos survive validation errors, and refresh does not reset an unfinished form.
- The bell shows recent committed request/payment milestones, with Moscow dates,
  the PayPal tag, clear held/available distinctions, and a link to the relevant
  section. The authenticated `/api/updates` endpoint polls every 12 seconds while
  the WebView is visible, with a five-second server cache; it never submits actions.
- This is a recent activity view (up to 60 milestones from 30 recent requests and
  20 payouts), not a separate complete audit log. Seen IDs are stored per Telegram
  user on the device; business records and balances remain in PostgreSQL.
- Home and wallet balances update without resetting forms or replaying actions.
  New events produce a banner and badge. Closed Mini Apps receive the bot's
  existing Telegram notifications; browser push is not used.
