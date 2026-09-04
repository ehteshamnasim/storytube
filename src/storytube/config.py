import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_STRING_DEFAULTS = {
    "GEMINI_MODEL": "gemini-3.1-flash-lite",
    "HF_IMAGE_MODEL": "black-forest-labs/FLUX.1-schnell",
    "IMAGE_PROVIDER": "huggingface",
}
_SECRET_KEYS = {"GEMINI_API_KEY", "HF_TOKEN", "POLLINATIONS_API_KEY", "SARVAM_API_KEY"}
_PATH_DEFAULTS = {"OUTPUT_DIR": "output", "PROMPTS_DIR": "prompts", "STORIES_DIR": "stories"}

_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin")
FFMPEG_BIN = os.environ.get(
    "FFMPEG_BIN",
    str(_FFMPEG_FULL / "ffmpeg") if (_FFMPEG_FULL / "ffmpeg").exists() else "ffmpeg",
)
FFPROBE_BIN = os.environ.get(
    "FFPROBE_BIN",
    str(_FFMPEG_FULL / "ffprobe") if (_FFMPEG_FULL / "ffprobe").exists() else "ffprobe",
)


def __getattr__(name: str):
    """Read config values fresh from the environment on every access.

    This lets the web UI update .env / os.environ at runtime and have the
    change take effect immediately, without restarting the process.
    """
    if name in _PATH_DEFAULTS:
        return Path(os.environ.get(name, _PATH_DEFAULTS[name]))
    if name in _STRING_DEFAULTS:
        return os.environ.get(name, _STRING_DEFAULTS[name])
    if name in _SECRET_KEYS:
        return os.environ.get(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

