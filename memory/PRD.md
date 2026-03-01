# Roundtable — PRD

## Problem Statement
Build a collaborative AI beta reader tool for fiction writers. The app simulates a panel of 5 distinct AI readers who react to manuscript chapters, with each reader having persistent memory. An Editor AI synthesizes their feedback into a professional report.

## Architecture

### Tech Stack
- **Backend:** FastAPI (Python) + Supabase (Postgres), modular services/routers
- **Frontend:** React + Tailwind CSS (Cormorant Garamond + Manrope fonts)
- **LLM:** OpenAI / Claude / Gemini via LiteLLM (set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY in backend/.env; model switchable)
- **Auth:** Emergent-managed Google OAuth
- **DB:** Supabase (Postgres)

### Code Structure
```
/app/
├── backend/
│   ├── main.py             # FastAPI app entry point
│   ├── config.py           # Config, DB and OpenAI clients
│   ├── models.py           # Pydantic and DB models
│   ├── utils.py            # Shared helper functions
│   ├── routers/
│   │   ├── api.py          # Manuscript and reading routes
│   │   └── auth.py         # Auth routes
│   └── services/
│       ├── editor.py       # Editor report logic
│       ├── manuscript.py   # Manuscript processing logic
│       ├── personas.py     # Persona generation logic
│       └── readers.py      # Core reader pipeline logic
└── frontend/src/
    ├── App.js
    ├── context/AuthContext.js
    ├── components/
    │   ├── CommentPopover.jsx
    │   ├── ManuscriptView.jsx
    │   ├── ModelSelector.js
    │   ├── ProgressBar.jsx
    │   ├── ReaderSidebar.jsx
    │   ├── StallBanner.jsx
    │   └── UserMenu.jsx
    ├── hooks/useReadingStream.js
    └── pages/
        ├── AuthCallback.js
        ├── DashboardPage.js
        ├── LoginPage.js
        ├── ReadingPage.js
        ├── ReportPage.js
        └── SetupPage.js
```

### API Endpoints
- `POST /api/auth/google` — Initiate Google OAuth
- `GET /api/auth/me` — Get current user
- `POST /api/auth/logout` — Logout
- `POST /api/manuscripts` — Create manuscript from text
- `POST /api/manuscripts/upload` — Upload .txt or .docx file
- `GET /api/manuscripts` — List user's manuscripts (auth required)
- `GET /api/manuscripts/{id}` — Get manuscript
- `PATCH /api/manuscripts/{id}/genre` — Update genre tags
- `GET /api/manuscripts/{id}/personas` — Get/generate reader personas
- `POST /api/manuscripts/{id}/personas/regenerate` — Regen one or all readers
- `GET /api/manuscripts/{id}/read-all` — SSE stream all sections
- `GET /api/manuscripts/{id}/all-reactions` — Get all reactions
- `GET /api/manuscripts/{id}/reading-status` — Check reading completion
- `POST /api/manuscripts/{id}/editor-report` — Generate editor report
- `GET /api/manuscripts/{id}/editor-report` — Get report
- `GET /api/config/models` — List available models
- `POST /api/config/model` — Switch active model

### MongoDB Collections
- `manuscripts` — raw text, genre, sections, user_id
- `reader_personas` — 5 personas per manuscript
- `reader_memories` — per-reader memory JSON per section
- `reader_reactions` — inline_comments + section_reflection per reader per section
- `editor_reports` — synthesized editorial JSON report

*(Schema migrated to Supabase/Postgres; see backend/supabase_schema.sql.)*

## User Personas
- Fiction writers (novel/short story) seeking beta reader feedback
- Self-published authors preparing for release
- Writing group members wanting objective feedback

## Core Requirements (Static)
1. Google OAuth authentication (Emergent-managed)
2. User dashboard — list + access manuscripts
3. Manuscript upload — paste text OR upload .txt/.docx file
4. Auto genre + audience detection (editable)
5. 5 distinct reader personas generated per manuscript (regeneratable)
6. Section-by-section reading with SSE streaming reactions
7. Per-reader memory compression between sections
8. Editor AI report with synthesized feedback
9. Model selector (gpt-4o-mini, claude, gemini, etc.)

## What's Been Implemented (March 2026 — v4)

### Authentication (DONE)
- Emergent-managed Google OAuth integration
- Session token stored in localStorage
- All manuscript endpoints protected with user_id filtering
- Dashboard, Setup, Reading, Report pages all require auth
- Login page with Google sign-in button

### .docx File Upload (DONE)
- Backend: `POST /api/manuscripts/upload` parses .docx via python-docx
- Frontend: drag-and-drop zone in SetupPage.js
- File type display (uploadedFileName state)
- .txt files handled locally; .docx sent to backend
- Auth headers included in upload requests

### Backend Resiliency (DONE)
- asyncio.wait_for(timeout=45) on every OpenAI API call
- JSON parse failure fallback with _parse_warning flag
- reader_warning / reader_error / reader_complete terminal events
- Queue drain with asyncio.wait_for(timeout=120) safety net
- Extensive logging throughout pipeline

### Frontend Resiliency (DONE)
- 60-second stall detector in useReadingStream.js
- Stall banner with Retry and View Partial Results
- reader_warning → toast.warning(), reader_crashed → toast.error()
- useRef guard preventing double SSE connections (React StrictMode fix)

### Backend Refactor (DONE)
- Split monolithic server.py into config.py, models.py, utils.py, services/, routers/

### Frontend Refactor (DONE)
- ReadingPage.js decomposed into ManuscriptView, ReaderSidebar, CommentPopover, ProgressBar, StallBanner, useReadingStream.js hook

### Reading UI (DONE)
- Continuous scrollable manuscript with margin annotation dots
- Comment popover with reader details and type badges
- Reader sidebar with status, reflections, comment count
- Type filter chips (reaction, prediction, confusion, critique, praise, theory, comparison)
- Auto-reading with SSE streaming
- Reading completion detection + Editor Report generation

### Cosmetic Fix (DONE)
- ManuscriptView.jsx: "1 sections" → "1 section" (proper singular/plural)

## Test Results (Iteration 6 — March 2026)
- Backend: 100% (34/34 tests pass)
- Frontend: 100% (all critical flows pass)
- .docx upload: verified end-to-end
- Auth protection: verified (401 without token)
- totalSections banner bug: confirmed fixed

## Prioritized Backlog

### P2 (Nice to have)
- [ ] PDF export for editor report
- [ ] Payment/Billing integration (Stripe)
- [ ] Landing/marketing page
- [ ] Reader "disagreement" highlighting (divergence visualization)
- [ ] Per-section engagement heatmap tooltips
- [ ] Manuscript version history
- [ ] Export reader memories as character bible

## Next Tasks
1. PDF download for editor report
2. Stripe billing integration
3. Marketing/landing page
4. Disagreement visualization between readers
