"""Make backend tests deterministic regardless of a developer's local .env."""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Set these before test modules import config/server. python-dotenv does not
# override existing values, so private local credentials cannot turn unit tests
# into networked integration tests.
os.environ["DATABASE_BACKEND"] = "memory"
os.environ["LLM_BACKEND"] = "mock"
os.environ["ENVIRONMENT"] = "test"
os.environ["READER_PIPELINE_VERSION"] = "v1"
