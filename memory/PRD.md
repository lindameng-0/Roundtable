# Roundtable — PRD

## Problem Statement
Build a collaborative AI beta reader tool for fiction writers. The app simulates a panel of 5 distinct AI readers who react to manuscript chapters, with each reader having persistent memory. An Editor AI synthesizes their feedback into a professional report.

## Architecture

### Tech Stack
- **Backend:** FastAPI (Python) + Motor/MongoDB async
- **Frontend:** React + Tailwind CSS (Cormorant Garamond + Manrope fonts)
- **LLM:** Emergent Universal Key via `emergentintegrations` (gpt-4o default, switchable)
- **DB:** MongoDB (test_database)

### API Endpoints
- `POST /api/manuscripts` — Upload text, trigger genre detection
- `POST /api/manuscripts/upload` — Upload .txt file
- `GET /api/manuscripts/{id}` — Get manuscript
- `PATCH /api/manuscripts/{id}/genre` — Update genre tags
- `GET /api/manuscripts/{id}/personas` — Get/generate reader personas
- `POST /api/manuscripts/{id}/personas/regenerate` — Regen one or all readers
- `GET /api/manuscripts/{id}/read/{section}` — SSE stream all 5 reader reactions
- `GET /api/manuscripts/{id}/reactions/{section}` — Get reactions for a section
- `POST /api/manuscripts/{id}/editor-report` — Generate editor report
- `GET /api/manuscripts/{id}/editor-report` — Get report
- `GET /api/config/models` — List available models
- `POST /api/config/model` — Switch active model

### MongoDB Collections
- `manuscripts` — raw text, genre, sections
- `reader_personas` — 5 personas per manuscript
- `reader_memories` — per-reader memory JSON per section
- `reader_reactions` — summary + full_thoughts per reader per section
- `editor_reports` — synthesized editorial JSON report

## User Personas
- Fiction writers (novel/short story) seeking beta reader feedback
- Self-published authors preparing for release
- Writing group members wanting objective feedback

## Core Requirements (Static)
1. Manuscript upload (paste or .txt file)
2. Auto genre + audience detection (editable chips)
3. 5 distinct reader personas generated per manuscript (regeneratable)
4. Section-by-section reading with SSE streaming reactions
5. Per-reader memory compression between sections
6. Editor AI report with engagement chart + recommendations
7. Model selector (gpt-4o, claude, gemini, etc.)

## What's Been Implemented (Jan 2026)
- Full setup flow: manuscript → genre detection → reader panel
- 5 reader archetypes: analytical (0.5 temp), emotional (0.9), casual (0.9), skeptical (0.7), genre_savvy (0.7)
- SSE streaming via asyncio.as_completed() — reactions appear as they complete
- Memory compression: analytical keeps 8 events, casual keeps 3, others keep 5
- Editor report: executive summary, consensus findings, character impressions, prediction accuracy, engagement heatmap, 5-7 recommendations
- Model switcher (UI + API) supporting OpenAI, Anthropic, Gemini
- Literary UI: paper #FDFBF7, clay #C86B56, Cormorant Garamond serif

## Prioritized Backlog

### P0 (Critical — not yet implemented)
- [ ] User authentication (JWT or Google OAuth)
- [ ] Manuscript save/resume sessions

### P1 (High value)
- [ ] Reader "disagreement" highlighting (show where readers diverge)
- [ ] Downloadable PDF report
- [ ] Per-section engagement notes on heatmap tooltips
- [ ] .docx file upload support

### P2 (Nice to have)
- [ ] Manuscript version history
- [ ] Inline annotations view (reactions linked to specific paragraphs)
- [ ] Reader "favorites" — readers can flag standout passages
- [ ] Export reader memories as character Bible

## Next Tasks
1. Add auth (JWT or Emergent Google Auth)
2. Add PDF download for editor report
3. .docx upload support
4. Improve disagreement visualization between readers
