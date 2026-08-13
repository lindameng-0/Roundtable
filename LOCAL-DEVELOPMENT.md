# Running Roundtable locally

Local development does not require Supabase or an LLM API key.

With no `backend/.env`, the backend automatically uses:

- `DATABASE_BACKEND=memory`: process-local data, cleared on restart.
- `LLM_BACKEND=mock`: deterministic placeholder readers and reports for testing the interface and workflow.

Mock feedback is deliberately labeled in its output. It is not suitable for judging a manuscript.

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

Confirm the runtime at <http://localhost:8000/api/>. It should report
`"database_backend":"memory"` and `"llm_backend":"mock"`.

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

This keeps manuscript data local while using Gemini for personas, readers, and
the Editor. Choose Standard (Flash) or Deep reading (Pro) in the setup screen.

## Production safety

Set `ENVIRONMENT=production` in production. The backend refuses to start with
the memory database or mock LLM in production, preventing silent data loss or
placeholder feedback.
