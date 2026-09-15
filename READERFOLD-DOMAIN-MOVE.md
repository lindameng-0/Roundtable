# Move Readerfold to readerfold.com

Updated September 12, 2026. Readerfold is configured for `https://readerfold.com`, and the live homepage, robots.txt, and 17-page sitemap have been verified over HTTPS. The user has submitted the sitemap in Search Console and confirmed the live URL test succeeds; indexing is still pending. Backend environment variables, email-provider settings, Google OAuth, Paddle settings, and old-domain redirects require separate verification. The repository and Railway services retain their existing technical names.

The selling points remain simulated human reading experiences and distinct reader tastes, voices, and perspectives. The headline remains **One story. Different reactions.** The book-circle symbol and color palette are retained. The social image has been replaced with Readerfold artwork.

## Prepare before the cutover

1. Confirm you control `readerfold.com` in your domain registrar account. Verify it in the GitHub account's Pages settings using the TXT record GitHub supplies. Keep the verification record. [GitHub domain verification](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/verifying-your-custom-domain-for-github-pages)
2. Verify the new domain property in Google Search Console and Bing Webmaster Tools. Keep access to the old property and domain.
3. Arrange an HTTPS redirect service for `roundtable.works` and any used `www` variant. It must preserve paths and query strings. A DNS record alone is not an HTTP redirect. GitHub's apex/www redirect does not provide arbitrary old-domain-to-new-domain redirects. Prepare this before changing the Pages custom domain; one Pages site cannot keep two independent custom domains as its primary domain.
4. In Paddle, request live domain approval for `readerfold.com`. Update public business/product branding to Readerfold where appropriate. Change the default payment link to a new-domain page that loads Paddle.js when the new site is ready. In this app the pricing page loads the checkout integration. Keep existing product/price IDs, customer IDs, subscriptions, API keys, and the Railway webhook endpoint. [Paddle domain approval and payment links](https://developer.paddle.com/build/transactions/default-payment-link/)
5. In Google Auth Platform, prepare the Readerfold app name, authorized domain, homepage, privacy and terms URLs. This app's OAuth callback is handled by the backend. If the Railway backend URL stays the same, keep `GOOGLE_REDIRECT_URI` and its registered Google callback unchanged; changing the frontend domain does not require inventing a frontend OAuth callback. Update authorized JavaScript origins only if they are configured for the current client.
6. Use the confirmed public support inbox `readerfold@gmail.com`. For a new `accounts@readerfold.com` sender, verify the sending domain in Resend using its supplied DNS records before changing the address.

## Configure the new frontend domain

The build's public origin is now centralized in `frontend/src/siteConfig.json`. At cutover, change only its `origin` value to:

```json
"origin": "https://readerfold.com"
```

Use HTTPS with no trailing slash. The production build uses this value for canonical URLs, structured-data IDs, social URLs, the sitemap, `robots.txt`, the deployed `CNAME`, policy hostname text, and guide download links. `frontend/package.json` uses `/` for asset paths, so it does not pin assets to the old domain. The root `CNAME` and `frontend/public/CNAME` are legacy source copies; update them to `readerfold.com` for consistency, but the generated build's `CNAME` is authoritative for the existing deployment command.

In the existing `lindameng-0/Roundtable` repository, set **Settings → Pages → Custom domain** to `readerfold.com`. Add it to GitHub before pointing DNS at Pages. Then configure these records at your DNS provider:

- Four apex `A` records, host `@`: `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`.
- One `CNAME`, host `www`, target `lindameng-0.github.io` (no repository path).

Replace conflicting website records for those hosts; retain unrelated mail and verification records. Wait for the DNS check and certificate, then enable **Enforce HTTPS**. GitHub notes DNS and HTTPS availability can each take up to 24 hours. [GitHub custom-domain setup](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site)

From `frontend`, build, verify, and publish:

```powershell
npm.cmd run build
node scripts/check-public-html.cjs
npm.cmd test -- --watch=false --runInBand --runTestsByPath src/searchExperience.test.js
```

After those checks pass, publish that exact build:

```powershell
node node_modules/gh-pages/bin/gh-pages.js -d build --nojekyll -r https://github.com/lindameng-0/Roundtable.git
```

The deploy destination stays the existing repository. There is no need to rename the repository to change the public brand or custom domain.

## Coordinate the backend and account services

At cutover, update the Railway web service's production variables:

```text
FRONTEND_URL=https://readerfold.com
CORS_ORIGINS=https://readerfold.com,https://www.readerfold.com,https://roundtable.works
```

Retain the old origin during the transition if old tabs still need it; remove it when no longer needed. The new apex origin is essential for cookie-authenticated requests and analytics. Keep an exact allowlist, not a wildcard. Update `APP_URL` if it is separately configured as a frontend URL in your deployment. Restart/redeploy the backend after changes. Apply shared frontend/sender variables to any service that actually uses them.

The code defaults the email sender label to `Readerfold <accounts@roundtable.works>`, retaining the existing sending domain. If production already has `AUTH_EMAIL_FROM` set, update its display name to Readerfold while retaining the verified address. Later, once Resend verification is complete, set `AUTH_EMAIL_FROM=Readerfold <accounts@readerfold.com>`. Deploy the backend source changes to update verification/reset subjects, account messages, and the MCP server's display name.

Keep the existing Railway API URL in `frontend/public/index.html` and any configured `REACT_APP_BACKEND_URL`. Keep `SESSION_COOKIE_SECURE=true` and the existing cross-site `SESSION_COOKIE_SAMESITE=none` while the frontend and Railway API use different sites. Do not change cookie names or recreate users for this rebrand. If you later move the API to a custom `api.readerfold.com` domain, handle that as a separate migration: Google callback registration, frontend API configuration, cookie behavior, Paddle webhook, and `MCP_ALLOWED_HOSTS` must be reviewed together. The existing MCP endpoint stays on Railway for this frontend-only domain move.

Where a new public support inbox is provisioned, update `frontend/src/components/PolicyContact.jsx`, the two support-email fields in `frontend/src/searchSchema.js`, and the correction email in `frontend/scripts/build-static-guides.cjs`. Update corresponding Paddle/Google/support profiles. The owner analytics identity is an account identifier, not a brand label; keep it unchanged.

## Redirect old links and check the result

Use permanent HTTP 301 redirects such as:

```text
https://roundtable.works/beta-readers/
  -> https://readerfold.com/beta-readers/

https://roundtable.works/guides/beta-reader-questionnaire/
  -> https://readerfold.com/guides/beta-reader-questionnaire/
```

If the old domain is managed through Cloudflare, its documented single-redirect pattern can be adapted to `http*://roundtable.works/*` → `https://readerfold.com/${2}`, status 301, with **Preserve query string** enabled. Add the corresponding old `www` rule if used. Requests must reach Cloudflare through the zone's proxied DNS and have working HTTPS; a rule alone without that routing is insufficient. An alternative provider must offer equivalent HTTPS/path/query-preserving redirects. [Cloudflare's domain redirect example](https://developers.cloudflare.com/rules/url-forwarding/examples/redirect-all-another-domain/)

Check the new homepage, both guides, downloads, canonical URLs, social image, and sitemap. Test an existing account's login, Google sign-in, verification/reset links, a saved manuscript, sign-out, and checkout availability. Do not create real purchases just to test a rename. Check old URLs with a header request and confirm one-to-one redirects, including query strings. The existing user/manuscript database and credits remain in place.

After the new domain is live and redirects work, submit Search Console's **Change of Address** from the old property and submit `https://readerfold.com/sitemap.xml`. Update profile links and valuable inbound links where possible. Retain old-domain redirects for at least one year, preferably longer for readers' bookmarks. Some search fluctuation during migration is normal. [Google's site-move guidance](https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes)

## Rollback

Keep the last verified build and the previous Railway values until the move is confirmed. If cutover fails, restore the public origin and Pages custom domain to `roundtable.works`, publish a build for that origin, restore the previous frontend/CORS values, and disable the old-to-new redirect. Do not delete/recreate accounts, change database identifiers, or rotate provider keys to resolve a branding problem.

## Local verification

The production HTML check passed for all 17 public pages, and all nine search-experience tests passed. The local memory queue had a timezone comparison bug that left UTC jobs queued on non-UTC machines. Timestamp comparisons now preserve their offsets; email, MCP, local workflow, and durable queue tests pass, including a three-section mock reading and report. Production PostgreSQL queue behavior is unchanged. Provider account settings were not modified.
