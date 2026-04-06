from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from fastapi import Cookie, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError

from .auth import create_session_token, create_state, decode_session_token, decode_state
from .config import settings
from .google_oauth import (
    OAuthConfigError,
    build_auth_url,
    exchange_code_for_tokens,
    fetch_userinfo,
)
from .storage import upsert_user

app = FastAPI(title="Tollgate API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _normalize_redirect(redirect: str | None) -> str:
    if not redirect:
        return settings.web_origin.rstrip("/") + "/dashboard"
    if redirect.startswith("http://") or redirect.startswith("https://"):
        return redirect
    if not redirect.startswith("/"):
        redirect = "/" + redirect
    return settings.web_origin.rstrip("/") + redirect


def _append_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query.update(params)
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/auth/google/start")
async def google_auth_start(redirect: str | None = None) -> RedirectResponse:
    try:
        redirect_url = _normalize_redirect(redirect)
        state = create_state({"redirect": redirect_url})
        auth_url = build_auth_url(state)
        return RedirectResponse(auth_url)
    except OAuthConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/auth/google/callback")
async def google_auth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    redirect_url = settings.web_origin.rstrip("/") + "/?auth=error"

    if error:
        redirect_url = _append_query(redirect_url, {"error": error})
        return RedirectResponse(redirect_url)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    try:
        decoded_state = decode_state(state)
        redirect_url = decoded_state.get("redirect", redirect_url)
    except JWTError:
        redirect_url = _append_query(redirect_url, {"error": "invalid_state"})
        return RedirectResponse(redirect_url)

    try:
        tokens = await exchange_code_for_tokens(code)
        access_token = tokens.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Missing access token")

        userinfo = await fetch_userinfo(access_token)
        user_id = userinfo.get("id") or userinfo.get("sub")
        if not user_id:
            raise HTTPException(status_code=400, detail="Missing user id")

        google_tokens = {
            "access_token": access_token,
            "expires_at": int(time.time()) + int(tokens.get("expires_in", 0)),
            "scope": tokens.get("scope"),
            "token_type": tokens.get("token_type"),
        }
        if tokens.get("refresh_token"):
            google_tokens["refresh_token"] = tokens.get("refresh_token")

        user_record: dict[str, Any] = {
            "id": user_id,
            "email": userinfo.get("email"),
            "google_tokens": google_tokens,
        }
        await upsert_user(user_record)

        session_token = create_session_token(user_id, user_record["email"] or "")
        response = RedirectResponse(_append_query(redirect_url, {"auth": "success"}))
        response.set_cookie(
            key=settings.session_cookie_name,
            value=session_token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
        )
        return response
    except OAuthConfigError as exc:
        redirect_url = _append_query(redirect_url, {"error": str(exc)})
        return RedirectResponse(redirect_url)


@app.get("/me")
async def me(
    session: str | None = Cookie(default=None, alias=settings.session_cookie_name)
) -> JSONResponse:
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_session_token(session)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid session")

    email = payload.get("email")
    return JSONResponse({"id": user_id, "email": email})


@app.post("/auth/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(settings.session_cookie_name)
    return response
