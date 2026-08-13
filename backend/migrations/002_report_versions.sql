CREATE TABLE IF NOT EXISTS report_versions (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  version INT NOT NULL,
  report_json JSONB NOT NULL DEFAULT '{}',
  reason TEXT NOT NULL DEFAULT 'generated',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(manuscript_id, version)
);
CREATE INDEX IF NOT EXISTS idx_report_versions_manuscript ON report_versions(manuscript_id, version DESC);
