-- Only anonymous daily counters; no visitor IDs, manuscript data or raw URLs.
CREATE TABLE IF NOT EXISTS site_analytics (
  day DATE NOT NULL,
  path TEXT NOT NULL,
  source TEXT NOT NULL,
  event TEXT NOT NULL,
  count BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (day, path, source, event)
);
ALTER TABLE site_analytics ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION increment_site_analytics(p_path TEXT, p_source TEXT, p_event TEXT)
RETURNS VOID LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
  INSERT INTO site_analytics(day, path, source, event, count)
  VALUES ((now() AT TIME ZONE 'UTC')::date, p_path, p_source, p_event, 1)
  ON CONFLICT (day, path, source, event)
  DO UPDATE SET count = site_analytics.count + 1;
  DELETE FROM site_analytics WHERE day < (now() AT TIME ZONE 'UTC')::date - 400;
END;
$$;
REVOKE ALL ON FUNCTION increment_site_analytics(TEXT, TEXT, TEXT) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    GRANT EXECUTE ON FUNCTION increment_site_analytics(TEXT, TEXT, TEXT) TO service_role;
    GRANT SELECT, INSERT, UPDATE, DELETE ON site_analytics TO service_role;
  END IF;
END $$;
