CREATE OR REPLACE FUNCTION release_stale_ai_cost(p_older_than_minutes INT DEFAULT 120)
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE reservation RECORD; released_count INT := 0;
BEGIN
  FOR reservation IN
    SELECT id FROM cost_reservations
    WHERE status = 'reserved' AND updated_at < now() - make_interval(mins => p_older_than_minutes)
  LOOP
    PERFORM release_ai_cost(reservation.id);
    released_count := released_count + 1;
  END LOOP;
  RETURN released_count;
END $$;
