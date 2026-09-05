# Running Roundtable locally

Local development does not require Supabase or an LLM API key.

With no `backend/.env`, the backend automatically uses:

- `DATABASE_BACKEND=memory`: process-local data, cleared on restart.
- `LLM_BACKEND=mock`: deterministic placeholder readers and reports for testing the interface and workflow.

Mock feedback is deliberately labeled in its output. It is not suitable for judging a manuscript.

## Durable local storage (recommended)

Phase 4 supports a normal local PostgreSQL server, with no Supabase account or
network connection. Set these values in the ignored `backend/.env`:

```dotenv
DATABASE_BACKEND=postgres
DATABASE_URL=postgresql://roundtable_app:your_password@127.0.0.1:5432/roundtable
MAX_WORKFLOW_COST_USD=25
```

The backend applies the numbered SQL files in `backend/migrations`
automatically at startup. Manuscripts, reader memories, workflow progress, and
report history then survive backend and computer restarts.

New manuscripts also have a per-manuscript hard AI budget. The reader-selection
screen defaults to $5, shows a preflight estimate for the selected readers plus
the first editor report, and lets you change the cap. Reopening a cached report
does not call a model or add cost.

Reader focus can be customized in the reader-selection step. Focus and personal
tastes lock permanently as soon as the reading run begins.

## 1. Install dependencies

From the repository root:

```powershell
python -m pip install -r backend/requirements.txt
cd frontend
npm.cmd ci --legacy-peer-deps --no-audit --no-fund
cd ..
```

## 2. Start the backend

In one PowerShell window:

```powershell
cd backend
python server.py
```

Confirm the runtime at <http://localhost:8000/api/health>. It reports the
selected database and whether it is ready.

## 3. Start the frontend

In another PowerShell window:

```powershell
cd frontend
npm.cmd start
```

Open <http://localhost:3000/setup>. Guest mode supports the complete setup,
reading stream, and report flow. The dashboard and Google login still require
OAuth configuration.

## Testing with real AI readers

Create `backend/.env` containing:

```dotenv
DATABASE_BACKEND=memory
LLM_BACKEND=live
GEMINI_API_KEY=your_key_here
```

This keeps manuscript data local while using the provider routes configured in
`READER_MODEL_POOL`, `PERSONA_MODEL_ROUTE`, `EDITOR_MODEL_ROUTE`, and
`COPYEDIT_MODEL_ROUTE`. See `PHASE-6-COST-CONTROL.md` for budget behavior.

## Production safety

Set `ENVIRONMENT=production` in production. The backend refuses to start with
the memory database or mock LLM in production, preventing silent data loss or
placeholder feedback.
