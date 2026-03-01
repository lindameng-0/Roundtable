import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Provider API keys — set the ones you use; LiteLLM reads these from env for the active provider
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')  # or GOOGLE_API_KEY for Gemini

# Mutable — can be changed at runtime via POST /api/config/model
LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-4o')
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'openai')
