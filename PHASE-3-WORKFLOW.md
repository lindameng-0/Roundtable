# Phase 3: Cost-aware workflow orchestration

Phase 3 wraps the working Reader V2 and Editor V3 pipelines in deterministic,
resumable orchestration. It does not add autonomous LLM agents or extra model
calls. Strong models remain responsible for literary judgment; application code
handles task planning, validation, persistence, retry, and accounting.

## Execution contract

- One stable task per manuscript, selected reader, and section.
- Task states: `pending`, `running`, `completed`, and `failed`.
- Saved reactions are the completion authority and reconcile the task ledger.
- Reconnect and retry execute only missing reader/section pairs.
- A failed task remains retryable and records attempts plus its latest error.
- Reader concurrency and start staggering are configurable.

## Cost and model routing

- Reader routes retain the configured mixed-model panel and bounded fallback.
- Editor V3 remains a separate high-quality synthesis step.
- Copy editing remains opt-in and uses its cheaper configured route.
- Recorded provider/model token usage is aggregated by workflow role.
- Cost is an estimate; provider billing remains authoritative.

## Local configuration

```dotenv
READER_MAX_CONCURRENCY=2
READER_START_STAGGER_SECONDS=2
```

Workflow state is available at:

`GET /api/manuscripts/{manuscript_id}/workflow-status`

Local `DATABASE_BACKEND=memory` state is cleared whenever the backend restarts.
For later Supabase use, run `backend/supabase_phase3_migration.sql`.
