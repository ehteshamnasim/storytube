"""YouTube: OAuth connect (loopback flow), upload a Short, and read back its analytics.

Uploading and reading private analytics both require OAuth 2.0 - a plain API key is
read-only and Google rejects it outright for videos.insert or the Analytics API.
"""

from __future__ import annotations

import http.server
import json
import threading
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Callable, Optional

import requests

from . import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
API_BASE = "https://www.googleapis.com/youtube/v3"
ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
TIMEOUT = 30
UPLOAD_TIMEOUT = 600
MAX_SHORT_SECONDS = 180
STATE_FILE = "youtube.json"
ANALYTICS_METRICS = ["views", "likes", "comments", "shares", "estimatedMinutesWatched", "averageViewDuration"]


class YouTubeError(RuntimeError):
    pass


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required name by BaseHTTPRequestHandler
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.server.oauth_result = {  # type: ignore[attr-defined]
            "code": params.get("code", [None])[0],
            "error": params.get("error_description", params.get("error", [None]))[0],
        }
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body style='font-family:-apple-system,sans-serif;padding:48px;color:#333'>"
            b"<h2>Connected</h2><p>You can close this tab and go back to Storytube.</p>"
            b"</body></html>"
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - silence default access log
        pass


class ConnectSession:
    """Tracks one in-progress OAuth connect attempt, keyed by session id."""

    def __init__(self, session_id: str, auth_url: str):
        self.id = session_id
        self.auth_url = auth_url
        self.status = "waiting"
        self.error: Optional[str] = None
        self.channel: Optional[dict] = None


_sessions: dict[str, ConnectSession] = {}


def _build_auth_url(client_id: str, redirect_uri: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def _exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=TIMEOUT,
    )
    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        raise YouTubeError(payload.get("error_description") or payload.get("error") or f"HTTP {response.status_code}")
    return payload


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    if not (client_id and client_secret and refresh_token):
        raise YouTubeError("YouTube is not connected. Connect it in Settings first.")
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=TIMEOUT,
    )
    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        message = payload.get("error_description") or payload.get("error") or f"HTTP {response.status_code}"
        if payload.get("error") == "invalid_grant":
            message = "YouTube access was revoked or expired. Reconnect it in Settings."
        raise YouTubeError(message)
    return payload["access_token"]


def start_connect(client_id: str, client_secret: str) -> ConnectSession:
    """Open a local loopback listener and hand back the URL the user opens in a browser."""
    if not client_id.strip() or not client_secret.strip():
        raise YouTubeError("Add your YouTube Client ID and Client Secret first.")

    httpd = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    httpd.oauth_result = None  # type: ignore[attr-defined]
    httpd.timeout = 300
    port = httpd.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/"
    auth_url = _build_auth_url(client_id.strip(), redirect_uri)

    session = ConnectSession(uuid.uuid4().hex[:12], auth_url)
    _sessions[session.id] = session

    def worker() -> None:
        try:
            httpd.handle_request()
            result = getattr(httpd, "oauth_result", None)
            if not result or result.get("error"):
                session.status = "error"
                session.error = (result or {}).get("error") or "No response from Google. Try connecting again."
                return
            code = result.get("code")
            if not code:
                session.status = "error"
                session.error = "Google did not return an authorization code."
                return
            tokens = _exchange_code(client_id.strip(), client_secret.strip(), code, redirect_uri)
            refresh_token = tokens.get("refresh_token")
            if not refresh_token:
                session.status = "error"
                session.error = (
                    "Google did not return a refresh token. Remove Storytube from "
                    "myaccount.google.com/permissions and try connecting again."
                )
                return
            channel = get_channel(tokens["access_token"])
            session.channel = {**channel, "refresh_token": refresh_token}
            session.status = "connected"
        except YouTubeError as exc:
            session.status = "error"
            session.error = str(exc)
        except Exception as exc:  # noqa: BLE001
            session.status = "error"
            session.error = f"Could not finish connecting: {exc}"
        finally:
            httpd.server_close()

    threading.Thread(target=worker, daemon=True).start()
    return session


def get_connect_session(session_id: str) -> Optional[ConnectSession]:
    return _sessions.get(session_id)


def get_channel(access_token: str) -> dict:
    response = requests.get(
        f"{API_BASE}/channels",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"part": "snippet,statistics", "mine": "true"},
        timeout=TIMEOUT,
    )
    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        message = payload.get("error", {}).get("message", f"HTTP {response.status_code}")
        raise YouTubeError(message)
    items = payload.get("items") or []
    if not items:
        raise YouTubeError("That Google account has no YouTube channel.")
    channel = items[0]
    return {
        "channel_id": channel["id"],
        "title": channel["snippet"]["title"],
        "subscriber_count": channel.get("statistics", {}).get("subscriberCount"),
    }


def upload_short(
    video_path: Path,
    title: str,
    description: str,
    access_token: str,
    privacy: str = "public",
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> dict:
    def report(stage: str, message: str) -> None:
        if on_progress:
            on_progress(stage, message)

    if not video_path.is_file():
        raise YouTubeError("That video no longer exists on disk.")

    title = (title or video_path.stem)[:100]
    description = description or ""
    if "#shorts" not in description.lower():
        description = f"{description}\n\n#Shorts".strip()

    size = video_path.stat().st_size
    report("container", "Starting the upload with YouTube…")
    init = requests.post(
        UPLOAD_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(size),
        },
        params={"uploadType": "resumable", "part": "snippet,status"},
        json={
            "snippet": {"title": title, "description": description[:5000], "categoryId": "24"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
        },
        timeout=TIMEOUT,
    )
    if init.status_code >= 400:
        payload = init.json() if init.content else {}
        raise YouTubeError(payload.get("error", {}).get("message", f"HTTP {init.status_code}"))
    upload_url = init.headers.get("Location")
    if not upload_url:
        raise YouTubeError("YouTube did not return an upload URL.")

    report("uploading", f"Uploading {size / 1024 / 1024:.1f} MB…")
    try:
        upload = requests.put(
            upload_url,
            headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
            data=video_path.read_bytes(),
            timeout=UPLOAD_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise YouTubeError(f"Upload failed: {exc}") from exc

    result = upload.json() if upload.content else {}
    if upload.status_code >= 400:
        raise YouTubeError(result.get("error", {}).get("message", f"HTTP {upload.status_code}"))

    video_id = result.get("id")
    if not video_id:
        raise YouTubeError("YouTube accepted the upload but returned no video ID.")

    report("done", "Posted to YouTube")
    return {
        "video_id": video_id,
        "url": f"https://youtube.com/shorts/{video_id}",
        "title": title,
        "privacy": privacy,
    }


def get_stats(video_id: str, access_token: str) -> dict:
    response = requests.get(
        f"{API_BASE}/videos",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"part": "statistics", "id": video_id},
        timeout=TIMEOUT,
    )
    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        raise YouTubeError(payload.get("error", {}).get("message", f"HTTP {response.status_code}"))
    items = payload.get("items") or []
    if not items:
        raise YouTubeError("YouTube has no numbers for that video yet.")
    stats = items[0].get("statistics", {})
    return {k: int(v) for k, v in stats.items() if str(v).isdigit()}


def get_analytics(channel_id: str, video_id: str, access_token: str) -> dict:
    """Watch-time metrics. These need yt-analytics.readonly and only exist for your own videos."""
    response = requests.get(
        ANALYTICS_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "ids": f"channel=={channel_id}",
            "startDate": "2005-01-01",
            "endDate": time.strftime("%Y-%m-%d"),
            "metrics": ",".join(ANALYTICS_METRICS),
            "filters": f"video=={video_id}",
        },
        timeout=TIMEOUT,
    )
    payload = response.json() if response.content else {}
    if response.status_code >= 400:
        raise YouTubeError(payload.get("error", {}).get("message", f"HTTP {response.status_code}"))
    rows = payload.get("rows") or []
    if not rows:
        return {}
    headers = [h["name"] for h in payload.get("columnHeaders", [])]
    return dict(zip(headers, rows[0]))


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
