from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import config
from ..assemble import get_audio_duration
from ..pipeline import PipelineOptions
from ..story_reader import read_story
from ..tts import generate_voice_over
from ..tts_indicf5 import generate_voice_over_indicf5
from ..tts_sarvam import generate_voice_over_sarvam
from . import config_store, jobs, prompt_store
from .schemas import (
    ConfigUpdateRequest,
    GenerateRequest,
    PromptSaveRequest,
    RemixRequest,
    StorySaveRequest,
    VoicePreviewRequest,
)

app = FastAPI(title="Storytube")

STATIC_DIR = Path(__file__).parent / "static"
ASSETS_DIR = Path("assets")


def safe_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_")
    return slug or "story"


def resolve_output_dir(name: str) -> Path:
    """Resolve an existing output folder by its real name, rejecting path traversal."""
    root = config.OUTPUT_DIR.resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root or not candidate.is_dir():
        raise HTTPException(status_code=404, detail="Output not found")
    return candidate


@app.get("/api/config")
def get_config() -> list[dict]:
    return config_store.get_masked_config()


@app.post("/api/config")
def post_config(payload: ConfigUpdateRequest) -> dict:
    config_store.update_env(payload.values)
    return {"ok": True}


@app.get("/api/prompts")
def get_prompt_categories() -> dict:
    return {"categories": prompt_store.list_categories()}


@app.get("/api/prompts/{category}")
def get_prompt(category: str) -> dict:
    try:
        text = prompt_store.get_current(category)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"text": text, "versions": prompt_store.list_versions(category)}


@app.post("/api/prompts/{category}")
def save_prompt(category: str, payload: PromptSaveRequest) -> dict:
    prompt_store.save_new_version(category, payload.text)
    return {"ok": True}


@app.post("/api/prompts/{category}/restore/{version_id}")
def restore_prompt(category: str, version_id: str) -> dict:
    try:
        prompt_store.restore_version(category, version_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/api/stories")
def list_stories() -> dict:
    stories_dir = config.STORIES_DIR
    stories_dir.mkdir(parents=True, exist_ok=True)
    names = [p.stem for p in sorted(stories_dir.glob("*.txt"))]
    return {"stories": names}


@app.get("/api/stories/{name}")
def get_story(name: str) -> dict:
    path = config.STORIES_DIR / f"{name}.txt"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Story not found")
    return {"name": name, "text": read_story(path)}


@app.post("/api/stories")
def save_story(payload: StorySaveRequest) -> dict:
    stories_dir = config.STORIES_DIR
    stories_dir.mkdir(parents=True, exist_ok=True)
    safe_name = safe_slug(payload.name)
    path = stories_dir / f"{safe_name}.txt"
    path.write_text(payload.text, encoding="utf-8")
    return {"ok": True, "name": safe_name}


@app.get("/api/outputs")
def list_outputs() -> dict:
    output_dir = config.OUTPUT_DIR
    if not output_dir.exists():
        return {"outputs": []}
    results = []
    for story_dir in sorted(output_dir.iterdir()):
        if not story_dir.is_dir() or story_dir.name.startswith("_"):
            continue
        final_video = story_dir / "final_video.mp4"
        has_video = final_video.exists()
        meta = {}
        meta_path = story_dir / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                meta = {}
        duration = meta.get("duration_seconds")
        if duration is None and has_video:
            try:
                duration = round(get_audio_duration(final_video), 1)
            except Exception:  # noqa: BLE001
                duration = None

        images_dir = story_dir / "images"
        images = (
            [f"/output/{story_dir.name}/images/{p.name}" for p in sorted(images_dir.glob("*.png"))]
            if images_dir.is_dir()
            else []
        )

        results.append(
            {
                "name": story_dir.name,
                "has_video": has_video,
                "video_url": f"/output/{story_dir.name}/final_video.mp4" if has_video else None,
                "images": images,
                "description": meta.get("description", ""),
                "language": meta.get("language", ""),
                "category": meta.get("category", ""),
                "style": meta.get("style", ""),
                "voice": meta.get("voice", ""),
                "scene_count": meta.get("scene_count") or len(images) or None,
                "duration_seconds": duration,
                "created_at": meta.get("created_at"),
                "modified_at": final_video.stat().st_mtime if has_video else story_dir.stat().st_mtime,
            }
        )
    results.sort(key=lambda r: r["modified_at"], reverse=True)
    return {"outputs": results}


PREVIEW_DIR = Path("output/_voice_previews")
PREVIEW_TEXT = {
    "hindi": "एक बार की बात है, एक छोटे से गाँव में एक ईमानदार लड़का रहता था।",
    "urdu": "ایک دفعہ کا ذکر ہے، ایک چھوٹے سے گاؤں میں ایک ایماندار لڑکا رہتا تھا۔",
    "arabic": "في قديم الزمان، كان يعيش في قرية صغيرة صبي صادق.",
    "bengali": "এক দেশে এক ছোট গ্রামে একজন সৎ ছেলে বাস করত।",
    "tamil": "ஒரு காலத்தில், ஒரு சிறிய கிராமத்தில் ஒரு நேர்மையான சிறுவன் வாழ்ந்தான்.",
    "telugu": "ఒకప్పుడు, ఒక చిన్న గ్రామంలో ఒక నిజాయితీగల బాలుడు నివసించేవాడు.",
}
DEFAULT_PREVIEW_TEXT = "Once upon a time, in a small village, there lived an honest young boy."

SARVAM_LANGUAGE_CODES = {
    "english": "en-IN",
    "hindi": "hi-IN",
    "hinglish": "hi-IN",
    "bengali": "bn-IN",
    "tamil": "ta-IN",
    "telugu": "te-IN",
    "kannada": "kn-IN",
    "malayalam": "ml-IN",
    "marathi": "mr-IN",
    "gujarati": "gu-IN",
    "odia": "od-IN",
    "punjabi": "pa-IN",
}


@app.post("/api/voice-preview")
def voice_preview(payload: VoicePreviewRequest) -> dict:
    text = PREVIEW_TEXT.get(payload.language.lower(), DEFAULT_PREVIEW_TEXT)
    key = safe_slug(f"{payload.provider}-{payload.voice}-{payload.language}")
    out_path = PREVIEW_DIR / f"{key}.mp3"

    if not out_path.exists():
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        language_code = SARVAM_LANGUAGE_CODES.get(payload.language.lower())
        if payload.provider == "sarvam" and language_code is None:
            raise HTTPException(status_code=400, detail=f"Sarvam does not support {payload.language}.")
        try:
            if payload.provider == "indicf5":
                generate_voice_over_indicf5(text, payload.voice, out_path)
            elif payload.provider == "sarvam":
                generate_voice_over_sarvam(text, payload.voice, out_path, language_code=language_code)
            else:
                generate_voice_over(text, payload.voice, out_path)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"url": f"/output/_voice_previews/{out_path.name}?t={int(out_path.stat().st_mtime)}"}


@app.post("/api/outputs/{name}/remix")
def remix_output(name: str, payload: RemixRequest) -> dict:
    """Re-render an existing output with different background audio, reusing images and voice."""
    story_dir = resolve_output_dir(name)
    safe_name = story_dir.name
    if not (story_dir / "scenes.json").exists():
        raise HTTPException(status_code=404, detail="This output has no scene plan to rebuild from.")

    meta = {}
    meta_path = story_dir / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            meta = {}

    story_file = story_dir / "story.txt"
    fallback = config.STORIES_DIR / f"{safe_name}.txt"
    if story_file.exists():
        story_text = story_file.read_text(encoding="utf-8")
    elif fallback.exists():
        story_text = fallback.read_text(encoding="utf-8")
    else:
        story_text = meta.get("description", safe_name)

    provider = meta.get("tts_provider", "edge")
    voice = meta.get("voice", "en-US-AriaNeural")
    options = PipelineOptions(
        style=meta.get("style", "anime/manga style"),
        language=meta.get("language", "English"),
        category=meta.get("category", "general"),
        tts_provider=provider,
        voice=voice if provider == "edge" else "en-US-AriaNeural",
        sarvam_speaker=voice if provider == "sarvam" else "shubh",
        indicf5_voice=voice if provider == "indicf5" else "mar_m",
        music_file=Path(payload.music_file) if payload.music_file else None,
        music_volume=payload.music_volume,
        ambience_volume=payload.ambience_volume,
    )

    job = jobs.create_job(safe_name, story_text, options)
    return {"job_id": job.id, "story_name": safe_name}


@app.get("/api/outputs/{name}/download")
def download_output(name: str) -> FileResponse:
    story_dir = resolve_output_dir(name)
    video = story_dir / "final_video.mp4"
    if not video.is_file():
        raise HTTPException(status_code=404, detail="This output has no final video yet.")
    return FileResponse(video, media_type="video/mp4", filename=f"{story_dir.name}.mp4")


@app.delete("/api/outputs/{name}")
def delete_output(name: str) -> dict:
    story_dir = resolve_output_dir(name)
    shutil.rmtree(story_dir)
    return {"ok": True}


@app.get("/api/assets")
def list_assets() -> dict:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    files = [p.name for p in sorted(ASSETS_DIR.iterdir()) if p.is_file() and p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")]
    return {"assets": files}


@app.post("/api/assets/upload")
async def upload_asset(file: UploadFile) -> dict:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in ("-", "_", ".")) or "upload.mp3"
    dest = ASSETS_DIR / safe_name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "path": str(dest)}


@app.post("/api/generate")
def start_generate(payload: GenerateRequest) -> dict:
    options = PipelineOptions(
        style=payload.style,
        language=payload.language,
        category=payload.category,
        tts_provider=payload.tts_provider,
        voice=payload.voice,
        voice_rate=payload.voice_rate,
        voice_pitch=payload.voice_pitch,
        sarvam_speaker=payload.sarvam_speaker,
        indicf5_voice=payload.indicf5_voice,
        intro_enabled=payload.intro_enabled,
        intro_title=payload.intro_title,
        intro_subtitle=payload.intro_subtitle,
        outro_enabled=payload.outro_enabled,
        outro_title=payload.outro_title,
        outro_subtitle=payload.outro_subtitle,
        sarvam_pace=payload.sarvam_pace,
        sarvam_temperature=payload.sarvam_temperature,
        size=payload.size,
        transition=payload.transition,
        scene_pause=payload.scene_pause,
        ambience_volume=payload.ambience_volume,
        music_volume=payload.music_volume,
        music_style=payload.music_style,
        music_file=Path(payload.music_file) if payload.music_file else None,
        force_replan=payload.force_replan,
        force_images=payload.force_images,
        force_voice=payload.force_voice,
    )
    safe_name = safe_slug(payload.story_name)
    job = jobs.create_job(safe_name, payload.story_text, options)
    return {"job_id": job.id, "story_name": safe_name}


@app.get("/api/generate/{job_id}/stream")
def stream_generate(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    def event_stream():
        while True:
            event = job.events.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event["type"] in ("complete", "error", "end"):
                if event["type"] == "end":
                    break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(config.OUTPUT_DIR)), name="output")

ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


class NoCacheStaticFiles(StaticFiles):
    """Serve the app shell without caching so UI updates appear on a normal refresh."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


if STATIC_DIR.exists():
    app.mount("/", NoCacheStaticFiles(directory=str(STATIC_DIR), html=True), name="static")
