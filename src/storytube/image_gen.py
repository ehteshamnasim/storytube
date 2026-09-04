import time
from pathlib import Path
from urllib.parse import quote

import requests
from huggingface_hub import InferenceClient

from . import config

_client_cache: dict[tuple[str, str], InferenceClient] = {}


def _get_client() -> InferenceClient:
    if not config.HF_TOKEN:
        raise RuntimeError("HF_TOKEN is not set. Add it to your .env file.")
    cache_key = (config.HF_IMAGE_MODEL, config.HF_TOKEN)
    if cache_key not in _client_cache:
        _client_cache.clear()
        _client_cache[cache_key] = InferenceClient(model=config.HF_IMAGE_MODEL, token=config.HF_TOKEN)
    return _client_cache[cache_key]


def _generate_image_huggingface(
    prompt: str,
    out_path: Path,
    seed: int | None,
    width: int,
    height: int,
    num_inference_steps: int,
) -> None:
    image = _get_client().text_to_image(
        prompt,
        seed=seed,
        width=width,
        height=height,
        num_inference_steps=num_inference_steps,
    )
    image.save(out_path)


POLLINATIONS_ATTEMPTS = 3
POLLINATIONS_RETRY_CODES = {401, 408, 429, 500, 502, 503, 504}


def _pollinations_message(response: requests.Response) -> str:
    """Turn a Pollinations failure into something worth reading, not a 400-character URL."""
    detail = ""
    try:
        detail = (response.json().get("error") or {}).get("message", "")
    except ValueError:
        detail = ""

    if response.status_code == 401:
        return (
            "Pollinations rejected the API key. It usually means the key is wrong or the account "
            "has run out of Pollen credits. Check enter.pollinations.ai/keys, or switch Image "
            f"Provider to 'local' in Settings to generate on your own Mac instead. {detail}".strip()
        )
    if response.status_code in (402, 403):
        return (
            "Pollinations needs Pollen credits for this model. Top up at enter.pollinations.ai, "
            f"or switch Image Provider to 'local' in Settings. {detail}".strip()
        )
    if response.status_code == 429:
        return f"Pollinations is rate limiting this key. Wait a moment and try again. {detail}".strip()
    return f"Pollinations returned HTTP {response.status_code}. {detail}".strip()


def _generate_image_pollinations(
    prompt: str,
    out_path: Path,
    seed: int | None,
    width: int,
    height: int,
) -> None:
    if config.POLLINATIONS_API_KEY:
        url = f"https://gen.pollinations.ai/image/{quote(prompt, safe='')}"
        params = {"width": width, "height": height, "nologo": "true", "model": "flux"}
        headers = {"Authorization": f"Bearer {config.POLLINATIONS_API_KEY}"}
    else:
        url = f"https://image.pollinations.ai/prompt/{quote(prompt, safe='')}"
        params = {"width": width, "height": height, "nologo": "true"}
        headers = {}
    if seed is not None:
        params["seed"] = seed

    message = ""
    for attempt in range(POLLINATIONS_ATTEMPTS):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=120)
        except requests.RequestException as exc:
            message = f"Could not reach Pollinations: {exc}"
            if attempt < POLLINATIONS_ATTEMPTS - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError(message) from exc

        if response.ok and response.headers.get("content-type", "").startswith("image/"):
            out_path.write_bytes(response.content)
            return

        message = _pollinations_message(response)
        # Their 401s are often transient rather than a genuinely bad key.
        if response.status_code in POLLINATIONS_RETRY_CODES and attempt < POLLINATIONS_ATTEMPTS - 1:
            time.sleep(3 * (attempt + 1))
            continue
        break

    raise RuntimeError(message or "Pollinations did not return an image.")


QUALITY_SUFFIX = (
    "highly detailed, rich colour palette, expressive lighting, strong composition, "
    "clean focused subject, depth of field, professional illustration quality, 4k"
)


def _enrich(prompt: str) -> str:
    return f"{prompt.rstrip().rstrip('.')}. {QUALITY_SUFFIX}"


def generate_image(
    prompt: str,
    out_path: Path,
    seed: int | None = None,
    width: int = 1280,
    height: int = 720,
    num_inference_steps: int = 8,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = _enrich(prompt)
    if config.IMAGE_PROVIDER == "local":
        from .image_gen_local import generate_image_local

        generate_image_local(prompt, out_path, seed or 0, width, height)
    elif config.IMAGE_PROVIDER == "pollinations":
        _generate_image_pollinations(prompt, out_path, seed, width, height)
    else:
        _generate_image_huggingface(prompt, out_path, seed, width, height, num_inference_steps)


