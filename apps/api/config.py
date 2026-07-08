"""
config.py — Application configuration loaded from environment variables.

All secrets are read from environment variables only. Never hardcode credentials.
On Railway, variables are injected at runtime. Locally, load from .env via python-dotenv.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ------------------------------------------------------------------
# Supabase
# ------------------------------------------------------------------
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "event-files")

# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALLOWED_ORIGINS: list[str] = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000"
).split(",")

# Application metadata
APP_VERSION: str = "1.0.0"
APP_TITLE: str = "VO Event Max API"
APP_DESCRIPTION: str = "Backend API for the VO Event Max conference management platform."

# File upload constraints
MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS: set[str] = {".xlsx", ".xls", ".csv"}

# Pagination defaults
DEFAULT_PAGE_SIZE: int = 50
MAX_PAGE_SIZE: int = 200
