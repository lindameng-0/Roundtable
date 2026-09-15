# Roundtable launch review — 2026-09-07

Recommendation: fix the confirmed account-security and usage-enforcement issues before a public paid launch. Then ship a small paid beta with credits, a coherent visual identity, and a useful public website. Search optimization follows having something public to index.

Scope: repository review and isolated local tests using an in-memory database and mocked Google/AI responses. No production penetration test, deployed browser review, dependency audit, or verification of deployed database permissions was performed. The web tool could not open roundtable.works. Application code and production settings were not changed.

## Confirmed launch blockers

| Finding | Evidence | Required change |
| --- | --- | --- |
| Account access through an unverified password retained during Google linking | `backend/routers/auth.py` signup stores an unverified password; Google callback finds the account by email, marks it verified, and preserves that password. Local reproduction: password login returned 200 after mocked Google login for the same email. | Never promote an unverified password into a verified credential through Google login. Clear unverified credentials and outstanding tokens when claiming the account, or require a secure explicit linking flow. Add regression coverage. Audit existing linked accounts for exposure. |
| OAuth state is not bound to the initiating browser | The login route stores hashed state but sets no browser-binding cookie; callback only checks database state. Local reproduction: callback in a separate TestClient issued a session cookie. | Bind the OAuth transaction to the initiating browser using a short-lived secure HttpOnly cookie and validate it at callback, alongside single-use server state. Review PKCE and login CSRF protection. |
| Users can disable provider-spend controls | `backend/models.py` accepts zero as unlimited; manuscript creation accepts a supplied cap; the budget PATCH route checks ownership only. Local reproduction: ordinary owner PATCH returned 200 with `unlimited: true`. | Keep provider budgets under server/admin control. Do not accept client-selected internal caps. Add an atomic account credit ledger and enforce reservations before every billable operation. |
| Word allowance can be bypassed | `append_manuscript_text` checks byte size but not account word usage. Local reproduction: a two-word manuscript accepted 30,001 more words; usage returned 30,003 against the 30,000 limit. | Enforce the current quota on append until credits replace it. Serialize quota checks and writes. Charge usage independently of stored manuscript size: deleting content must not refund already consumed AI work. |

Existing checks run: `python -m pytest backend/tests/test_phase3_security.py backend/tests/test_email_auth.py backend/tests/test_phase6_cost_control.py -q -p no:cacheprovider` — 15 passed. The additional local reproductions above demonstrate coverage gaps; passing existing tests is not launch clearance.

Other items to verify before opening access:

- Rate limiting trusts the first X-Forwarded-For value. Confirm the deployed proxy sanitizes this and blocks untrusted direct access. PostgreSQL has shared rate buckets; the other database adapters can fall back to per-process limits.
- The model configuration endpoint lets any signed-in user change process-global defaults. Remove that ability or restrict it to an administrator; keep model choice scoped to each manuscript.
- Verify production database roles and Supabase API grants/RLS. The baseline schema comments out an RLS example; that alone does not establish deployed exposure.
- Exercise simultaneous jobs, worker restarts, retries, deletion during work, and recovery of reservations on the deployed database backend.
- Test browser login with the current frontend/backend domains. Cross-site cookies can create browser compatibility problems; a same-origin API proxy or a controlled API subdomain should be considered.
- Check dependency vulnerabilities, secret history, production headers, logs, backups and restore, and transactional-email deliverability.

OWASP's OAuth guidance requires CSRF protection tied to the user agent: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html

## Replace the $5 experience

The frontend defaults to $5 in `SetupPage.js`; the backend default is $25. Raw dollar estimates also appear on reading progress, report-generation confirmations, and report summaries.

Remove the user-editable cap, internal provider dollar amounts, and instructions to raise the AI budget from all those surfaces. Retain server-controlled circuit breakers and internal usage accounting. A hidden cap alone is not a credit/payment system.

The replacement experience should show available credits, the next reset date, and a quoted credit charge before starting work. Example wording: “This reading uses 24 credits. Your balance is 180.” Numbers here are illustrative. Reserve the quoted charge atomically; settle once and release unused reservations after failure. Provider retries must not become duplicate customer charges. Keep completed reports accessible at zero balance.

## Three-tier pricing proposal

These are starting hypotheses, not validated prices or implemented products:

| Tier | Monthly price | Monthly credits |
| --- | ---: | ---: |
| Free | $0 | 10 |
| Pro | $19 | 200 |
| Studio | $49 | 600 |

Start with the same core feedback quality across tiers, varying allowances. Studio need not include collaboration at launch. Make the free allowance sufficient for a useful short sample, after measuring costs.

- Subscription credits refresh each billing cycle, with no rollover.
- Purchased top-up credits persist and are consumed after monthly credits.
- Price top-ups roughly 20–25% above the applicable paid tier's included per-credit rate. Publish exact packs before launch. Decide separately whether Free can purchase a pack.
- Cancellation/downgrade takes effect at renewal. Preserve access to existing work and purchased credits under the published policy.
- For launch, scheduling tier changes at renewal avoids mid-cycle proration complexity; users can top up immediately. If immediate upgrades are introduced, specify proportional payment and credit grants together.
- Define refunds, disputes, failed payments, credit expiry, and cancellation behavior before implementing fulfillment.

Emergent documents monthly resets, durable top-up credits, and monthly-first consumption. Its published examples have inconsistencies, so borrow the structure rather than copying its arithmetic: https://help.emergent.sh/plans-and-credits

Before locking prices, measure complete runs across short stories, chapters, and novels, with different panel sizes, model choices, editor reports, and retries. Map word count, reader count, and operation to a predictable credit quote. Validate margins at high usage, including infrastructure, payment fees, failures, and support. Publish representative “what this allowance buys” examples only after measuring.

## Payment implementation (superseded by Paddle)

Use Stripe-hosted Checkout for subscriptions and one-time credit packs, and Customer Portal for billing management. Keep product credits in Roundtable's database.

Store customers, subscription state, credit grants with source and expiry, reservations, ledger entries, and processed payment records. Use integer credits and database transactions. Server-side catalog entries must map authorized plan/pack identifiers to Stripe Price IDs; never trust browser amounts or credit quantities.

Verify webhook signatures against the raw request body. Grant subscription allowance once for each eligible paid billing period; grant top-ups only after payment is confirmed. Handle duplicates and out-of-order deliveries, and deduplicate both event delivery and the underlying invoice/payment grant. Do not fulfill from a success redirect alone. Periodically reconcile Stripe state against the ledger. Free monthly grants also require idempotent period keys.

Test renewal, duplicate webhooks, delayed payment, failures, cancellation, downgrade, refund, dispute, and simultaneous credit spends before enabling live sales.

References:

- https://docs.stripe.com/billing/subscriptions/webhooks
- https://docs.stripe.com/checkout/fulfillment
- https://docs.stripe.com/webhooks
- https://docs.stripe.com/billing/testing

## Visual direction

The login uses a dark green/gold split-screen composition and burgundy controls, while the application uses cream, clay, and a different visual structure. The inconsistency is present in the source; a rendered visual/accessibility review remains necessary.

Direction: a contemporary literary review or reading room. Use ivory paper, charcoal text, restrained oxblood or library green, fine rules, generous margins, small folio labels, and a recognizable typographic wordmark. Keep Cormorant for display headings if it works in browser testing; use a sturdier reading serif for long manuscripts and a clear sans-serif for controls.

Use one shared header, typography scale, color system, button style, and form treatment across landing, login, setup, dashboard, reading, and reports. Replace the login's dark promotional panel with a compact form on the same paper surface and a small example annotation. Give manuscripts, reader margin notes, and editorial reports a book-like hierarchy. Avoid relying on cream plus terracotta as the entire identity.

Verify narrow screens, keyboard navigation, contrast, focus visibility, loading, failures, empty states, and long manuscripts. Do not hide model/debug terminology inconsistently: explain choices in terms writers can act on, such as speed and reading depth.

## SEO and answer-engine discovery

Current root routing sends guests to login. The HTML has a basic title and description but no substantial public product content, and the repository has no public pricing, example report, sitemap, or robots file.

First release public, indexable pages for the product, pricing, how it works, a permissioned or synthetic sample report, FAQ, privacy, and terms. Lead with a clear description: “AI beta readers for fiction writers, with distinct reader reactions and an editorial report.” Explain limitations and manuscript handling accurately.

Serve useful HTML without requiring client-side rendering. Static/prerendered marketing pages can coexist with the existing React application. Add unique titles/descriptions, canonicals, social cards, a sitemap, proper HTTP statuses, and Search Console verification. The current GitHub Pages deployment copies index.html to 404.html: confirm public deep links return 200, not a rendered page with a 404 response.

For AEO, answer specific questions in readable page text: what Roundtable does, supported genres/formats, how reader perspectives differ, costs, ownership, retention, and AI limitations. Use truthful Organization/SoftwareApplication structured data where appropriate; never invent ratings. Keep private manuscripts and authenticated reports behind authorization and out of sitemaps. Robots rules are not access control.

Google's guidance emphasizes normal Search eligibility and useful accessible content for AI features, not a separate magic AEO markup layer: https://developers.google.com/search/docs/appearance/ai-features

## Release order and gates

1. Fix the four reproduced security/usage issues and add targeted regression tests.
2. Measure run costs; implement the ledger and Stripe in test mode; replace all internal-dollar UI with credits.
3. Unify the visual system and launch the public product/pricing/example pages.
4. Validate upload → readers → report → export on mobile and desktop, with real AI and deployed persistent workers. Verify billing failure/retry behavior and database restore.
5. Publish manuscript ownership, provider processing, retention/deletion, refund, and support information that matches actual behavior. Add account deletion; manuscript deletion already exists.
6. Invite 10–20 writers. Track signup → upload → completed reading → report viewed → paid conversion, plus cost and failure rate. Keep manuscript contents out of analytics. Broaden launch after the core flow and billing are dependable.

A large content campaign, annual billing, collaboration, and advanced plan features can follow this first release.
