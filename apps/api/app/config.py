from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    web_origin: str
    app_jwt_secret: str
    cookie_secure: bool
    supabase_url: str | None
    supabase_service_role_key: str | None
    session_cookie_name: str
    gmail_scopes: list[str]
    claude_api_key: str | None
    claude_model: str
    claude_api_url: str


def load_settings() -> Settings:
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
    )
    web_origin = os.getenv("WEB_ORIGIN", "http://localhost:3000")
    app_jwt_secret = os.getenv("APP_JWT_SECRET", "dev-secret-change-me")
    cookie_secure = _get_bool("COOKIE_SECURE", False)
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    session_cookie_name = os.getenv("SESSION_COOKIE_NAME", "tg_session")
    claude_api_key = os.getenv("CLAUDE_API_KEY")
    claude_model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
    claude_api_url = os.getenv("CLAUDE_API_URL", "https://api.anthropic.com/v1/messages")
    gmail_scopes = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]

    return Settings(
        google_client_id=google_client_id,
        google_client_secret=google_client_secret,
        google_redirect_uri=google_redirect_uri,
        web_origin=web_origin,
        app_jwt_secret=app_jwt_secret,
        cookie_secure=cookie_secure,
        supabase_url=supabase_url,
        supabase_service_role_key=supabase_service_role_key,
        session_cookie_name=session_cookie_name,
        gmail_scopes=gmail_scopes,
        claude_api_key=claude_api_key,
        claude_model=claude_model,
        claude_api_url=claude_api_url,
    )


settings = load_settings()
