# Database setup (Supabase)

The app needs these tables in your Supabase project. If you see:

`Could not find the table 'public.manuscripts' in the schema cache`

then the schema has not been applied yet.

## Steps

1. Open your [Supabase Dashboard](https://supabase.com/dashboard) and select your project.
2. Go to **SQL Editor**.
3. Copy the contents of `supabase_schema.sql` (in this folder) and paste into a new query.
4. Click **Run** (or press Ctrl+Enter).

Tables are created in order: `users`, `user_sessions`, `manuscripts`, `reader_personas`, `reader_memories`, `reader_reactions`, `editor_reports`. The script uses `CREATE TABLE IF NOT EXISTS`, so it's safe to run more than once.

### If you already had the database (reader refactor)

If you see:

`Could not find the 'persona_block' column of 'reader_personas' in the schema cache`

run **`supabase_migration_reader_refactor.sql`** in the SQL Editor instead. It adds the `persona_block` and `response_json` columns required by the refactored reader pipeline.

After it runs, retry the request that failed.
