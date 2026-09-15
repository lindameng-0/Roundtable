# Roundtable assistant connections

Roundtable exposes a private MCP server at
`https://roundtable-production-3d0c.up.railway.app/api/mcp/`.
The static site at roundtable.works does not proxy `/api`; use the backend URL.

## Connect

1. Sign in with a verified account and open `/connections` (also in the account menu).
2. Create a named key. Read-only is the default; reading permission also allows
   manuscript creation, reader setup/configuration, and paid readings/reports.
3. In a compatible MCP client, choose Streamable HTTP, use the endpoint above,
   and set the `Authorization` header to `Bearer YOUR_KEY`.
4. Ask the assistant to list manuscripts and select the draft to work with.

This version supports clients with custom bearer headers. It does not implement
OAuth discovery, authorization-code login, the legacy SSE transport, or a stdio
launcher. Do not claim compatibility with clients that require OAuth. Public
setup guidance is at `/connect-assistant`.

## Tools

- `list_manuscripts`, `get_manuscript`, `list_readers`
- `get_credit_balance`, `estimate_reading`
- `create_manuscript`, `prepare_readers`, `set_reader_focus`
- `start_reading`, `get_job`, `get_reading_results`
- `create_editorial_report`, `get_editorial_report`

`list_readers` never generates readers. Reader setup and automatic genre analysis
can spend credits and require explicit `confirm_credit_use=true`. Readings and
editorial reports also compare a fresh estimate with the user-approved estimate.
**The approved estimate is not a hard spending cap.** Actual usage can differ;
the existing credit reservation and settlement system enforces account balance.
The UI and tool descriptions disclose this. MCP keys cannot buy credits, change
billing, delete manuscripts, or manage other keys. Set `permission=read` to
prevent any tool that creates/configures manuscripts or starts AI work.

Readings run through the existing durable worker and use its deterministic
idempotency key. Reader configuration locks at enqueue time. Poll jobs no more
often than every five seconds. After timeouts, inspect manuscripts and jobs
before retrying creation. Manuscript creation is not idempotent; the client must
not retry blindly. This initial MCP release does not expose report regeneration
or failed-reading retries.

## Authentication and deployment

- Keys contain 256 bits of randomness, are shown once, and are stored as hashes.
  Connection names, permission, identifying prefixes, and expiries are stored.
- Expiry choices are 7, 30, and 90 days. Revocation deletes the credential and
  takes effect on the next request. Queued/running work can continue afterward.
- The MCP transport validates every request and each tool call against current
  credentials and account verification. Browser cookies do not authenticate MCP.
- Browser key management requires an existing verified session and an allowed
  Origin. Bearer keys cannot authenticate to ordinary account/billing/admin APIs.
- Existing manuscript ownership, rate limiting, credits, and job services are
  reused through an internal request type, never an externally supplied user ID.
- The official Python MCP SDK is pinned in `backend/requirements.txt`. Each app
  lifespan creates a fresh stateless MCP session manager. Host and Origin
  validation stay enabled. `MCP_ALLOWED_HOSTS` can add exact production hosts;
  `CORS_ORIGINS` controls allowed browser origins. Requests without Origin are
  accepted for native MCP clients, subject to host validation and bearer auth.
- Migration `012_integration_keys.sql` adds the RLS-protected credential table.
  PostgreSQL runs migrations at startup under the existing migration lock.
  Supabase REST deployments must apply this SQL separately with server privileges.
- Deploy the backend and worker, confirm health and the new MCP endpoint, then
  publish the complete frontend build. Keep `/connections` out of the sitemap.

## Validation

Run `python -m pytest backend/tests/test_mcp_integration.py
backend/tests/test_site_analytics.py backend/tests/test_email_auth.py
backend/tests/test_durable_ai_jobs.py backend/tests/test_phase3_security.py -q`.
Tests force memory storage and mock LLMs. The MCP suite exercises the real HTTP
protocol, credential storage/revocation/expiry, Origin/Host checks, account
boundaries, read-only enforcement, credit approval, idempotent enqueue, and a
three-section reading plus editorial report through the actual worker.

Run the frontend search tests and production build. Confirm the new public pages
contain their content and indexing metadata before JavaScript executes; confirm
private fallback HTML remains noindex. The sample reading is explicitly labeled
as a curated, AI-assisted editorial demonstration, not a recorded product run.

Official references:
- https://github.com/modelcontextprotocol/python-sdk/tree/v1.x
- https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
