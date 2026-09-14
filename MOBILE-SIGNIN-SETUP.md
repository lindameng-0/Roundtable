# Mobile Google sign-in: same-site API setup

The previous public build called the API on an unrelated Railway hostname. Browsers that block third-party cookies can complete Google authorization but omit the session cookie on the frontend's `/api/auth/me` request. `SameSite=None; Secure` does not override that browser policy.

## Production cutover

1. In the existing Railway web service (not the worker), add the custom domain `api.readerfold.com` under Networking. Copy the exact CNAME target and any verification TXT record Railway provides.
2. In the DNS manager for readerfold.com, add those records for the API subdomain. Leave the existing apex/www, email, and verification records unchanged. Wait for Railway to show a valid certificate and for `https://api.readerfold.com/api/health` to return healthy.
3. In the existing Google OAuth web client, add the authorized redirect URI `https://api.readerfold.com/api/auth/google/callback`. Retain the previous registered URI during rollout.
4. Set the Railway web service's `GOOGLE_REDIRECT_URI` to that exact new URI. Keep `FRONTEND_URL=https://readerfold.com`, an exact frontend CORS allowlist, and secure HTTP-only session cookies. Deploy the web service.
5. Configure the frontend API URL as `https://api.readerfold.com` (build-time `REACT_APP_BACKEND_URL`, or the `backend-url` meta tag when that environment override is unset), build and publish. Login initiation, Google callback, and subsequent API calls must all use the new API host; mixing hosts loses the OAuth-state or session cookie.
6. Test an actual Google login on Safari/mobile: callback reaches the dashboard, a reload remains signed in, and logout clears the session. Also test email/password sign-in and existing manuscript access. Existing sessions on the old API host will need a new sign-in.

Do not put session tokens in URLs or local storage or ask users to disable browser privacy protections. The frontend fixes in this change prevent stale session checks from undoing login and show an explicit retry screen when the callback cannot confirm a session. Those fixes alone do not eliminate the cross-site-cookie dependency.

References: https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/ and https://docs.railway.com/networking/domains/working-with-domains

## September 14 cutover verification

DNS CNAME and Railway verification TXT records for `api.readerfold.com` resolve, HTTPS is valid, and `/api/health` reports ready. The live web service now sends `https://api.readerfold.com/api/auth/google/callback` as its Google redirect URI. A signed-out Google authorization probe with `prompt=none` returned `interaction_required` to that exact callback, confirming Google recognizes the registered URI. The frontend meta configuration and production build now use `https://api.readerfold.com`. A real mobile Google login and reload remain the final user verification.
