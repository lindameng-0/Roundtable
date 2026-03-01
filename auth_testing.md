# Auth-Gated App Testing Playbook

## Step 1: Create Test User & Session

```bash
DB_NAME=$(grep DB_NAME /app/backend/.env | cut -d '=' -f2)
mongosh --eval "
use('${DB_NAME}');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

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
await page.goto("https://fiction-sync.preview.emergentagent.com/dashboard")
```

## Checklist
- [ ] User document has user_id field (custom UUID)
- [ ] Session user_id matches user's user_id exactly
- [ ] All queries use `{"_id": 0}` projection
- [ ] /api/auth/me returns user data with session token in header or cookie
- [ ] Dashboard loads with past manuscripts for authenticated user
- [ ] Unauthenticated requests to /dashboard redirect to /login

## Quick Debug

```bash
DB_NAME=$(grep DB_NAME /app/backend/.env | cut -d '=' -f2)
mongosh --eval "use('${DB_NAME}'); db.users.find().limit(2).pretty(); db.user_sessions.find().limit(2).pretty();"
```
