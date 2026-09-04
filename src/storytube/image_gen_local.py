from __future__ import annotations

import os
from pathlib import Path

from . import config

MODEL_NAME = "schnell"
MODEL_REPO = "black-forest-labs/FLUX.1-schnell"

# 8-bit halves weight traffic, and Apple Silicon is memory-bandwidth bound here.
# Set STORYTUBE_FLUX_QUANTIZE=0 to load full precision instead.
QUANTIZE = int(os.environ.get("STORYTUBE_FLUX_QUANTIZE", "8")) or None

# FLUX.1-schnell is timestep-distilled for 1-4 steps; more steps cost time without adding detail.
DEFAULT_STEPS = 4

_flux = None


def _load_flux(quantize: int | None = QUANTIZE):
    global _flux
    if _flux is not None:
        return _flux

    from huggingface_hub.errors import GatedRepoError
    from mflux.models.flux.variants.txt2img.flux import Flux1, ModelConfig

    # mflux downloads weights through huggingface_hub, which reads the token from the environment.
    if config.HF_TOKEN:
        os.environ.setdefault("HF_TOKEN", config.HF_TOKEN)

    try:
        _flux = Flux1(model_config=ModelConfig.schnell(), quantize=quantize)
    except GatedRepoError as exc:
        raise RuntimeError(
            f"{MODEL_REPO} is gated. Open https://huggingface.co/{MODEL_REPO} while logged in "
            "to the same Hugging Face account as your HF_TOKEN, accept the licence, then run "
            "this again. Approval is instant and only needed once."
        ) from exc
    return _flux


def generate_image_local(
    prompt: str,
    out_path: Path,
    seed: int = 0,
    width: int = 1280,
    height: int = 720,
    num_inference_steps: int = DEFAULT_STEPS,
) -> None:
    """Generate an image with FLUX.1-schnell running locally through MLX on Apple Silicon."""
    flux = _load_flux()

    # FLUX works in latent blocks of 16px, so round the requested size to fit.
    width = max(256, round(width / 16) * 16)
    height = max(256, round(height / 16) * 16)

    image = flux.generate_image(
        seed=seed,
        prompt=prompt,
        num_inference_steps=num_inference_steps,
        width=width,
        height=height,
        guidance=0.0,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path=out_path, overwrite=True)
