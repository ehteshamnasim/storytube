from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import config

ENV_PATH = Path(".env")

CONFIG_SCHEMA: list[dict[str, Any]] = [
    {
        "key": "GEMINI_API_KEY",
        "label": "Gemini API Key",
        "group": "Story & Scene Planning",
        "type": "password",
        "secret": True,
        "help": "Used to turn your story into scenes (narration + image prompts).",
        "guidance": "Get a free key at aistudio.google.com/apikey (sign in with Google, click 'Create API key').",
        "guidance_url": "https://aistudio.google.com/apikey",
    },
    {
        "key": "GEMINI_MODEL",
        "label": "Gemini Model",
        "group": "Story & Scene Planning",
        "type": "combo",
        "options": [
            {"value": "gemini-3.1-flash-lite", "label": "gemini-3.1-flash-lite — fast and cheap (recommended)"},
            {"value": "gemini-3.1-flash", "label": "gemini-3.1-flash — balanced"},
            {"value": "gemini-3.1-pro", "label": "gemini-3.1-pro — highest quality, slower"},
            {"value": "gemini-flash-latest", "label": "gemini-flash-latest — rolling alias"},
        ],
        "secret": False,
        "default": "gemini-3.1-flash-lite",
        "help": "Model used for scene planning. Pick another one if Google deprecates the current one.",
        "guidance": "Full list at ai.google.dev/gemini-api/docs/models.",
        "guidance_url": "https://ai.google.dev/gemini-api/docs/models",
    },
    {
        "key": "IMAGE_PROVIDER",
        "label": "Image Provider",
        "group": "Images",
        "type": "select",
        "options": ["local", "huggingface", "pollinations"],
        "secret": False,
        "default": "local",
        "help": "Which service generates the scene images.",
        "guidance": (
            "local = FLUX.1-schnell running on your own Mac: free forever, unlimited, no API key "
            "(first run downloads ~24 GB). huggingface = Inference Providers (needs credits). "
            "pollinations = Pollinations.ai (needs Pollen credits for good quality)."
        ),
        "guidance_url": "",
    },
    {
        "key": "HF_TOKEN",
        "label": "Hugging Face Token",
        "group": "Images",
        "type": "password",
        "secret": True,
        "applies_when": {"IMAGE_PROVIDER": ["huggingface", "local"]},
        "help": "Needed to download the local FLUX model, and for the 'huggingface' provider.",
        "guidance": "Create a fine-grained token at huggingface.co/settings/tokens with 'Make calls to Inference Providers' enabled.",
        "guidance_url": "https://huggingface.co/settings/tokens",
    },
    {
        "key": "HF_IMAGE_MODEL",
        "label": "Hugging Face Image Model",
        "group": "Images",
        "type": "combo",
        "options": [
            {"value": "black-forest-labs/FLUX.1-schnell", "label": "FLUX.1-schnell — fast, few steps (recommended)"},
            {"value": "black-forest-labs/FLUX.1-dev", "label": "FLUX.1-dev — higher quality, slower"},
            {"value": "stabilityai/stable-diffusion-3.5-large", "label": "Stable Diffusion 3.5 Large"},
            {"value": "stabilityai/stable-diffusion-xl-base-1.0", "label": "SDXL Base 1.0"},
        ],
        "secret": False,
        "default": "black-forest-labs/FLUX.1-schnell",
        "applies_when": {"IMAGE_PROVIDER": ["huggingface"]},
        "help": "Model used when Image Provider is 'huggingface'.",
        "guidance": "Browse more at huggingface.co/models?pipeline_tag=text-to-image.",
        "guidance_url": "https://huggingface.co/models?pipeline_tag=text-to-image",
    },
    {
        "key": "POLLINATIONS_API_KEY",
        "label": "Pollinations API Key",
        "group": "Images",
        "type": "password",
        "secret": True,
        "applies_when": {"IMAGE_PROVIDER": ["pollinations"]},
        "help": "Needed only if Image Provider is 'pollinations'. Without it, a slower free anonymous tier is used.",
        "guidance": "Sign up and create a secret key (sk_...) at enter.pollinations.ai/keys. Needs Pollen credits (quests or a small top-up) to actually generate images.",
        "guidance_url": "https://enter.pollinations.ai/keys",
    },
    {
        "key": "SARVAM_API_KEY",
        "label": "Sarvam API Key",
        "group": "Voice-over",
        "type": "password",
        "secret": True,
        "help": "Needed only if TTS Provider is 'sarvam'. Gives authentic Indian-accented Hindi/Urdu voices.",
        "guidance": "Sign up free at indus.sarvam.ai, get your API key from the dashboard.",
        "guidance_url": "https://indus.sarvam.ai",
    },
    {
        "key": "ELEVENLABS_API_KEY",
        "label": "ElevenLabs API Key",
        "group": "Voice-over",
        "type": "password",
        "secret": True,
        "help": "The most expressive reader, and the only one that handles Urdu well. Paid, from $6/month.",
        "guidance": "Create a key under Profile > API Keys. The free tier has no commercial licence, so pick Starter or above before posting reels publicly.",
        "guidance_url": "https://elevenlabs.io/app/settings/api-keys",
    },
    {
        "key": "IG_USER_ID",
        "label": "Instagram Account ID",
        "group": "Instagram",
        "type": "text",
        "secret": False,
        "help": "A long number like 17841400000000000. Not your @handle.",
        "guidance": "In Graph API Explorer, run me/accounts?fields=instagram_business_account and copy the id it returns.",
        "guidance_url": "https://developers.facebook.com/tools/explorer/",
    },
    {
        "key": "IG_ACCESS_TOKEN",
        "label": "Instagram Access Token",
        "group": "Instagram",
        "type": "password",
        "secret": True,
        "help": "A long string starting with EAA. Expires after 60 days, then you generate a new one.",
        "guidance": "Generate it in Graph API Explorer with instagram_basic, instagram_content_publish, pages_show_list and pages_read_engagement ticked.",
        "guidance_url": "https://developers.facebook.com/tools/explorer/",
    },
    {
        "key": "OUTPUT_DIR",
        "label": "Output Directory",
        "group": "Advanced",
        "type": "text",
        "secret": False,
        "default": "output",
        "help": "Where generated videos/images/audio are saved.",
        "guidance": "",
        "guidance_url": "",
    },
]


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def get_raw_env() -> dict[str, str]:
    return _parse_env_file(ENV_PATH)


def get_masked_config() -> list[dict[str, Any]]:
    current = get_raw_env()
    result = []
    for field in CONFIG_SCHEMA:
        key = field["key"]
        raw_value = current.get(key, "")
        is_set = bool(raw_value)
        if field["secret"]:
            display_value = f"{'•' * 8}{raw_value[-4:]}" if is_set else ""
        else:
            display_value = raw_value or field.get("default", "")
        result.append({**field, "value": display_value, "is_set": is_set})
    return result


def update_env(updates: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    known_keys = {f["key"] for f in CONFIG_SCHEMA}
    seen: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key, _, _ = stripped.partition("=")
        key = key.strip()
        if key in updates and key in known_keys:
            new_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen and key in known_keys:
            new_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    import os

    for key, value in updates.items():
        if key in known_keys:
            os.environ[key] = value


def get_prompts_dir() -> Path:
    return config.PROMPTS_DIR

