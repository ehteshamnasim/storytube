import time
from pathlib import Path

import requests

from . import config

API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
VOICES_URL = "https://api.elevenlabs.io/v1/voices"

# Multilingual v2 covers 29 languages and Urdu is not among them; only v3 reaches it.
MODEL_MULTILINGUAL = "eleven_multilingual_v2"
MODEL_V3 = "eleven_v3"
V2_LANGUAGES = {
    "english", "hindi", "arabic", "tamil", "german", "french", "spanish", "italian",
    "portuguese", "polish", "dutch", "turkish", "russian", "ukrainian", "czech",
    "greek", "finnish", "croatian", "malay", "slovak", "danish", "swedish",
    "bulgarian", "romanian", "indonesian", "filipino", "japanese", "korean", "chinese",
}

ATTEMPTS = 3
RETRY_CODES = {408, 429, 500, 502, 503, 504}


def model_for_language(language: str) -> str:
    return MODEL_MULTILINGUAL if language.strip().lower() in V2_LANGUAGES else MODEL_V3


def _message(response: requests.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    if isinstance(detail, dict):
        status = detail.get("status", "")
        text = detail.get("message", "")
        if status == "quota_exceeded":
            return "Your ElevenLabs credits are used up for this billing period."
        if status in {"invalid_api_key", "missing_permissions"}:
            return "That ElevenLabs API key was rejected. Check it in Settings."
        if text:
            return text
    if response.status_code == 401:
        return "That ElevenLabs API key was rejected. Check it in Settings."
    return f"ElevenLabs returned {response.status_code}."


def list_voices() -> list[dict]:
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set. Add it in Settings.")
    response = requests.get(
        VOICES_URL, headers={"xi-api-key": config.ELEVENLABS_API_KEY}, timeout=30
    )
    if not response.ok:
        raise RuntimeError(_message(response))
    return [
        {
            "voice_id": voice["voice_id"],
            "name": voice.get("name", voice["voice_id"]),
            "labels": voice.get("labels", {}),
        }
        for voice in response.json().get("voices", [])
    ]


def generate_voice_over_elevenlabs(
    text: str,
    voice_id: str,
    out_path: Path,
    language: str = "English",
    stability: float = 0.45,
    similarity_boost: float = 0.75,
    style: float = 0.35,
    speed: float = 1.0,
) -> None:
    """Read `text` with an ElevenLabs voice. Lower stability leaves more room for expression."""
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set. Add it in Settings.")

    payload = {
        "text": text,
        "model_id": model_for_language(language),
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "speed": speed,
        },
    }

    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            response = requests.post(
                f"{API_URL}/{voice_id}",
                headers={
                    "xi-api-key": config.ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json=payload,
                timeout=120,
            )
            if response.ok and response.content:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(response.content)
                return
            last_error = RuntimeError(_message(response))
            if response.status_code not in RETRY_CODES:
                raise last_error
        except requests.RequestException as exc:
            last_error = exc
        if attempt < ATTEMPTS - 1:
            time.sleep(2 * (attempt + 1))

    raise RuntimeError(str(last_error))
