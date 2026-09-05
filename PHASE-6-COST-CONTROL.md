# Phase 6 — Cost control

Phase 6 keeps the high-quality reader/editor routing while putting a hard, per-manuscript ceiling around paid model work.

## What is controlled

- Setup genre detection is recorded against the manuscript.
- Persona generation uses the inexpensive `PERSONA_MODEL_ROUTE` and is reserved/recorded.
- Reader V2, hierarchical editor maps, final editor synthesis, and the optional copy edit reserve budget before every provider call.
- Malformed-JSON retries are included in the reservation. Successful calls settle to actual token usage; calls that never reach a provider release their reservation.
- Unknown/unpriced model routes are refused instead of silently bypassing the budget.

## User-facing behavior

- Setup defaults each manuscript to a $5 limit and estimates the selected readers plus the first editor report.
- The reading header shows recorded spend against the hard limit.
- Editor regeneration and copy edit show their estimated incremental cost and require confirmation.
- A cached editor report remains free to reopen.

Estimates use the prices in `backend/services/model_routing.py`; provider invoices remain authoritative. Update that table when model pricing changes.

## API

- `GET /api/manuscripts/{id}/cost-estimate?operation=remaining|readers|editor|editor_regeneration|copyedit`
- `GET /api/manuscripts/{id}/budget`
- `PATCH /api/manuscripts/{id}/budget` with `{ "cost_limit_usd": 5.0 }`

`$0` means unlimited. The API refuses lowering a limit beneath already spent or currently reserved cost.

## Persistence and concurrency

Migration `backend/migrations/003_cost_control.sql` adds manuscript counters, an audit table, and PostgreSQL/Supabase transaction functions. `reserve_ai_cost` locks the manuscript row, so concurrent readers cannot all pass the same remaining-budget check.
Migration `004_cost_reservation_recovery.sql` releases reservations left behind for more than two hours by a crashed process.
