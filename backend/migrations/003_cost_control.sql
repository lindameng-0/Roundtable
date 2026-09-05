ALTER TABLE manuscripts
  ADD COLUMN IF NOT EXISTS cost_limit_usd NUMERIC(12,6) NOT NULL DEFAULT 25,
  ADD COLUMN IF NOT EXISTS cost_spent_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cost_reserved_usd NUMERIC(12,6) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS cost_reservations (
  id TEXT PRIMARY KEY,
  manuscript_id TEXT NOT NULL REFERENCES manuscripts(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  operation_key TEXT,
  estimated_cost_usd NUMERIC(12,6) NOT NULL CHECK (estimated_cost_usd >= 0),
  actual_cost_usd NUMERIC(12,6),
  status TEXT NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved', 'completed', 'released')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cost_reservations_manuscript ON cost_reservations(manuscript_id, created_at DESC);

CREATE OR REPLACE FUNCTION reserve_ai_cost(
  p_reservation_id TEXT,
  p_manuscript_id TEXT,
  p_role TEXT,
  p_operation_key TEXT,
  p_estimated_cost_usd NUMERIC
) RETURNS JSONB LANGUAGE plpgsql AS $$
DECLARE m manuscripts%ROWTYPE;
BEGIN
  SELECT * INTO m FROM manuscripts WHERE id = p_manuscript_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Manuscript not found'; END IF;
  IF m.cost_limit_usd > 0 AND m.cost_spent_usd + m.cost_reserved_usd + p_estimated_cost_usd > m.cost_limit_usd THEN
    RETURN jsonb_build_object('reserved', false, 'limit_usd', m.cost_limit_usd,
      'spent_usd', m.cost_spent_usd, 'reserved_usd', m.cost_reserved_usd,
      'requested_usd', p_estimated_cost_usd);
  END IF;
  INSERT INTO cost_reservations(id, manuscript_id, role, operation_key, estimated_cost_usd)
  VALUES(p_reservation_id, p_manuscript_id, p_role, p_operation_key, p_estimated_cost_usd);
  UPDATE manuscripts SET cost_reserved_usd = cost_reserved_usd + p_estimated_cost_usd WHERE id = p_manuscript_id;
  RETURN jsonb_build_object('reserved', true, 'limit_usd', m.cost_limit_usd,
    'spent_usd', m.cost_spent_usd, 'reserved_usd', m.cost_reserved_usd + p_estimated_cost_usd);
END $$;

CREATE OR REPLACE FUNCTION settle_ai_cost(p_reservation_id TEXT, p_actual_cost_usd NUMERIC)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE r cost_reservations%ROWTYPE;
BEGIN
  SELECT * INTO r FROM cost_reservations WHERE id = p_reservation_id FOR UPDATE;
  IF NOT FOUND OR r.status <> 'reserved' THEN RETURN; END IF;
  UPDATE manuscripts SET
    cost_reserved_usd = GREATEST(0, cost_reserved_usd - r.estimated_cost_usd),
    cost_spent_usd = cost_spent_usd + GREATEST(0, p_actual_cost_usd)
  WHERE id = r.manuscript_id;
  UPDATE cost_reservations SET actual_cost_usd = GREATEST(0, p_actual_cost_usd),
    status = 'completed', updated_at = now() WHERE id = p_reservation_id;
END $$;

CREATE OR REPLACE FUNCTION release_ai_cost(p_reservation_id TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE r cost_reservations%ROWTYPE;
BEGIN
  SELECT * INTO r FROM cost_reservations WHERE id = p_reservation_id FOR UPDATE;
  IF NOT FOUND OR r.status <> 'reserved' THEN RETURN; END IF;
  UPDATE manuscripts SET cost_reserved_usd = GREATEST(0, cost_reserved_usd - r.estimated_cost_usd)
  WHERE id = r.manuscript_id;
  UPDATE cost_reservations SET status = 'released', updated_at = now() WHERE id = p_reservation_id;
END $$;
