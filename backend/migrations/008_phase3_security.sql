-- Invalidate existing browser tokens once while moving to cookie-only sessions.
DELETE FROM user_sessions;
ALTER TABLE user_sessions DROP COLUMN IF EXISTS session_token;
ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS token_hash TEXT;
ALTER TABLE user_sessions ALTER COLUMN token_hash SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_sessions_token_hash ON user_sessions(token_hash);

CREATE TABLE IF NOT EXISTS oauth_states (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_oauth_states_expiry ON oauth_states(expires_at);

CREATE TABLE IF NOT EXISTS rate_limit_buckets (
  key TEXT PRIMARY KEY,
  count INTEGER NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_buckets_expiry ON rate_limit_buckets(expires_at);

-- Ownerless manuscripts are intentionally retained for a later, explicit data
-- retention decision, but their anonymous capability credentials are removed.
ALTER TABLE manuscripts DROP COLUMN IF EXISTS access_token_hash;
