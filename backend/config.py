import os
from pathlib import Path
from dotenv import load_dotenv

from db import get_db, get_memory_db, get_postgres_db

# Load .env first so all os.environ reads below see env vars
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip()
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development').strip().lower()
REQUIRE_AUTH = os.environ.get(
    'REQUIRE_AUTH',
    'true' if ENVIRONMENT == 'production' else 'false',
).strip().lower() in {'1', 'true', 'yes', 'on'}
DATABASE_BACKEND = os.environ.get(
    'DATABASE_BACKEND',
    'supabase' if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else 'memory',
).strip().lower()
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()

if DATABASE_BACKEND == 'memory':
    if ENVIRONMENT == 'production':
        raise RuntimeError('DATABASE_BACKEND=memory is not allowed in production')
    db = get_memory_db()
elif DATABASE_BACKEND == 'supabase':
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for DATABASE_BACKEND=supabase')
    db = get_db(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
elif DATABASE_BACKEND == 'postgres':
    if not DATABASE_URL:
        raise RuntimeError('DATABASE_URL is required for DATABASE_BACKEND=postgres')
    db = get_postgres_db(DATABASE_URL, ROOT_DIR / 'migrations')
else:
    raise RuntimeError("DATABASE_BACKEND must be 'memory', 'postgres', or 'supabase'")

# Provider API keys — set the ones you use; LiteLLM reads these from env for the active provider
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
# Gemini: support both GOOGLE_API_KEY and GEMINI_API_KEY
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
GEMINI_API_KEY = GOOGLE_API_KEY  # alias for code that references GEMINI_API_KEY
LLM_BACKEND = os.environ.get(
    'LLM_BACKEND',
    'live' if any([OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY]) else 'mock',
).strip().lower()
if LLM_BACKEND not in {'live', 'mock'}:
    raise RuntimeError("LLM_BACKEND must be 'live' or 'mock'")
if ENVIRONMENT == 'production' and LLM_BACKEND == 'mock':
    raise RuntimeError('LLM_BACKEND=mock is not allowed in production')
MOCK_LLM = LLM_BACKEND == 'mock'

# Mutable — only gpt-4o-mini is used
LLM_MODEL = os.environ.get('LLM_MODEL', 'gemini-2.5-flash')
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'gemini')

# Reader V2 is the production path: it combines reaction and continuity state
# in one budgeted provider call. V1 remains available only for compatibility.
READER_PIPELINE_VERSION = os.environ.get('READER_PIPELINE_VERSION', 'v2').strip().lower()
if READER_PIPELINE_VERSION not in {'v1', 'v2'}:
    raise RuntimeError("READER_PIPELINE_VERSION must be 'v1' or 'v2'")

READER_MODEL_POOL = os.environ.get(
    'READER_MODEL_POOL',
    'gemini:gemini-2.5-flash',
).strip()
MEMORY_MODEL_ROUTE = os.environ.get(
    'MEMORY_MODEL_ROUTE',
    'gemini:gemini-2.5-flash-lite',
).strip()
PERSONA_MODEL_ROUTE = os.environ.get(
    'PERSONA_MODEL_ROUTE',
    'openai:gpt-5.6-luna',
).strip()
EDITOR_MODEL_ROUTE = os.environ.get(
    'EDITOR_MODEL_ROUTE',
    'gemini:gemini-2.5-pro',
).strip()
EDITOR_MAP_MODEL_ROUTE = os.environ.get(
    'EDITOR_MAP_MODEL_ROUTE',
    'openai:gpt-5.6-luna',
).strip()
EDITOR_DIRECT_MAX_CHARS = max(20_000, int(os.environ.get('EDITOR_DIRECT_MAX_CHARS', '220000')))
EDITOR_CHUNK_MAX_CHARS = max(20_000, int(os.environ.get('EDITOR_CHUNK_MAX_CHARS', '70000')))
EDITOR_MAX_CHUNKS = max(2, int(os.environ.get('EDITOR_MAX_CHUNKS', '16')))
COPYEDIT_MODEL_ROUTE = os.environ.get(
    'COPYEDIT_MODEL_ROUTE',
    'openai:gpt-5.6-luna',
).strip()
READER_MAX_CONCURRENCY = max(1, int(os.environ.get('READER_MAX_CONCURRENCY', '2')))
READER_START_STAGGER_SECONDS = max(0.0, float(os.environ.get('READER_START_STAGGER_SECONDS', '2')))
MAX_WORKFLOW_COST_USD = max(0.0, float(os.environ.get('MAX_WORKFLOW_COST_USD', '25')))

# ── Google OAuth (own credentials) ────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
# URI registered in Google Cloud Console — must match exactly
GOOGLE_REDIRECT_URI = os.environ.get(
    'GOOGLE_REDIRECT_URI',
    'http://localhost:8000/api/auth/google/callback',
)
# Frontend origin — backend redirects here after a successful OAuth login
FRONTEND_URL = os.environ.get(
    'FRONTEND_URL',
    os.environ.get('APP_URL', 'http://localhost:3000'),
)
SESSION_COOKIE_SECURE = os.environ.get(
    'SESSION_COOKIE_SECURE', 'true' if ENVIRONMENT == 'production' else 'false'
).strip().lower() in {'1', 'true', 'yes', 'on'}
SESSION_COOKIE_SAMESITE = os.environ.get(
    'SESSION_COOKIE_SAMESITE', 'none' if ENVIRONMENT == 'production' else 'lax'
).strip().lower()
if SESSION_COOKIE_SAMESITE not in {'lax', 'strict', 'none'}:
    raise RuntimeError("SESSION_COOKIE_SAMESITE must be 'lax', 'strict', or 'none'")

# Transactional email for email/password account verification. Resend is used
# through its HTTPS API so no additional runtime dependency is required.
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '').strip()
AUTH_EMAIL_FROM = os.environ.get('AUTH_EMAIL_FROM', 'Roundtable <accounts@roundtable.works>').strip()
EMAIL_VERIFICATION_TTL_MINUTES = max(
    15,
    int(os.environ.get('EMAIL_VERIFICATION_TTL_MINUTES', '60')),
)
PASSWORD_RESET_TTL_MINUTES = max(10, int(os.environ.get('PASSWORD_RESET_TTL_MINUTES', '30')))
AUTH_SIGNUP_RATE_PER_HOUR = max(1, int(os.environ.get('AUTH_SIGNUP_RATE_PER_HOUR', '5')))
AUTH_LOGIN_RATE_PER_15_MINUTES = max(1, int(os.environ.get('AUTH_LOGIN_RATE_PER_15_MINUTES', '10')))
AUTH_EMAIL_RATE_PER_HOUR = max(1, int(os.environ.get('AUTH_EMAIL_RATE_PER_HOUR', '5')))
AUTH_TOKEN_RATE_PER_HOUR = max(1, int(os.environ.get('AUTH_TOKEN_RATE_PER_HOUR', '20')))
MANUSCRIPT_CREATE_RATE_PER_HOUR = max(1, int(os.environ.get('MANUSCRIPT_CREATE_RATE_PER_HOUR', '10')))
MANUSCRIPT_CREATE_IP_RATE_PER_HOUR = max(1, int(os.environ.get('MANUSCRIPT_CREATE_IP_RATE_PER_HOUR', '30')))
AI_ACCOUNT_RATE_PER_HOUR = max(1, int(os.environ.get('AI_ACCOUNT_RATE_PER_HOUR', '30')))
AI_IP_RATE_PER_HOUR = max(1, int(os.environ.get('AI_IP_RATE_PER_HOUR', '60')))
MAX_UPLOAD_MB = max(1, min(100, int(os.environ.get('MAX_UPLOAD_MB', '25'))))

# Admin users bypass usage limits
ADMIN_EMAILS = [
    "itsyuko0o1@gmail.com",
]
