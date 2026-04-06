from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from .config import settings

DATA_USERS_PATH = Path(__file__).resolve().parent.parent / "data" / "users.json"
DATA_TRIALS_PATH = Path(__file__).resolve().parent.parent / "data" / "trials.json"


def _ensure_data_file(path: Path, default: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(default, encoding="utf-8")


def _load_users_local() -> dict[str, Any]:
    _ensure_data_file(DATA_USERS_PATH, "{}")
    return json.loads(DATA_USERS_PATH.read_text(encoding="utf-8"))


def _save_users_local(data: dict[str, Any]) -> None:
    DATA_USERS_PATH.write_text(
        json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
    )


def _load_trials_local() -> list[dict[str, Any]]:
    _ensure_data_file(DATA_TRIALS_PATH, "[]")
    return json.loads(DATA_TRIALS_PATH.read_text(encoding="utf-8"))


def _save_trials_local(data: list[dict[str, Any]]) -> None:
    DATA_TRIALS_PATH.write_text(
        json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
    )


async def upsert_user(user: dict[str, Any]) -> dict[str, Any]:
    if settings.supabase_url and settings.supabase_service_role_key:
        return await _upsert_user_supabase(user)
    return _upsert_user_local(user)


async def get_user(user_id: str) -> dict[str, Any] | None:
    if settings.supabase_url and settings.supabase_service_role_key:
        return await _get_user_supabase(user_id)
    return _get_user_local(user_id)


def _upsert_user_local(user: dict[str, Any]) -> dict[str, Any]:
    data = _load_users_local()
    data[user["id"]] = user
    _save_users_local(data)
    return user


def _get_user_local(user_id: str) -> dict[str, Any] | None:
    data = _load_users_local()
    return data.get(user_id)


async def list_trials(user_id: str) -> list[dict[str, Any]]:
    if settings.supabase_url and settings.supabase_service_role_key:
        return await _list_trials_supabase(user_id)
    return _list_trials_local(user_id)


async def upsert_trials(
    user_id: str, trials: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if settings.supabase_url and settings.supabase_service_role_key:
        return await _upsert_trials_supabase(user_id, trials)
    return _upsert_trials_local(user_id, trials)


def _list_trials_local(user_id: str) -> list[dict[str, Any]]:
    data = _load_trials_local()
    return [trial for trial in data if trial.get("user_id") == user_id]


def _upsert_trials_local(
    user_id: str, trials: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    data = _load_trials_local()
    index: dict[tuple[str, str], int] = {}
    for idx, trial in enumerate(data):
        key = (trial.get("user_id", ""), trial.get("email_message_id", ""))
        if key[1]:
            index[key] = idx

    for trial in trials:
        key = (user_id, trial.get("email_message_id", ""))
        if key[1] and key in index:
            data[index[key]] = trial
        else:
            data.append(trial)
    _save_trials_local(data)
    return trials


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


async def _list_trials_supabase(user_id: str) -> list[dict[str, Any]]:
    url = (
        settings.supabase_url.rstrip("/")
        + "/rest/v1/trials?user_id=eq."
        + user_id
        + "&select=*"
    )
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def _upsert_trials_supabase(
    user_id: str, trials: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not trials:
        return []

    message_ids = [
        trial.get("email_message_id")
        for trial in trials
        if trial.get("email_message_id")
    ]
    existing_ids: set[str] = set()
    if message_ids:
        existing_ids = await _find_existing_trial_message_ids(user_id, message_ids)

    filtered = [
        trial
        for trial in trials
        if not trial.get("email_message_id")
        or trial.get("email_message_id") not in existing_ids
    ]
    if not filtered:
        return []

    url = settings.supabase_url.rstrip("/") + "/rest/v1/trials"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, headers=headers, json=filtered)
        response.raise_for_status()
        return response.json()


async def _find_existing_trial_message_ids(
    user_id: str, message_ids: list[str]
) -> set[str]:
    ids_param = ",".join(message_ids)
    url = (
        settings.supabase_url.rstrip("/")
        + "/rest/v1/trials?select=email_message_id&user_id=eq."
        + user_id
        + "&email_message_id=in.("
        + ids_param
        + ")"
    )
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    return {item.get("email_message_id") for item in payload if item.get("email_message_id")}
