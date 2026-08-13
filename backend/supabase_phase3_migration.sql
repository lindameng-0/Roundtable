-- Phase 3: resumable reader/section workflow ledger.
CREATE TABLE IF NOT EXISTS workflow_tasks (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  reader_id TEXT NOT NULL,
  reader_name TEXT NOT NULL,
  section_number INT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  attempts INT NOT NULL DEFAULT 0,
  planned_provider TEXT,
  planned_model TEXT,
  actual_provider TEXT,
  actual_model TEXT,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (manuscript_id, reader_id, section_number)
);
CREATE INDEX IF NOT EXISTS idx_workflow_tasks_manuscript ON workflow_tasks(manuscript_id);
