# Credits and Paddle setup

Implemented plans: Free (10 one-time starter credits), Pro ($19/month, 200 credits), Studio ($49/month, 600 credits). One-time packs: 100 credits/$12 and 250 credits/$30. Plans live in `backend/routers/billing.py`; the frontend reads that catalog. Change catalog amounts together with Paddle prices.

## Database and runtime

Apply migration `010_credits_and_auth_linking.sql` before serving the new application. PostgreSQL applies numbered migrations automatically at startup. Supabase installations must apply it with their migration/admin connection; the tables and RPC require service-role access. The migration enables RLS on credit tables and does not expose the RPC to public callers.

The migration intentionally clears passwords and sessions for existing `email,google` accounts. The previous Google-linking flow may have verified an attacker-chosen password. Affected users can sign in with Google or set a new password using the reset-email flow. Other password-only accounts are unaffected. Pending email-verification links issued before this migration must be resent: new links bind to the exact password credential they verify.

Set `CREDITS_ENABLED=true`, `READER_PIPELINE_VERSION=v2`, and `AI_JOBS_ENABLED=true`. Run the existing worker process alongside the API. Production refuses to start with credits disabled or the unmetered V1 reader pipeline. Configure Uvicorn's trusted proxy addresses (`FORWARDED_ALLOW_IPS`) for the actual deployment; the application no longer trusts arbitrary X-Forwarded-For values itself. Do not use a wildcard on a directly reachable server.

The starter grant is issued once per account, including existing accounts on their first credit-system request. Monthly credits expire at the paid period end; starter and top-up credits do not expire. There is no word allowance or per-manuscript dollar cap. Upload size and abuse rate limits remain.

Credits are metered in integer thousandths. `CREDITS_PER_USD=100` converts the configured internal model-price estimates into credits. This is an initial conversion, not a verified margin guarantee. Calibrate the model-price table and conversion using representative manuscripts before selling at scale.

Each live model call reserves a bounded amount before contacting the provider. Successful calls settle up to that reservation, failed calls release it, and repeat settlement is idempotent. An abandoned reservation is released after 24 hours during balance access. Preflight quotes are estimates, not fixed-price jobs: longer responses can require additional credits partway through a workflow. Completed sections remain saved. Reservations are per provider call, not a guarantee against every duplicate model invocation after a worker crash; test job recovery under your deployment's actual failure conditions.

## Paddle sandbox configuration

Create a Paddle Billing sandbox account and four USD prices:

| Environment variable | Price | Type |
| --- | --- | --- |
| `PADDLE_PRICE_PRO` | $19 / 200 credits | Monthly, frequency 1 |
| `PADDLE_PRICE_STUDIO` | $49 / 600 credits | Monthly, frequency 1 |
| `PADDLE_PRICE_TOPUP_100` | $12 / 100 credits | One-time |
| `PADDLE_PRICE_TOPUP_250` | $30 / 250 credits | One-time |

Set `PADDLE_ENVIRONMENT=sandbox`, `PADDLE_API_KEY`, `PADDLE_CLIENT_TOKEN` (a `test_` client token), and `PADDLE_WEBHOOK_SECRET`. The API key and webhook secret are server-only. The client token is intentionally public and returned in the catalog. Use the sandbox host `https://sandbox-api.paddle.com`; the integration pins `Paddle-Version: 1`.

Set the default payment link in Paddle to `https://YOUR_FRONTEND/pricing` (localhost is supported for sandbox). This page initializes Paddle.js when `_ptxn` is present, allowing transaction links and payment-recovery emails to open checkout. Live accounts require website approval and an approved payment-link domain. Include support contact information, terms, and refund/privacy policies on the approved website before asking Paddle to activate live sales.

Paddle API-key permissions needed: customer read/write, price read, transaction read/write, subscription read/write, customer-portal-session write, and adjustment read. Use the corresponding names shown by Paddle's authentication dashboard.

Create a notification destination at `https://YOUR_API_HOST/api/billing/webhook` and subscribe to:

- `transaction.completed`
- `subscription.created`, `subscription.updated`, `subscription.activated`
- `subscription.canceled`, `subscription.paused`, `subscription.resumed`, `subscription.past_due`
- `adjustment.created`, `adjustment.updated`

The endpoint checks `Paddle-Signature` against the exact raw request body. It retrieves the current Paddle resource, validates the account/customer and catalog price, and grants credits only when the transaction is `completed`. Client-side checkout completion never grants credits. Monthly grants are deduplicated by subscription and paid period; packs are deduplicated by transaction. Do not enable trials, non-monthly billing, multiple quantities, or immediate prorated upgrades without extending fulfillment.

Prices in the page are USD base prices. Configure tax mode consistently in Paddle; applicable taxes and the final payable amount appear in checkout. Paddle handles the payment checkout and customer billing portal.

## Checkout, renewals, and plan changes

`/pricing` is public; `/billing` is the signed-in balance and history page. Checkout is created by the backend and opened as a Paddle overlay. The backend ignores client-supplied prices or quantities. An unfinished checkout can be resumed or explicitly canceled before opening another; this prevents overlapping purchases. If Paddle accepts a create request but its response is lost, the next attempt searches for that order before proceeding. An ambiguous provider failure with no recoverable transaction requires operator reconciliation rather than blindly creating another charge.

Customer Portal manages cancellation, payment methods, and invoices. The app's plan-change buttons use `proration_billing_mode=do_not_bill`: the recurring price is updated without an immediate charge, and the new monthly allowance is granted only at the next completed renewal. Existing monthly credits keep their original expiry. The page displays the next plan when it differs from the current paid allowance.

Failed or merely `paid` (not yet processed) transactions do not issue credits. Cancellation preserves purchased and starter credits; existing monthly credits expire normally. There is one recurring plan per account.

## Refunds and payment review

Approved one-time pack refunds/credits/chargebacks revoke proportional credits. Spent credits become a credit debt recovered from unspent or future grants. Replayed adjustment events do not revoke twice; reversed chargebacks/credits restore the appropriate amount. A chargeback warning temporarily blocks new AI work. Reconciliation checks all current adjustments for the transaction and uses event ordering to reject stale snapshots.

Subscription refunds, mismatched currencies, and adjustments with unavailable totals are flagged for operator review. Saved manuscripts and reports remain accessible. Operator procedure: inspect Paddle and `credit_entries`, determine the grant to reverse, then use an audited `services.credits.change` operation with a unique support-case key. Record `kind: adjustment`; resolve the corresponding `payment_reviews` entry and recalculate `payment_review` only after outstanding cases are handled. Do not edit balances without an audit receipt. Automatic subscription-refund proration and a staff review UI are not part of this release.

## Release checks

Local validation covers mocked Paddle callbacks and isolated PostgreSQL concurrency. Before activation, complete actual Paddle sandbox Checkout and Portal flows: subscription, top-up, renewal, failed payment, cancellation, next-renewal plan change, duplicate notification, refund, and reversal. Test webhook delivery/retry with the deployed database and worker. Monitor failed notifications and payment-review cases. Scheduled remote reconciliation is not implemented.

Use separate production API keys, client tokens, Price IDs, and notification secrets. Set `PADDLE_ENVIRONMENT=production` and explicitly set `PADDLE_LIVE_ENABLED=true` only after Paddle approval and sandbox acceptance. The default disables live payments. No live payments or deployment were enabled by this implementation.

Check deployed authentication cookies and deep links; the static frontend host needs rewrites or the existing GitHub Pages fallback for `/pricing` and `/billing`.

Official references:

- https://developer.paddle.com/build/transactions/default-payment-link/
- https://developer.paddle.com/api-reference/transactions/create-transaction/
- https://developer.paddle.com/webhooks/transactions/transaction-completed/
- https://developer.paddle.com/webhooks/about/signature-verification/
- https://developer.paddle.com/api-reference/customer-portals/create-customer-portal-session/
