from __future__ import annotations

import time
from typing import Any

from jose import JWTError, jwt

from .config import settings

ALGORITHM = "HS256"
STATE_TTL_SECONDS = 10 * 60
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60


def create_state(payload: dict[str, Any]) -> str:
    to_encode = {
        **payload,
        "exp": int(time.time()) + STATE_TTL_SECONDS,
        "typ": "state",
    }
    return jwt.encode(to_encode, settings.app_jwt_secret, algorithm=ALGORITHM)


def decode_state(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.app_jwt_secret, algorithms=[ALGORITHM])
    if payload.get("typ") != "state":
        raise JWTError("Invalid state token")
    return payload


def create_session_token(user_id: str, email: str) -> str:
    to_encode = {
        "sub": user_id,
        "email": email,
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
        "typ": "session",
    }
    return jwt.encode(to_encode, settings.app_jwt_secret, algorithm=ALGORITHM)


def decode_session_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.app_jwt_secret, algorithms=[ALGORITHM])
    if payload.get("typ") != "session":
        raise JWTError("Invalid session token")
    return payload
