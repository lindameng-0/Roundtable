-- Roundtable Supabase schema (run in SQL Editor)
-- Replaces MongoDB collections: manuscripts, reader_personas, reader_memories, reader_reactions, editor_reports, users, user_sessions

-- Users (from auth flow; session-based)
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT,
  picture TEXT,
  password_hash TEXT,
  email_verified BOOLEAN NOT NULL DEFAULT false,
  auth_provider TEXT NOT NULL DEFAULT 'email',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sessions (Emergent OAuth exchange)
CREATE TABLE IF NOT EXISTS user_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_token_hash ON user_sessions(token_hash);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_user
  ON email_verification_tokens(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user
  ON password_reset_tokens(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS oauth_states (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rate_limit_buckets (
  key TEXT PRIMARY KEY,
  count INTEGER NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL
);

-- Manuscripts
CREATE TABLE IF NOT EXISTS manuscripts (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  raw_text TEXT NOT NULL,
  genre TEXT,
  target_audience TEXT,
  age_range TEXT,
  comparable_books JSONB DEFAULT '[]',
  model TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
  sections JSONB DEFAULT '[]',
  total_sections INT DEFAULT 0,
  total_lines INT DEFAULT 0,
  cost_limit_usd NUMERIC(12,6) NOT NULL DEFAULT 25,
  cost_spent_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
  cost_reserved_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
  reader_config_locked BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_manuscripts_user_id ON manuscripts(user_id);

-- Reader personas (5 per manuscript)
CREATE TABLE IF NOT EXISTS reader_personas (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  age INT DEFAULT 35,
  occupation TEXT,
  personality TEXT,
  reading_habits TEXT,
  favorite_genres TEXT,
  genre_preferences TEXT,
  reading_priority TEXT,
  liked_tropes JSONB DEFAULT '[]',
  disliked_tropes JSONB DEFAULT '[]',
  voice_style TEXT,
  temperature FLOAT DEFAULT 0.7,
  quote TEXT,
  avatar_index INT DEFAULT 0,
  personality_specific_instructions TEXT,
  persona_block TEXT,
  attention_mode TEXT,
  primary_focus TEXT,
  secondary_focuses JSONB NOT NULL DEFAULT '[]',
  writer_focus_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- If table exists without new columns: run supabase_migration_reader_refactor.sql
CREATE INDEX IF NOT EXISTS idx_reader_personas_manuscript_id ON reader_personas(manuscript_id);

-- Reader memories (per reader per section)
CREATE TABLE IF NOT EXISTS reader_memories (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  reader_id TEXT NOT NULL,
  section_number INT NOT NULL,
  memory_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reader_memories_manuscript_reader ON reader_memories(manuscript_id, reader_id);

-- Reader reactions (new schema: checking_in, reading_journal, what_i_think_the_writer_is_doing, moments, questions_for_writer; legacy inline_comments/section_reflection kept for compat)
CREATE TABLE IF NOT EXISTS reader_reactions (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  reader_id TEXT NOT NULL,
  reader_name TEXT NOT NULL,
  section_number INT NOT NULL,
  inline_comments JSONB DEFAULT '[]',
  section_reflection TEXT,
  response_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- If table already exists without response_json: ALTER TABLE reader_reactions ADD COLUMN IF NOT EXISTS response_json JSONB DEFAULT '{}';
CREATE INDEX IF NOT EXISTS idx_reader_reactions_manuscript ON reader_reactions(manuscript_id);
CREATE INDEX IF NOT EXISTS idx_reader_reactions_manuscript_section ON reader_reactions(manuscript_id, section_number);

-- Editor reports (one per manuscript)
CREATE TABLE IF NOT EXISTS editor_reports (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE UNIQUE,
  report_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_editor_reports_manuscript_id ON editor_reports(manuscript_id);

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

-- Deterministic Phase 3 task ledger (one reader task per manuscript section)
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

-- Waitlist (when user hits manuscript limit)
CREATE TABLE IF NOT EXISTS waitlist (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  email TEXT NOT NULL,
  user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS waitlist_email_unique ON waitlist(email);

-- Product feedback submitted from the setup/usage-limit screen
CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id);

-- Phase 6 cost controls. Existing installations should run migrations/003_cost_control.sql
-- so the atomic reserve/settle functions are installed as well.
CREATE TABLE IF NOT EXISTS cost_reservations (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  operation_key TEXT,
  estimated_cost_usd NUMERIC(12,6) NOT NULL,
  actual_cost_usd NUMERIC(12,6),
  status TEXT NOT NULL DEFAULT 'reserved',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enable RLS if you want row-level security (optional; use service_role key to bypass)
-- ALTER TABLE manuscripts ENABLE ROW LEVEL SECURITY;
-- etc.
