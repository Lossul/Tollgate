from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from fastapi import Cookie, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError
from pydantic import BaseModel, Field

from .auth import create_session_token, create_state, decode_session_token, decode_state
from .config import settings
from .gmail import GmailAPIError, get_message_metadata, list_messages
from .google_oauth import (
    OAuthConfigError,
    build_auth_url,
    exchange_code_for_tokens,
    fetch_userinfo,
    refresh_access_token,
)
from .storage import get_user, list_trials, upsert_trials, upsert_user
from .trial_parser import parse_trial_email
from .trial_utils import days_remaining, status_from_end_date

app = FastAPI(title="Tollgate API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_origin_regex=r"^https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?$",
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


def _require_session(session: str | None) -> dict[str, str]:
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_session_token(session)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid session")
    return {"user_id": user_id, "email": payload.get("email", "")}


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
    session_info = _require_session(session)
    return JSONResponse({"id": session_info["user_id"], "email": session_info["email"]})


class ScanRequest(BaseModel):
    max_results: int = Field(default=50, ge=1, le=200)
    query: str | None = None


@app.post("/scan")
async def scan_inbox(
    payload: ScanRequest,
    session: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> JSONResponse:
    session_info = _require_session(session)
    user_id = session_info["user_id"]
    user = await get_user(user_id)
    if not user or not user.get("google_tokens"):
        raise HTTPException(status_code=400, detail="Missing Google tokens")

    tokens = user["google_tokens"]
    access_token = tokens.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access token")

    expires_at = tokens.get("expires_at") or 0
    if expires_at and expires_at <= int(time.time()) + 60:
        refresh_token = tokens.get("refresh_token")
        if refresh_token:
            refreshed = await refresh_access_token(refresh_token)
            access_token = refreshed.get("access_token", access_token)
            tokens["access_token"] = access_token
            tokens["expires_at"] = int(time.time()) + int(refreshed.get("expires_in", 0))
            user["google_tokens"] = tokens
            await upsert_user(user)

    query = payload.query or 'newer_than:1y (trial OR \"free trial\" OR \"trial ends\" OR \"trial ending\" OR subscription OR billing)'
    try:
        messages = await list_messages(
            access_token, max_results=payload.max_results, query=query
        )
    except GmailAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}") from exc

    semaphore = asyncio.Semaphore(6)

    async def fetch_message(message_id: str) -> dict[str, Any]:
        async with semaphore:
            return await get_message_metadata(access_token, message_id)

    tasks = [fetch_message(item["id"]) for item in messages if item.get("id")]
    try:
        metadata_list = await asyncio.gather(*tasks, return_exceptions=False)
    except GmailAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API error: {exc}") from exc

    trials: list[dict[str, Any]] = []
    for message in metadata_list:
        headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        snippet = message.get("snippet", "")

        parsed = await parse_trial_email(subject=subject, sender=sender, snippet=snippet)
        combined_lower = f"{subject} {snippet}".lower()
        if parsed.confidence < 0.2 and "trial" not in combined_lower:
            continue

        end_date = parsed.trial_end_date
        trial_id = str(uuid.uuid4())
        trials.append(
            {
                "id": trial_id,
                "user_id": user_id,
                "service_name": parsed.service_name or subject or "Unknown Service",
                "start_date": parsed.trial_start_date,
                "end_date": end_date,
                "cancel_url": parsed.cancel_url,
                "status": status_from_end_date(end_date),
                "source": "email",
                "email_message_id": message.get("id"),
                "created_at": datetime.utcnow().isoformat(),
            }
        )

    stored = await upsert_trials(user_id, trials)
    response_trials = [
        {
            **trial,
            "days_remaining": days_remaining(trial.get("end_date")),
        }
        for trial in stored
    ]
    return JSONResponse(
        {
            "scanned": len(messages),
            "created": len(response_trials),
            "trials": response_trials,
        }
    )


@app.get("/trials")
async def get_trials(
    session: str | None = Cookie(default=None, alias=settings.session_cookie_name)
) -> JSONResponse:
    session_info = _require_session(session)
    user_trials = await list_trials(session_info["user_id"])
    response_trials = [
        {**trial, "days_remaining": days_remaining(trial.get("end_date"))}
        for trial in user_trials
    ]
    return JSONResponse({"trials": response_trials})


@app.post("/auth/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(settings.session_cookie_name)
    return response
