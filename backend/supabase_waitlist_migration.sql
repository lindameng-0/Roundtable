-- Waitlist table for usage limit flow. Run in Supabase SQL Editor.
-- Option A: If you use Supabase Auth (auth.users), use this:
/*
CREATE TABLE IF NOT EXISTS waitlist (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email TEXT NOT NULL,
    user_id UUID REFERENCES auth.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS waitlist_email_unique ON waitlist(email);
*/

-- Option B: If you use the app's custom users table (user_id TEXT), use this:
CREATE TABLE IF NOT EXISTS waitlist (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email TEXT NOT NULL,
    user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS waitlist_email_unique ON waitlist(email);
