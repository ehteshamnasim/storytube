"""Standalone IndicF5 worker.

Runs inside .venv-indicf5 because IndicF5 needs transformers<4.50 and numpy<=1.26.4,
which conflict with mflux in the main environment. Reads one JSON job per line on
stdin and writes one JSON result per line on stdout, keeping the model warm.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The model libraries print progress to stdout, so reserve the real stdout for the
# JSON protocol and send every other print to stderr.
_protocol_out = sys.stdout
sys.stdout = sys.stderr

MODEL_REPO = "ai4bharat/IndicF5"
SAMPLE_RATE = 24000

_model = None


def _patch_audio_loading() -> None:
    """torchaudio 2.11 decodes via TorchCodec, which needs FFmpeg 4-7; this Mac has 8."""
    import soundfile as sf
    import torch
    import torchaudio

    def load(path, *args, **kwargs):
        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
        return torch.from_numpy(data.T).contiguous(), sample_rate

    torchaudio.load = load


def _load_model(token: str | None):
    global _model
    if _model is None:
        from transformers import AutoModel

        _patch_audio_loading()
        _model = AutoModel.from_pretrained(MODEL_REPO, trust_remote_code=True, token=token or None)
    return _model


def _synthesize(job: dict) -> None:
    import numpy as np
    import soundfile as sf

    model = _load_model(job.get("token"))
    audio = model(job["text"], ref_audio_path=job["ref_audio"], ref_text=job["ref_text"])

    audio = np.asarray(audio, dtype=np.float32)
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio / peak * 0.95

    out_path = Path(job["out_wav"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, audio, samplerate=SAMPLE_RATE)


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            _synthesize(json.loads(line))
            result = {"ok": True}
        except Exception as exc:  # reported back to the parent process
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        _protocol_out.write(json.dumps(result) + "\n")
        _protocol_out.flush()


if __name__ == "__main__":
    main()
