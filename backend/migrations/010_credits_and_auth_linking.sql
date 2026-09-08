-- Retire passwords that the former automatic linking flow may have verified.
ALTER TABLE email_verification_tokens ADD COLUMN credential_hash TEXT;
DELETE FROM user_sessions WHERE user_id IN (SELECT user_id FROM users WHERE auth_provider = 'email,google');
DELETE FROM email_verification_tokens WHERE user_id IN (SELECT user_id FROM users WHERE auth_provider = 'email,google');
DELETE FROM password_reset_tokens WHERE user_id IN (SELECT user_id FROM users WHERE auth_provider = 'email,google');
UPDATE users SET password_hash = NULL, auth_provider = 'google' WHERE auth_provider = 'email,google';

CREATE TABLE credit_wallets (
  id TEXT PRIMARY KEY,
  version BIGINT NOT NULL DEFAULT 0,
  data JSONB NOT NULL DEFAULT '{}'
);
CREATE TABLE credit_entries (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX credit_entries_user ON credit_entries(user_id, created_at DESC);
ALTER TABLE credit_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_entries ENABLE ROW LEVEL SECURITY;

-- Compare-and-swap and audit receipt commit together. Retrying an operation
-- can never apply a second grant or settlement, even across API instances.
CREATE OR REPLACE FUNCTION apply_credit_change(p_user TEXT, p_version BIGINT,
  p_data JSONB, p_key TEXT, p_entry JSONB) RETURNS BOOLEAN
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO credit_wallets(id) VALUES(p_user) ON CONFLICT DO NOTHING;
  PERFORM 1 FROM credit_wallets WHERE id = p_user FOR UPDATE;
  IF EXISTS(SELECT 1 FROM credit_entries WHERE id = p_key) THEN RETURN FALSE; END IF;
  UPDATE credit_wallets SET data = p_data, version = version + 1
    WHERE id = p_user AND version = p_version;
  IF NOT FOUND THEN RETURN FALSE; END IF;
  INSERT INTO credit_entries(id, user_id, data) VALUES(p_key, p_user, p_entry);
  RETURN TRUE;
END;
$$;
REVOKE ALL ON FUNCTION apply_credit_change(TEXT, BIGINT, JSONB, TEXT, JSONB) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    GRANT ALL ON credit_wallets, credit_entries TO service_role;
    GRANT EXECUTE ON FUNCTION apply_credit_change(TEXT, BIGINT, JSONB, TEXT, JSONB) TO service_role;
  END IF;
END $$;
