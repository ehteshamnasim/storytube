import asyncio
import time
from pathlib import Path

import edge_tts

# edge-tts is a free public service and drops requests now and then, so an empty
# response usually means "try again" rather than "wrong voice".
ATTEMPTS = 3


async def _synthesize(
    text: str, voice: str, out_path: Path, rate: str = "+0%", pitch: str = "+0Hz"
) -> list[dict]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(
        text, voice, rate=rate, pitch=pitch, boundary="WordBoundary"
    )
    word_boundaries: list[dict] = []
    with open(out_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_boundaries.append(
                    {
                        "text": chunk["text"],
                        "start": chunk["offset"] / 1e7,
                        "duration": chunk["duration"] / 1e7,
                    }
                )
    return word_boundaries


def generate_voice_over(
    text: str, voice: str, out_path: Path, rate: str = "+0%", pitch: str = "+0Hz"
) -> list[dict]:
    last_error: Exception | None = None

    for attempt in range(ATTEMPTS):
        try:
            boundaries = asyncio.run(_synthesize(text, voice, out_path, rate, pitch))
            if out_path.exists() and out_path.stat().st_size > 0:
                return boundaries
            last_error = RuntimeError("edge-tts returned an empty recording")
        except Exception as exc:  # noqa: BLE001 - retried below, reported if it keeps failing
            last_error = exc

        # A zero-byte file would otherwise look like a valid cached voice-over later.
        out_path.unlink(missing_ok=True)
        if attempt < ATTEMPTS - 1:
            time.sleep(2 * (attempt + 1))

    raise RuntimeError(
        f"edge-tts returned no audio for voice '{voice}' after {ATTEMPTS} attempts. "
        f"It is a free service and sometimes drops requests, so waiting a minute often fixes it. "
        f"If it keeps failing, the voice may not match the text: use hi-IN-* for Hindi, "
        f"ur-PK-* for Urdu, ar-SA-* for Arabic, en-US-* or en-IN-* for English."
    ) from last_error
