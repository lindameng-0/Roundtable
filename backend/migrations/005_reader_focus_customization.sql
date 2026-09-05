ALTER TABLE manuscripts
  ADD COLUMN IF NOT EXISTS reader_config_locked BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE reader_personas
  ADD COLUMN IF NOT EXISTS primary_focus TEXT,
  ADD COLUMN IF NOT EXISTS secondary_focuses JSONB NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS writer_focus_note TEXT;
