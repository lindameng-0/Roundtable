CREATE TABLE IF NOT EXISTS ai_jobs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  job_type TEXT NOT NULL CHECK(job_type IN ('reading', 'editor_report', 'copy_edit')),
  idempotency_key TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK(status IN ('queued', 'running', 'completed', 'failed')),
  progress JSONB NOT NULL DEFAULT '{}',
  result JSONB,
  error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_expires_at TIMESTAMPTZ,
  worker_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  UNIQUE(user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_ai_jobs_claim
  ON ai_jobs(status, available_at, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_jobs_user_status
  ON ai_jobs(user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_jobs_manuscript
  ON ai_jobs(manuscript_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_worker_heartbeats (
  worker_id TEXT PRIMARY KEY,
  last_seen TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE editor_reports ADD COLUMN IF NOT EXISTS source_job_id TEXT;
ALTER TABLE report_versions ADD COLUMN IF NOT EXISTS job_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_report_versions_job_id
  ON report_versions(job_id) WHERE job_id IS NOT NULL;
