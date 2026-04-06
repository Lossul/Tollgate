from __future__ import annotations

from typing import Any

import httpx

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailAPIError(RuntimeError):
    pass


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def list_messages(
    access_token: str,
    *,
    max_results: int = 50,
    query: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"maxResults": max_results}
    if query:
        params["q"] = query

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{GMAIL_API_BASE}/messages",
            headers=_auth_headers(access_token),
            params=params,
        )
        if response.is_error:
            raise GmailAPIError(f"{response.status_code}: {response.text}")
        payload = response.json()
    return payload.get("messages", [])


async def get_message_metadata(access_token: str, message_id: str) -> dict[str, Any]:
    params = {
        "format": "metadata",
        "metadataHeaders": ["Subject", "From", "Date"],
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{GMAIL_API_BASE}/messages/{message_id}",
            headers=_auth_headers(access_token),
            params=params,
        )
        if response.is_error:
            raise GmailAPIError(f"{response.status_code}: {response.text}")
        return response.json()
