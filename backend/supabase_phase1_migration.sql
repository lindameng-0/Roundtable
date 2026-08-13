-- Roundtable Phase 1 compatibility migration.
-- Safe to run repeatedly on an existing Supabase database.

ALTER TABLE manuscripts
  ADD COLUMN IF NOT EXISTS access_token_hash TEXT;

ALTER TABLE manuscripts
  ADD COLUMN IF NOT EXISTS model TEXT NOT NULL DEFAULT 'gemini-2.5-flash';

CREATE INDEX IF NOT EXISTS idx_manuscripts_access_token_hash
  ON manuscripts(access_token_hash);

CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id);

-- Prevent duplicate reader results for one reader/section. If either index
-- fails, inspect and remove existing duplicates before rerunning the migration.
CREATE UNIQUE INDEX IF NOT EXISTS reader_reactions_one_per_reader_section
  ON reader_reactions(manuscript_id, reader_id, section_number);

CREATE UNIQUE INDEX IF NOT EXISTS reader_memories_one_per_reader_section
  ON reader_memories(manuscript_id, reader_id, section_number);
