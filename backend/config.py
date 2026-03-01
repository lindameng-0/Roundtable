import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')

# Mutable — can be changed at runtime via POST /api/config/model
LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-4o')
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'openai')
