import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load the .env file from the project root.
load_dotenv(PROJECT_ROOT / ".env")


def get_connection(dbname=None):
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    db = dbname or os.getenv("DB_NAME", "smart_inventory")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "2"))

    if not password:
        raise RuntimeError("DB_PASSWORD is not set. Check the project's .env file.")

    return psycopg.connect(
        host=host,
        port=port,
        dbname=db,
        user=user,
        password=password,
        connect_timeout=timeout,
    )
