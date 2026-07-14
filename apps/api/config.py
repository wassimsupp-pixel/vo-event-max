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

# ------------------------------------------------------------------
# Mail connection (OAuth) — Email Agent inbox sync
# ------------------------------------------------------------------
# OAuth *app* credentials, provisioned by the operator (see
# docs/mail-connection-setup.md). Leave a provider's client id/secret empty to
# disable it. Never commit real secrets — these are read from env vars only.
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

MICROSOFT_CLIENT_ID: str = os.getenv("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET: str = os.getenv("MICROSOFT_CLIENT_SECRET", "")
# "common" allows both personal and work/school accounts; set a tenant id to
# restrict to one organisation.
MICROSOFT_TENANT_ID: str = os.getenv("MICROSOFT_TENANT_ID", "common")

# Redirect URI registered in the OAuth app; must point at this API's
# /api/mail/oauth/callback route (e.g. https://<api-host>/api/mail/oauth/callback).
MAIL_OAUTH_REDIRECT_URI: str = os.getenv("MAIL_OAUTH_REDIRECT_URI", "")
# Frontend base URL the callback bounces the user back to after consent.
WEB_APP_URL: str = os.getenv("WEB_APP_URL", "http://localhost:3000")
# How many of the most recent inbox messages to pull per manual sync.
MAIL_SYNC_MAX_MESSAGES: int = int(os.getenv("MAIL_SYNC_MAX_MESSAGES", "20"))
