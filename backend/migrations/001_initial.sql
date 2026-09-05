CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT, picture TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS user_sessions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  session_token TEXT NOT NULL UNIQUE, expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS manuscripts (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  access_token_hash TEXT, raw_text TEXT NOT NULL, genre TEXT, target_audience TEXT, age_range TEXT,
  comparable_books JSONB NOT NULL DEFAULT '[]', model TEXT NOT NULL DEFAULT 'gemini-2.5-flash',
  sections JSONB NOT NULL DEFAULT '[]', total_sections INT NOT NULL DEFAULT 0, total_lines INT NOT NULL DEFAULT 0,
  cost_limit_usd NUMERIC(12,6) NOT NULL DEFAULT 25, cost_spent_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
  cost_reserved_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
  reader_config_locked BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reader_personas (
  id TEXT PRIMARY KEY, manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  name TEXT NOT NULL, age INT DEFAULT 35, occupation TEXT, personality TEXT, reading_habits TEXT,
  favorite_genres TEXT, genre_preferences TEXT, reading_priority TEXT, liked_tropes JSONB DEFAULT '[]',
  disliked_tropes JSONB DEFAULT '[]', voice_style TEXT, temperature FLOAT DEFAULT 0.7, quote TEXT,
  avatar_index INT DEFAULT 0, personality_specific_instructions TEXT, persona_block TEXT, attention_mode TEXT,
  primary_focus TEXT, secondary_focuses JSONB NOT NULL DEFAULT '[]', writer_focus_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reader_memories (
  id TEXT PRIMARY KEY, manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  reader_id TEXT NOT NULL, section_number INT NOT NULL, memory_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(manuscript_id, reader_id, section_number)
);
CREATE TABLE IF NOT EXISTS reader_reactions (
  id TEXT PRIMARY KEY, manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  reader_id TEXT NOT NULL, reader_name TEXT NOT NULL, section_number INT NOT NULL,
  inline_comments JSONB NOT NULL DEFAULT '[]', section_reflection TEXT, response_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(manuscript_id, reader_id, section_number)
);
CREATE TABLE IF NOT EXISTS editor_reports (
  id TEXT PRIMARY KEY, manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE UNIQUE,
  report_json JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS workflow_tasks (
  id TEXT PRIMARY KEY, manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  reader_id TEXT NOT NULL, reader_name TEXT NOT NULL, section_number INT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','completed','failed')),
  attempts INT NOT NULL DEFAULT 0, planned_provider TEXT, planned_model TEXT, actual_provider TEXT,
  actual_model TEXT, last_error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(manuscript_id, reader_id, section_number)
);
CREATE TABLE IF NOT EXISTS waitlist (
  id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS feedback (
  id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL, message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_manuscripts_user ON manuscripts(user_id);
CREATE INDEX IF NOT EXISTS idx_reactions_manuscript ON reader_reactions(manuscript_id);
CREATE INDEX IF NOT EXISTS idx_workflow_manuscript ON workflow_tasks(manuscript_id);
