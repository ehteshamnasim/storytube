from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import config
from .config import FFMPEG_BIN

SAMPLE_RATE = 24000
VOICES_DIR = Path("assets/voices")
MODEL_REPO = "ai4bharat/IndicF5"
WORKER_SCRIPT = Path("scripts/indicf5_worker.py")

_worker: subprocess.Popen | None = None


@dataclass(frozen=True)
class ReferenceVoice:
    key: str
    label: str
    file: str
    ref_text: str


REFERENCE_VOICES: dict[str, ReferenceVoice] = {
    "mar_m": ReferenceVoice(
        key="mar_m",
        label="Male — calm storyteller (Marathi reference)",
        file="MAR_M_WIKI_00001.wav",
        ref_text=(
            "या प्रथाला एकोणीसशे पंचातर ईसवी पासून भारतीय दंड संहिताची धारा "
            "चारशे अठ्ठावीस आणि चारशे एकोणतीसच्या अन्तर्गत निषेध केला."
        ),
    ),
    "mar_f": ReferenceVoice(
        key="mar_f",
        label="Female — neutral narrator (Marathi reference)",
        file="MAR_F_WIKI_00001.wav",
        ref_text="दिगंतराव्दारे अंतराळ कक्षेतला कचरा चिन्हित करण्यासाठी प्रयत्न केले जात आहे.",
    ),
    "mar_f_warm": ReferenceVoice(
        key="mar_f_warm",
        label="Female — warm and expressive (Marathi reference)",
        file="MAR_F_HAPPY_00001.wav",
        ref_text="आतिथ्य व्यावसायिकांना अतिथींच्या गरजा लक्षात घेऊन त्यांची सेवा करावी लागते.",
    ),
    "pan_f": ReferenceVoice(
        key="pan_f",
        label="Female — bright and happy (Punjabi reference)",
        file="PAN_F_HAPPY_00002.wav",
        ref_text=(
            "ਇੱਕ ਗ੍ਰਾਹਕ ਨੇ ਸਾਡੀ ਬੇਮਿਸਾਲ ਸੇਵਾ ਬਾਰੇ ਦਿਲੋਂਗਵਾਹੀ ਦਿੱਤੀ "
            "ਜਿਸ ਨਾਲ ਸਾਨੂੰ ਅਨੰਦ ਮਹਿਸੂਸ ਹੋਇਆ।"
        ),
    ),
}


def list_voices() -> list[dict[str, str]]:
    return [{"key": v.key, "label": v.label} for v in REFERENCE_VOICES.values()]


def _resolve_voice(speaker: str) -> tuple[Path, str]:
    """Return reference audio path and transcript, supporting built-in keys and custom clips."""
    voice = REFERENCE_VOICES.get(speaker)
    if voice:
        path = VOICES_DIR / voice.file
        if not path.exists():
            raise RuntimeError(
                f"Reference voice '{speaker}' is missing at {path}. "
                "Re-download the IndicF5 prompt files into assets/voices/."
            )
        return path, voice.ref_text

    custom = Path(speaker)
    if custom.exists():
        transcript = custom.with_suffix(".txt")
        if not transcript.exists():
            raise RuntimeError(
                f"Custom reference voice {custom} needs a matching transcript at {transcript} "
                "containing exactly what is spoken in the clip."
            )
        return custom, transcript.read_text(encoding="utf-8").strip()

    raise RuntimeError(
        f"Unknown IndicF5 voice '{speaker}'. Use one of {sorted(REFERENCE_VOICES)} "
        "or a path to your own reference .wav with a matching .txt transcript."
    )


def _patch_audio_loading() -> None:
    """Kept for direct in-process use; the worker applies the same patch itself."""
    import soundfile as sf
    import torch
    import torchaudio

    if getattr(torchaudio, "_storytube_soundfile_patch", False):
        return

    def load(path, *args, **kwargs):
        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
        return torch.from_numpy(data.T).contiguous(), sample_rate

    torchaudio.load = load
    torchaudio._storytube_soundfile_patch = True


def _worker_python() -> Path:
    # absolute(), not resolve(): resolving follows the symlink out of the venv to the
    # system interpreter, which would lose the venv's packages.
    python = Path(".venv-indicf5/bin/python").absolute()
    if not python.exists():
        raise RuntimeError(
            "IndicF5 runs in its own environment because it needs transformers<4.50 and "
            "numpy<=1.26.4, which conflict with the image model. Create it with:\n"
            "  python3.14 -m venv .venv-indicf5\n"
            "  .venv-indicf5/bin/pip install 'git+https://github.com/ai4bharat/IndicF5.git' "
            "'transformers<4.50' 'numpy<=1.26.4' soundfile"
        )
    return python


def _get_worker() -> subprocess.Popen:
    global _worker
    if _worker is not None and _worker.poll() is None:
        return _worker

    _worker = subprocess.Popen(
        [str(_worker_python()), str(WORKER_SCRIPT.resolve())],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    return _worker


def generate_voice_over_indicf5(
    text: str,
    speaker: str,
    out_path: Path,
) -> None:
    ref_path, ref_text = _resolve_voice(speaker)
    worker = _get_worker()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)

    job = {
        "text": text,
        "ref_audio": str(ref_path.resolve()),
        "ref_text": ref_text,
        "out_wav": str(wav_path),
        "token": config.HF_TOKEN or "",
    }

    try:
        worker.stdin.write(json.dumps(job) + "\n")
        worker.stdin.flush()
        response = worker.stdout.readline()
        if not response:
            raise RuntimeError("IndicF5 worker exited unexpectedly.")
        result = json.loads(response)
        if not result.get("ok"):
            raise RuntimeError(f"IndicF5 failed: {result.get('error')}")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [FFMPEG_BIN, "-y", "-v", "error", "-i", str(wav_path),
             "-c:a", "libmp3lame", "-q:a", "2", str(out_path)],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
        )
    finally:
        wav_path.unlink(missing_ok=True)
