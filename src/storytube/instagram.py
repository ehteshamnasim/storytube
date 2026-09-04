"""Instagram Graph API helpers. Publishing is not wired up yet; this verifies credentials."""

from __future__ import annotations

import requests

GRAPH_VERSION = "v23.0"
# Instagram Login issues tokens for graph.instagram.com, Facebook Login for graph.facebook.com.
GRAPH_HOSTS = ("https://graph.instagram.com", "https://graph.facebook.com")
PUBLISHABLE_TYPES = {"BUSINESS", "MEDIA_CREATOR", "CREATOR"}
TIMEOUT = 15


class InstagramError(RuntimeError):
    pass


def _get(host: str, path: str, token: str, params: dict) -> dict:
    response = requests.get(
        f"{host}/{GRAPH_VERSION}/{path}",
        params={**params, "access_token": token},
        timeout=TIMEOUT,
    )
    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        message = payload.get("error", {}).get("message", f"HTTP {response.status_code}")
        raise InstagramError(message)
    return payload


def test_connection(user_id: str, token: str) -> dict:
    """Resolve the account behind the credentials and report whether it can publish."""
    if not user_id.strip():
        raise InstagramError("Add your Instagram Account ID first.")
    if not token.strip():
        raise InstagramError("Add your Instagram Access Token first.")

    last_error = None
    for host in GRAPH_HOSTS:
        try:
            account = _get(host, user_id.strip(), token.strip(), {"fields": "username,account_type"})
        except InstagramError as exc:
            last_error = exc
            continue
        except requests.RequestException as exc:
            raise InstagramError(f"Could not reach Instagram: {exc}") from exc

        quota = {}
        try:
            usage = _get(
                host,
                f"{user_id.strip()}/content_publishing_limit",
                token.strip(),
                {"fields": "config,quota_usage"},
            )
            quota = (usage.get("data") or [{}])[0]
        except (InstagramError, requests.RequestException):
            quota = {}

        account_type = account.get("account_type", "")
        return {
            "username": account.get("username", ""),
            "account_type": account_type,
            "can_publish": account_type.upper() in PUBLISHABLE_TYPES or not account_type,
            "quota_used": quota.get("quota_usage"),
            "quota_total": (quota.get("config") or {}).get("quota_total"),
            "host": host,
        }

    raise InstagramError(str(last_error) if last_error else "Could not verify those credentials.")
