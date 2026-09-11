ALTER TABLE users
  ADD COLUMN IF NOT EXISTS password_hash TEXT,
  ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'email';

-- Every user created before this migration came from the established Google
-- OAuth flow, so preserve their access as verified Google accounts.
UPDATE users
SET email_verified = true,
    auth_provider = CASE
      WHEN password_hash IS NULL THEN 'google'
      ELSE auth_provider
    END;

CREATE TABLE IF NOT EXISTS email_verification_tokens (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_user
  ON email_verification_tokens(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_hash
  ON email_verification_tokens(token_hash);
