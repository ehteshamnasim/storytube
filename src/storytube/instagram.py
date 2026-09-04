"""Instagram Graph API: verify credentials, publish a reel, and read back its insights."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Optional

import requests

GRAPH_VERSION = "v23.0"
# Instagram Login issues tokens for graph.instagram.com, Facebook Login for graph.facebook.com.
GRAPH_HOSTS = ("https://graph.instagram.com", "https://graph.facebook.com")
RUPLOAD_HOST = "https://rupload.facebook.com/ig-api-upload"
PUBLISHABLE_TYPES = {"BUSINESS", "MEDIA_CREATOR", "CREATOR"}
TIMEOUT = 30
UPLOAD_TIMEOUT = 600
# Meta advise polling roughly once a minute for no more than five.
POLL_SECONDS = 5
POLL_ATTEMPTS = 60
STATE_FILE = "instagram.json"

INSIGHT_METRICS = ["views", "reach", "likes", "comments", "saved", "shares"]


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


def _post(host: str, path: str, token: str, data: dict) -> dict:
    response = requests.post(
        f"{host}/{GRAPH_VERSION}/{path}",
        data={**data, "access_token": token},
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


def _working_host(user_id: str, token: str) -> str:
    return test_connection(user_id, token)["host"]


def publish_reel(
    video_path: Path,
    caption: str,
    user_id: str,
    token: str,
    share_to_feed: bool = True,
    is_ai_generated: bool = True,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> dict:
    """Upload a local MP4 as a reel. Uses resumable upload so no public URL is needed."""

    def report(stage: str, message: str) -> None:
        if on_progress:
            on_progress(stage, message)

    if not video_path.is_file():
        raise InstagramError("That video no longer exists on disk.")

    user_id, token = user_id.strip(), token.strip()
    report("checking", "Checking your Instagram account…")
    account = test_connection(user_id, token)
    if not account["can_publish"]:
        raise InstagramError(
            f"@{account['username']} is a {account['account_type']} account. "
            "Only Business or Creator accounts can publish through the API."
        )
    host = account["host"]

    report("container", "Creating the post…")
    container = _post(
        host,
        f"{user_id}/media",
        token,
        {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption[:2200],
            "share_to_feed": "true" if share_to_feed else "false",
            "is_ai_generated": "true" if is_ai_generated else "false",
        },
    )
    container_id = container.get("id")
    if not container_id:
        raise InstagramError("Instagram did not return an upload container.")

    size = video_path.stat().st_size
    report("uploading", f"Uploading {size / 1024 / 1024:.1f} MB…")
    try:
        upload = requests.post(
            f"{RUPLOAD_HOST}/{GRAPH_VERSION}/{container_id}",
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(size),
            },
            data=video_path.read_bytes(),
            timeout=UPLOAD_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise InstagramError(f"Upload failed: {exc}") from exc

    result = upload.json() if upload.content else {}
    if upload.status_code >= 400 or not result.get("success", True):
        detail = result.get("debug_info", {}).get("message") or result.get("error", {}).get("message")
        raise InstagramError(f"Upload rejected: {detail or upload.status_code}")

    report("processing", "Instagram is processing the video…")
    for _ in range(POLL_ATTEMPTS):
        status = _get(host, container_id, token, {"fields": "status_code,status"})
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise InstagramError(f"Instagram could not process the video: {status.get('status', code)}")
        time.sleep(POLL_SECONDS)
    else:
        raise InstagramError("Instagram is still processing the video. Try publishing again shortly.")

    report("publishing", "Publishing…")
    published = _post(host, f"{user_id}/media_publish", token, {"creation_id": container_id})
    media_id = published.get("id")
    if not media_id:
        raise InstagramError("Instagram accepted the video but returned no post ID.")

    details = {}
    try:
        details = _get(host, media_id, token, {"fields": "permalink,timestamp,media_product_type"})
    except InstagramError:
        details = {}

    report("done", "Posted to Instagram")
    return {
        "media_id": media_id,
        "permalink": details.get("permalink", ""),
        "published_at": details.get("timestamp", ""),
        "username": account["username"],
    }


def get_insights(media_id: str, user_id: str, token: str) -> dict:
    """Engagement numbers for a published post. Metrics vary by media type, so failures are tolerated."""
    host = _working_host(user_id, token)
    stats: dict[str, int] = {}

    try:
        basic = _get(host, media_id, token, {"fields": "like_count,comments_count,permalink"})
        if "like_count" in basic:
            stats["likes"] = basic["like_count"]
        if "comments_count" in basic:
            stats["comments"] = basic["comments_count"]
        permalink = basic.get("permalink", "")
    except InstagramError:
        permalink = ""

    try:
        insights = _get(host, f"{media_id}/insights", token, {"metric": ",".join(INSIGHT_METRICS)})
        for entry in insights.get("data", []):
            values = entry.get("values") or [{}]
            stats[entry["name"]] = values[0].get("value", 0)
    except InstagramError:
        pass

    if not stats:
        raise InstagramError("Instagram returned no numbers for that post yet.")
    return {"stats": stats, "permalink": permalink}


def read_state(out_dir: Path) -> dict:
    path = out_dir / STATE_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(out_dir: Path, state: dict) -> None:
    (out_dir / STATE_FILE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

