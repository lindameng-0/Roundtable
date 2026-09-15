-- Signup-funnel counters plus pseudonymous visitor deduplication.
-- Raw IP addresses are never stored. The application supplies an HMAC digest.
CREATE TABLE IF NOT EXISTS site_analytics_visitors (
  day DATE NOT NULL,
  path TEXT NOT NULL,
  source TEXT NOT NULL,
  event TEXT NOT NULL,
  visitor_hash TEXT NOT NULL,
  PRIMARY KEY (day, path, source, event, visitor_hash)
);
ALTER TABLE site_analytics_visitors ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION record_site_analytics(
  p_path TEXT, p_source TEXT, p_event TEXT, p_visitor_hash TEXT DEFAULT NULL
)
RETURNS VOID LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
  INSERT INTO site_analytics(day, path, source, event, count)
  VALUES ((now() AT TIME ZONE 'UTC')::date, p_path, p_source, p_event, 1)
  ON CONFLICT (day, path, source, event)
  DO UPDATE SET count = site_analytics.count + 1;

  IF p_visitor_hash IS NOT NULL THEN
    INSERT INTO site_analytics_visitors(day, path, source, event, visitor_hash)
    VALUES ((now() AT TIME ZONE 'UTC')::date, p_path, p_source, p_event, p_visitor_hash)
    ON CONFLICT DO NOTHING;
  END IF;

  DELETE FROM site_analytics WHERE day < (now() AT TIME ZONE 'UTC')::date - 400;
  DELETE FROM site_analytics_visitors WHERE day < (now() AT TIME ZONE 'UTC')::date - 90;
END;
$$;
REVOKE ALL ON FUNCTION record_site_analytics(TEXT, TEXT, TEXT, TEXT) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    GRANT EXECUTE ON FUNCTION record_site_analytics(TEXT, TEXT, TEXT, TEXT) TO service_role;
    GRANT SELECT, INSERT, DELETE ON site_analytics_visitors TO service_role;
  END IF;
END $$;
