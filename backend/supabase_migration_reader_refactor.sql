-- Run this in Supabase SQL Editor to add columns required by the reader pipeline refactor.
-- Fixes: PGRST204 "Could not find the 'persona_block' column" and same for 'response_json'.

-- Reader personas: add persona_block (full persona text for system prompt) and attention_mode (SUBTEXT, MOMENTUM, etc.)
ALTER TABLE reader_personas
  ADD COLUMN IF NOT EXISTS persona_block TEXT;
ALTER TABLE reader_personas
  ADD COLUMN IF NOT EXISTS attention_mode TEXT;

-- Reader reactions: add response_json (new schema: checking_in, reading_journal, moments, etc.)
ALTER TABLE reader_reactions
  ADD COLUMN IF NOT EXISTS response_json JSONB DEFAULT '{}';

-- Reload PostgREST schema cache so API sees new columns immediately (Supabase may do this automatically)
NOTIFY pgrst, 'reload schema';
