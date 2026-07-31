"""Application configuration.

Database location is derived from the application root, not the current
working directory, so behaviour does not change depending on where a
script or test happens to be invoked from.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"

load_dotenv(BASE_DIR / ".env")

DEFAULT_SQLITE_PATH = INSTANCE_DIR / "app.db"


def get_database_url() -> str:
    """Return the configured database URL.

    Defaults to a SQLite file under the application's instance directory.
    Set DATABASE_URL (e.g. postgresql+psycopg2://user:pass@host/dbname) to
    use PostgreSQL instead - no code changes required.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"


ACCOUNT_LOCKOUT_THRESHOLD = int(os.environ.get("ACCOUNT_LOCKOUT_THRESHOLD", "5"))
ACCOUNT_LOCKOUT_MINUTES = int(os.environ.get("ACCOUNT_LOCKOUT_MINUTES", "15"))

# Used to sign API access tokens (ai_wasteguard/tokens.py). The default is
# fine for local development only - any real deployment MUST override this
# via the API_SECRET_KEY environment variable, or every deployment sharing
# the default would accept each other's tokens.
API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "dev-insecure-secret-change-me-before-any-real-deployment")
API_TOKEN_EXPIRY_MINUTES = int(os.environ.get("API_TOKEN_EXPIRY_MINUTES", "60"))
