from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from .config import settings

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "users.json"


def _ensure_data_file() -> None:
    if not DATA_PATH.exists():
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATA_PATH.write_text("{}", encoding="utf-8")


def _load_local() -> dict[str, Any]:
    _ensure_data_file()
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _save_local(data: dict[str, Any]) -> None:
    DATA_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


async def upsert_user(user: dict[str, Any]) -> dict[str, Any]:
    if settings.supabase_url and settings.supabase_service_role_key:
        return await _upsert_user_supabase(user)
    return _upsert_user_local(user)


async def get_user(user_id: str) -> dict[str, Any] | None:
    if settings.supabase_url and settings.supabase_service_role_key:
        return await _get_user_supabase(user_id)
    return _get_user_local(user_id)


def _upsert_user_local(user: dict[str, Any]) -> dict[str, Any]:
    data = _load_local()
    data[user["id"]] = user
    _save_local(data)
    return user


def _get_user_local(user_id: str) -> dict[str, Any] | None:
    data = _load_local()
    return data.get(user_id)


async def _upsert_user_supabase(user: dict[str, Any]) -> dict[str, Any]:
    url = settings.supabase_url.rstrip("/") + "/rest/v1/users?on_conflict=id"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, headers=headers, json=[user])
        response.raise_for_status()
        payload = response.json()
        if payload:
            return payload[0]
    return user


async def _get_user_supabase(user_id: str) -> dict[str, Any] | None:
    url = (
        settings.supabase_url.rstrip("/")
        + "/rest/v1/users?id=eq."
        + user_id
        + "&select=*"
    )
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if payload:
            return payload[0]
    return None
