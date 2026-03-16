-- Roundtable Supabase schema (run in SQL Editor)
-- Replaces MongoDB collections: manuscripts, reader_personas, reader_memories, reader_reactions, editor_reports, users, user_sessions

-- Users (from auth flow; session-based)
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT,
  picture TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sessions (Emergent OAuth exchange)
CREATE TABLE IF NOT EXISTS user_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  session_token TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_session_token ON user_sessions(session_token);

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
  sections JSONB DEFAULT '[]',
  total_sections INT DEFAULT 0,
  total_lines INT DEFAULT 0,
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

-- Waitlist (when user hits manuscript limit)
CREATE TABLE IF NOT EXISTS waitlist (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  email TEXT NOT NULL,
  user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS waitlist_email_unique ON waitlist(email);

-- Enable RLS if you want row-level security (optional; use service_role key to bypass)
-- ALTER TABLE manuscripts ENABLE ROW LEVEL SECURITY;
-- etc.
