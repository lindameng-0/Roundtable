# Auth-Gated App Testing Playbook

## Step 1: Create Test User & Session

**Option A: Supabase (current backend)**  
In Supabase SQL Editor or via API, insert a test user and session:

```sql
INSERT INTO users (user_id, email, name, picture, created_at)
VALUES (
  'test-user-' || extract(epoch from now())::bigint,
  'test.user.' || extract(epoch from now())::bigint || '@example.com',
  'Test User',
  'https://via.placeholder.com/150',
  now()
)
RETURNING user_id;

-- Use the returned user_id in the next insert; set session_token for auth header.
INSERT INTO user_sessions (user_id, session_token, expires_at, created_at)
VALUES (
  '<user_id from above>',
  'test_session_' || extract(epoch from now())::bigint,
  now() + interval '7 days',
  now()
);
-- Use the session_token value as Bearer token.
```

**Option B: MongoDB (legacy)**  
If using MongoDB, use mongosh with DB_NAME from .env to insert into `users` and `user_sessions` and copy the session_token.

## Step 2: Test Backend API

```bash
API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
SESSION_TOKEN="<token from step 1>"

curl -X GET "$API_URL/api/auth/me" -H "Authorization: Bearer $SESSION_TOKEN"
curl -X GET "$API_URL/api/manuscripts" -H "Authorization: Bearer $SESSION_TOKEN"
```

## Step 3: Browser Testing

```python
await page.context.add_cookies([{
    "name": "session_token",
    "value": "YOUR_SESSION_TOKEN",
    "domain": "fiction-sync.preview.emergentagent.com",
    "path": "/",
    "httpOnly": True,
    "secure": True,
    "sameSite": "None"
}])
await page.goto("https://ai-roundtable-test.preview.emergentagent.com/dashboard")
```

## Checklist
- [ ] User document has user_id field (custom UUID)
- [ ] Session user_id matches user's user_id exactly
- [ ] All queries use `{"_id": 0}` projection
- [ ] /api/auth/me returns user data with session token in header or cookie
- [ ] Dashboard loads with past manuscripts for authenticated user
- [ ] Unauthenticated requests to /dashboard redirect to /login

## Quick Debug

**Supabase:** In SQL Editor: `SELECT * FROM users LIMIT 2; SELECT * FROM user_sessions LIMIT 2;`
