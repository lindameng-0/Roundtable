# Search visibility and owner analytics

Published September 8, 2026. Source commit `a8dad62` deployed successfully to the Railway web and worker services, and the production build was published to GitHub Pages. Live checks confirmed public HTML, sitemap, robots.txt, the support address, healthy PostgreSQL/worker status, a successful analytics write, and HTTP 401 for unsigned dashboard API access. Owner sign-in must use the verified owner account.

## Publish

1. Deploy the updated backend. PostgreSQL applies `backend/migrations/011_site_analytics.sql` during normal startup. If using the Supabase REST backend, apply that migration in Supabase's SQL editor before deploying. It creates an RLS-protected counter table and an atomic increment function. Keep the service-role key on the backend. Memory mode is only for local testing and loses counters at restart.
2. Owner access defaults to the **verified** Roundtable account `itsyuko0o1@gmail.com`. `OWNER_EMAIL` can override this server-side. For a permanent identity binding, set `OWNER_USER_ID` to that account's database `user_id`; then both the verified email and ID must match. Never set it to an email or an unverified account ID. Sign out and in after deploying to refresh the owner navigation flag.
3. Run `npm.cmd run build` from `frontend`, then publish the entire `frontend/build` directory through the existing hosting workflow. `npm.cmd run deploy` builds and publishes to the configured GitHub Pages repository. Do not overwrite `404.html` with `index.html`: the build now creates the correct unindexed application fallback.
4. Keep directory indexes for `/pricing/`, `/ai-beta-reader/`, `/manuscript-feedback/`, `/terms/`, `/privacy/`, and `/refunds/`. These contain rendered HTML with working content and metadata before JavaScript runs. A static host's optional trailing slash redirects are expected; canonical URLs use the site's established slashless public paths. Keep query strings out of canonicals.
5. Sign in with the verified owner account and open `/owner/analytics`, or use **Analytics** in the navigation. Check that anonymous and other-account requests to `/api/analytics/summary` return 401/403. Production cookie requests require an allowed `Origin`; set `CORS_ORIGINS` to the exact frontend origin as usual.

The owner confirmed `roundtablesupport@gmail.com` as the public support inbox. It is configured in `frontend/src/components/PolicyContact.jsx`; the private analytics owner account remains `itsyuko0o1@gmail.com`.

## Search-console setup (requires your domain account)

- Verify `roundtable.works` in [Google Search Console](https://search.google.com/search-console), normally using its DNS TXT record. Submit `https://roundtable.works/sitemap.xml`, inspect the homepage and both guides, and request indexing after publication. Check any available generative-AI inclusion setting for the property.
- Verify/import the domain in [Bing Webmaster Tools](https://www.bing.com/webmasters), submit the same sitemap, inspect index coverage, and review AI Performance when available for the property.
- Confirm that DNS, CDN, and firewall settings let search crawlers fetch the public HTML, CSS, and JavaScript. Manuscript and owner routes stay protected and out of the sitemap. `robots.txt` is a crawl instruction, never an authorization mechanism.
- The owner confirmed Google and Bing account verification on September 8, 2026. Sitemap submission is handled in those dashboards; publishing the website does not submit it automatically.

## What is measured

- Daily public-page views, broad incoming referrer categories (including major AI assistants), and clicks on links to signup. Period choices are 7/30/90 days; boundaries use UTC and the current day is partial.
- Current all-time totals of verified accounts, saved manuscripts, and editorial reports, counted from the database. Deletions reduce these current totals; report revisions are not counted as new reports.
- No analytics cookies, browser storage, visitor/session IDs, raw IPs, raw referrers, query strings, manuscript IDs/text, or emails are stored in the counters. The existing request rate limiter still processes network identity for abuse prevention. Do Not Track and Global Privacy Control skip browser measurement.
- Counts are atomic across PostgreSQL workers. Storage dimensions are allowlisted, endpoints reject arbitrary URLs/fields, and collection is origin-checked and rate-limited. Aggregates older than the retention window are pruned on new traffic. With no new traffic, old aggregates remain until the next event; schedule equivalent database cleanup if strict time-based deletion is required.
- Counts start at deployment. Repeat visits, browser refreshes, owner public-page visits, bots, missing referrers, privacy signals, and blockers affect totals. Public event submissions are not independently verified transactions. These are **not unique visitors, paid conversions, or an attributed funnel**. AI referral clicks are not AI citations, and Google AI clicks cannot be distinguished from Google Search by referrer.
- The dashboard does not claim revenue, retention, search rankings, or Core Web Vitals. Use Paddle for reconciled revenue and the search consoles for search impressions, queries, indexing, and available AI citation measurements.

## Ongoing growth work

The build uses actual React public content for prerendering, per-page descriptions/canonicals/social metadata, accurate organization/software/FAQ structured data, two practical writing guides, internal links, and a generated sitemap. Public guide copy and FAQ answers live in `frontend/src/searchContent.json`; FAQ schema uses the same answers. Keep facts and published pricing current. No fabricated reviews, ratings, or ranking guarantees are included.

Weekly: inspect indexing errors and the queries leading to visits; compare equal periods; improve a page that already attracts relevant writers; add an honest example answering a recurring writing question; and review signup interest alongside actual account/manuscript totals. Share useful examples with relevant writing communities where their posting rules allow it. Avoid buying links or publishing near-duplicate keyword pages.

Google says foundational search best practices also apply to its AI features, and no special AI schema is required: [AI features](https://developers.google.com/search/docs/appearance/ai-features), [AI optimization guidance](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide). Bing describes its citation measurements in [AI Performance](https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview). Eligibility and good implementation do not guarantee rankings, citations, or traffic.

## Validation

Run `python -m pytest backend/tests/test_site_analytics.py backend/tests/test_email_auth.py -q -p no:cacheprovider` from the repository root. These check real session authorization, verified-email/optional-ID restrictions, origin checks, privacy signals, allowlists, aggregation, date windows, and rate limits.

From `frontend`, run `npm.cmd test -- --watch=false --runInBand --runTestsByPath src/searchExperience.test.js` and `npm.cmd run build`. Public HTML generation is part of the build and fails if a page is missing substantial content. Production SQL migration execution must also be checked against the deployed database; local unit tests use the memory backend.

Verified in this workspace: 16 backend tests and 3 frontend tests passed; seven generated public pages had exactly one H1, canonical URL, indexable robots metadata, and structured data; the private fallback remained unindexed. Playwright checked the public guide at 390px, the owner dashboard at 390px/1440px, non-owner denial, a 7-day filter, and an API-error state. Browser dashboard data was mocked; backend tests exercised actual session lookup. The production build passes with pre-existing React hook warnings in ReadingPage and ReportPage. Preview screenshots are under `output/playwright/owner-analytics-*.png`.

## Sample reading and MCP update

The homepage now identifies Roundtable as AI beta readers for fiction writers.
`/sample-reading` adds a curated, clearly labeled editorial demonstration with
passage-linked perspectives, an assessment, and an explained revision. It is
linked from the homepage, guides, and footer. `/connect-assistant` documents MCP
connections; `/connections` is authenticated and stays unindexed. The sitemap
now contains nine public pages. Existing privacy and product-copy edits were
preserved, with an additional factual disclosure for assistant connections.

See `MCP-SETUP.md` for authentication, supported clients, tools, and deployment.
Validation includes the HTTP MCP protocol and an independent official SDK client,
a three-section mock reading/report through the worker, mobile/desktop browser
checks, frontend search tests, and rendered-HTML/sitemap checks.
