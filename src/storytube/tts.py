import asyncio
from pathlib import Path

import edge_tts


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
    try:
        return asyncio.run(_synthesize(text, voice, out_path, rate, pitch))
    except edge_tts.exceptions.NoAudioReceived as exc:
        raise RuntimeError(
            f"edge-tts produced no audio with voice '{voice}'. This almost always means the "
            f"voice does not match the narration language. Pick a voice whose locale matches "
            f"the language (hi-IN-* for Hindi, ur-PK-* for Urdu, ar-SA-* for Arabic, "
            f"en-US-* for English), or switch the TTS provider to Sarvam."
        ) from exc
