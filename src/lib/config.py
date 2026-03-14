import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

# Load .env from project root, then from src/
load_dotenv(os.path.join(PROJECT_DIR, ".env"))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _is_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]
    SQLITE_PATH = os.path.join(PROJECT_DIR, "instance", "virtual_greenhouse.db")
    SENSOR_INGEST_TOKEN = os.environ["SENSOR_INGEST_TOKEN"]
