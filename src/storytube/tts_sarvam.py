import base64
from pathlib import Path

import requests

from . import config

API_URL = "https://api.sarvam.ai/text-to-speech"


def estimate_word_boundaries(text: str, total_duration: float) -> list[dict]:
    words = text.split()
    if not words:
        return []
    weights = [max(len(w), 1) for w in words]
    total_weight = sum(weights)
    boundaries = []
    cursor = 0.0
    for word, weight in zip(words, weights):
        word_duration = total_duration * (weight / total_weight)
        boundaries.append({"text": word, "start": cursor, "duration": word_duration})
        cursor += word_duration
    return boundaries


def generate_voice_over_sarvam(
    text: str,
    speaker: str,
    out_path: Path,
    language_code: str = "hi-IN",
    model: str = "bulbul:v3",
    pace: float = 1.0,
    temperature: float = 0.6,
) -> None:
    if not config.SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set. Add it to your .env file.")

    temperature = min(temperature, 1.0)

    response = requests.post(
        API_URL,
        headers={
            "api-subscription-key": config.SARVAM_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "language_code": language_code,
            "speaker": speaker,
            "model": model,
            "pace": pace,
            "temperature": temperature,
            "output_audio_codec": "mp3",
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    audio_bytes = base64.b64decode(data["audios"][0])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(audio_bytes)
