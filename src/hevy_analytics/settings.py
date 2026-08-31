import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / "data" / "hevy.db"
LANDMARKS_PATH = PROJECT_ROOT / "config" / "landmarks.yaml"
CONTEXT_PATH = PROJECT_ROOT / "config" / "context.yaml"

HEVY_API_KEY = os.environ.get("HEVY_API_KEY", "")
HEVY_BASE_URL = "https://api.hevyapp.com/v1"

REQUEST_DELAY_SECONDS = 0.3
PAGE_SIZE = 10
MAX_RETRIES = 3

EPOCH_CURSOR = "1970-01-01T00:00:00Z"
