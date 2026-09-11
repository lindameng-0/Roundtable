CREATE TABLE IF NOT EXISTS integration_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    permission TEXT NOT NULL CHECK (permission IN ('read', 'run')),
    token_hash TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS integration_keys_user_idx ON integration_keys(user_id);
ALTER TABLE integration_keys ENABLE ROW LEVEL SECURITY;
-- Browser clients have no table policy. Only the backend manages credentials.
