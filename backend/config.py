import os
from pathlib import Path
from dotenv import load_dotenv

from db import get_db

# Load .env first so all os.environ reads below see env vars
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_SERVICE_ROLE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']
db = get_db(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Provider API keys — set the ones you use; LiteLLM reads these from env for the active provider
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')  # or GOOGLE_API_KEY for Gemini

# Mutable — only gpt-4o-mini is used
LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-4o-mini')
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'openai')

# Admin users bypass usage limits
ADMIN_EMAILS = [
    "itsyuko0o1@gmail.com",
]

# Google OAuth (redirect flow) — used when not using Emergent
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
FRONTEND_URL = (os.environ.get("FRONTEND_URL") or "http://localhost:3000").rstrip("/")
BACKEND_URL = (os.environ.get("BACKEND_URL") or os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8000").rstrip("/")
