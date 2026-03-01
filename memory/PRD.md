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

## What's Been Implemented (Feb 2026 — v3 resiliency update)
- **Backend resiliency (6-point plan, fully tested)**:
  - `asyncio.wait_for(timeout=45)` on every OpenAI API call in `get_reader_inline_reaction()`
  - JSON parse failure fallback: returns partial data + `_parse_warning` flag instead of crashing
  - `process_reader()` emits `reader_warning` (non-terminal) + `reader_complete` (terminal), or `reader_error` on timeout
  - Queue drain changed from count-based to terminal-event-based with `asyncio.wait_for(timeout=120)` absolute safety net
  - `return_exceptions=True` on `asyncio.gather` (already existed, confirmed)
  - Extensive `logger.info/warning/error` logging at every pipeline step
- **Frontend stall detection**:
  - `lastEventTimeRef` tracks time of last SSE event
  - `useEffect` polls every 10 seconds; sets `isStalled=true` if 60s elapsed with no events
  - Stall banner (`data-testid=stall-warning-banner`) appears with **Retry** and **View partial results** buttons
  - `handleRetry()` closes old stream and restarts reading (backend skips completed sections)
  - `handleViewPartial()` marks reading as done and allows report generation with partial data
- **New SSE event types handled on frontend**:
  - `reader_warning` → `toast.warning()` (soft, 4s)
  - `reader_crashed` → `toast.error()` + clears from ThinkingStrip
  - `reading_complete` → alias for `all_complete` (for forward compatibility)
  - `reader_error` → also now clears the reader from ThinkingStrip


- **Auto-reading**: clicking Start Reading triggers full automatic read of all sections via `/read-all` SSE endpoint. No manual section navigation.
- **Inline annotations**: reader output is JSON `{inline_comments: [{line, type, comment}], section_reflection, memory_update}`. Line numbers are global across the full manuscript.
- **Continuous manuscript view**: full manuscript rendered as scrollable document with all sections. Each paragraph has a `data-line` attribute.
- **Margin dots**: colored dots in left margin per paragraph with comments. Multiple readers stack. Click to open popover.
- **Comment popover**: shows all reader comments for that line with reader avatar, name, type badge (color-coded), and comment text. Closes on Escape or click-away.
- **Reader sidebar panels**: per-reader collapsible panels showing status (Reading section N / Done), section reflections, comment count, and "show all comments" toggle.
- **Type filter**: 7 comment types (reaction, prediction, confusion, critique, praise, theory, comparison) filterable via chips.
- **Persona generation**: now includes `personality_specific_instructions` for each reader's unique analytical lens.
- **Editor report**: adapted to read from inline_comments format.
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
