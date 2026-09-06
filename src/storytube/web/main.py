from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import config
from ..assemble import get_audio_duration
from .. import instagram
from .. import youtube
from ..pipeline import PipelineOptions
from ..poetry import (
    MAX_POEM_CHARS,
    MAX_POEM_LINES,
    MIN_BACKGROUND_EDGE,
    DELIVERY,
    POEM_TEMPLATES,
    POET_AVATARS,
    POET_AVATARS_DIR,
    PoemError,
    PoemOptions,
    _segment_lines,
    clean_poem,
    load_photo,
    prepare_background,
    render_poem_card,
    undrawable_characters,
)
from ..story_reader import read_story
from ..tts import generate_voice_over
from ..tts_elevenlabs import generate_voice_over_elevenlabs, list_voices as list_elevenlabs_voices
from ..tts_indicf5 import generate_voice_over_indicf5
from ..tts_sarvam import generate_voice_over_sarvam
from . import config_store, jobs, prompt_store
from .schemas import (
    BulkDeleteRequest,
    ConfigUpdateRequest,
    GenerateRequest,
    PoemRequest,
    PromptSaveRequest,
    PublishRequest,
    RemixRequest,
    StorySaveRequest,
    VoicePreviewRequest,
    YoutubeConnectRequest,
    YoutubePublishRequest,
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


def poem_folder_name(first_line: str) -> str:
    """Slug the opening line, falling back to a timestamp for scripts with no Latin letters."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", first_line[:40]).strip("_").lower()
    if len(slug) >= 3:
        return f"poem_{slug}"
    return f"poem_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


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


def video_file(story_dir: Path) -> Optional[Path]:
    """Story runs produce final_video.mp4, poem runs produce reel.mp4."""
    for candidate in ("final_video.mp4", "reel.mp4"):
        path = story_dir / candidate
        if path.exists():
            return path
    return None


def thumbnail_file(story_dir: Path) -> Optional[Path]:
    """The best still to use as a custom YouTube thumbnail.

    A poem's card.png already has the poem lettered onto it, so it makes a far better
    thumbnail than any single video frame. A story has no such card, so the first scene
    image stands in instead.
    """
    card = story_dir / "card.png"
    if card.exists():
        return card
    images_dir = story_dir / "images"
    if images_dir.is_dir():
        first = sorted(images_dir.glob("*.png"))
        if first:
            return first[0]
    return None


@app.get("/api/outputs")
def list_outputs() -> dict:
    output_dir = config.OUTPUT_DIR
    if not output_dir.exists():
        return {"outputs": []}
    results = []
    for story_dir in sorted(output_dir.iterdir()):
        if not story_dir.is_dir() or story_dir.name.startswith("_"):
            continue
        final_video = video_file(story_dir)
        has_video = final_video is not None
        meta = {}
        meta_path = story_dir / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                meta = {}
        duration = meta.get("duration_seconds")
        if duration is None and final_video:
            try:
                duration = round(get_audio_duration(final_video), 1)
            except Exception:  # noqa: BLE001
                duration = None

        kind = meta.get("kind", "story")
        images_dir = story_dir / "images"
        if kind == "poem":
            images = [
                f"/output/{story_dir.name}/{p.name}"
                for p in (story_dir / "card.png", story_dir / "background.png")
                if p.exists()
            ]
        elif images_dir.is_dir():
            images = [f"/output/{story_dir.name}/images/{p.name}" for p in sorted(images_dir.glob("*.png"))]
        else:
            images = []

        caption_path = story_dir / "caption.txt"
        caption = caption_path.read_text(encoding="utf-8") if caption_path.exists() else ""
        posted = instagram.read_state(story_dir)
        posted_yt = youtube.read_state(story_dir)

        size = meta.get("size") or ("1080x1920" if kind == "poem" else "1920x1080")
        try:
            frame_w, frame_h = (int(p) for p in str(size).split("x"))
        except ValueError:
            frame_w, frame_h = 1920, 1080
        if frame_h > frame_w:
            orientation = "portrait"
        elif frame_w > frame_h:
            orientation = "landscape"
        else:
            orientation = "square"

        results.append(
            {
                "name": story_dir.name,
                "kind": kind,
                "size": size,
                "orientation": orientation,
                "has_video": has_video,
                "video_url": f"/output/{story_dir.name}/{final_video.name}" if final_video else None,
                "images": images,
                "caption": caption,
                "instagram": posted or None,
                "youtube": posted_yt or None,
                "is_draft": (story_dir / ".draft").exists(),
                "description": meta.get("description") or meta.get("mood", ""),
                "language": meta.get("language", ""),
                "category": meta.get("category", ""),
                "style": meta.get("style", ""),
                "voice": meta.get("voice", ""),
                "scene_count": meta.get("scene_count") or (len(images) if kind != "poem" else None),
                "duration_seconds": duration,
                "created_at": meta.get("created_at"),
                "modified_at": final_video.stat().st_mtime if final_video else story_dir.stat().st_mtime,
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


@app.get("/api/elevenlabs/voices")
def elevenlabs_voices() -> dict:
    try:
        return {"voices": list_elevenlabs_voices()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/voice-preview")
def voice_preview(payload: VoicePreviewRequest) -> dict:
    text = PREVIEW_TEXT.get(payload.language.lower(), DEFAULT_PREVIEW_TEXT)
    key = safe_slug(f"{payload.provider}-{payload.voice}-{payload.language}-{payload.delivery}")
    out_path = PREVIEW_DIR / f"{key}.mp3"

    # A previous failure can leave a zero-byte file, which would replay as silence forever.
    if not out_path.exists() or out_path.stat().st_size == 0:
        out_path.unlink(missing_ok=True)
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        language_code = SARVAM_LANGUAGE_CODES.get(payload.language.lower())
        if payload.provider == "sarvam" and language_code is None:
            raise HTTPException(status_code=400, detail=f"Sarvam does not support {payload.language}.")
        try:
            if payload.provider == "indicf5":
                generate_voice_over_indicf5(text, payload.voice, out_path)
            elif payload.provider == "sarvam":
                generate_voice_over_sarvam(text, payload.voice, out_path, language_code=language_code)
            elif payload.provider == "elevenlabs":
                pace = DELIVERY.get(payload.delivery, DELIVERY["natural"])
                generate_voice_over_elevenlabs(
                    text, payload.voice, out_path, language=payload.language,
                    style=pace["style"], speed=pace["speed"],
                )
            else:
                pace = DELIVERY.get(payload.delivery, DELIVERY["natural"])
                generate_voice_over(text, payload.voice, out_path, rate=pace["rate"], pitch=pace["pitch"])
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


@app.post("/api/poem")
def start_poem(payload: PoemRequest) -> dict:
    try:
        lines = clean_poem(payload.poem_text)
    except PoemError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    base = safe_slug(payload.name) if payload.name.strip() else poem_folder_name(lines[0])
    name = base
    counter = 2
    while (config.OUTPUT_DIR / name).exists() and not payload.force_image:
        name = f"{base}_{counter}"
        counter += 1

    options = PoemOptions(
        style=payload.style,
        language=payload.language,
        size=payload.size,
        seconds_per_line=payload.seconds_per_line,
        music_file=Path(payload.music_file) if payload.music_file else None,
        music_volume=payload.music_volume,
        handle=payload.handle.strip(),
        seed=payload.seed,
        force_image=payload.force_image,
        background_file=resolve_poem_background(payload),
        focus_x=payload.focus_x,
        focus_y=payload.focus_y,
        zoom=payload.zoom,
        narrate=payload.narrate,
        voice=payload.voice,
        delivery=payload.delivery,
        voice_provider=payload.voice_provider,
        text_scale=payload.text_scale,
        avatar_id=payload.avatar_id,
        lines_per_segment=payload.lines_per_segment,
        transition=payload.transition,
        transition_seconds=payload.transition_seconds,
    )
    job = jobs.create_poem_job(name, "\n".join(lines), options)
    return {"job_id": job.id, "name": name, "lines": lines}


@app.post("/api/instagram/test")
def instagram_test() -> dict:
    env = config_store.get_raw_env()
    try:
        return {"ok": True, **instagram.test_connection(env.get("IG_USER_ID", ""), env.get("IG_ACCESS_TOKEN", ""))}
    except instagram.InstagramError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/outputs/{name}/instagram/publish")
def instagram_publish(name: str, payload: PublishRequest) -> dict:
    story_dir = resolve_output_dir(name)
    video = video_file(story_dir)
    if video is None:
        raise HTTPException(status_code=404, detail="This output has no video to post.")

    existing = instagram.read_state(story_dir)
    if existing.get("media_id") and not payload.force:
        raise HTTPException(status_code=409, detail="This video has already been posted to Instagram.")

    env = config_store.get_raw_env()
    user_id, token = env.get("IG_USER_ID", ""), env.get("IG_ACCESS_TOKEN", "")
    if not user_id or not token:
        raise HTTPException(status_code=400, detail="Add your Instagram details in Settings first.")

    caption = payload.caption
    if not caption.strip():
        caption_path = story_dir / "caption.txt"
        caption = caption_path.read_text(encoding="utf-8") if caption_path.exists() else story_dir.name

    job = jobs.create_instagram_job(story_dir.name, video, caption, story_dir, user_id, token)
    return {"job_id": job.id, "name": story_dir.name}


@app.get("/api/outputs/{name}/instagram")
def instagram_status(name: str, refresh: bool = False) -> dict:
    story_dir = resolve_output_dir(name)
    state = instagram.read_state(story_dir)
    if not state.get("media_id"):
        return {"posted": False}

    if refresh:
        env = config_store.get_raw_env()
        try:
            insights = instagram.get_insights(
                state["media_id"], env.get("IG_USER_ID", ""), env.get("IG_ACCESS_TOKEN", "")
            )
            state["stats"] = insights["stats"]
            state["permalink"] = insights["permalink"] or state.get("permalink", "")
            state["stats_at"] = datetime.now().isoformat(timespec="seconds")
            instagram.write_state(story_dir, state)
        except instagram.InstagramError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"posted": True, **state}


@app.post("/api/youtube/connect")
def youtube_connect() -> dict:
    env = config_store.get_raw_env()
    try:
        session = youtube.start_connect(env.get("YOUTUBE_CLIENT_ID", ""), env.get("YOUTUBE_CLIENT_SECRET", ""))
    except youtube.YouTubeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session_id": session.id, "auth_url": session.auth_url}


@app.get("/api/youtube/connect/status")
def youtube_connect_status(session_id: str) -> dict:
    session = youtube.get_connect_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Unknown connect session.")

    channel = None
    if session.channel:
        if session.status == "connected":
            config_store.update_env(
                {
                    "YOUTUBE_REFRESH_TOKEN": session.channel["refresh_token"],
                    "YOUTUBE_CHANNEL_ID": session.channel["channel_id"],
                    "YOUTUBE_CHANNEL_TITLE": session.channel["title"],
                }
            )
        channel = {k: v for k, v in session.channel.items() if k != "refresh_token"}

    return {"status": session.status, "error": session.error, "channel": channel}


@app.get("/api/youtube/test")
def youtube_test() -> dict:
    env = config_store.get_raw_env()
    try:
        token = youtube.refresh_access_token(
            env.get("YOUTUBE_CLIENT_ID", ""), env.get("YOUTUBE_CLIENT_SECRET", ""), env.get("YOUTUBE_REFRESH_TOKEN", "")
        )
        channel = youtube.get_channel(token)
    except youtube.YouTubeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **channel}


@app.post("/api/outputs/{name}/youtube/publish")
def youtube_publish(name: str, payload: YoutubePublishRequest) -> dict:
    story_dir = resolve_output_dir(name)
    video = video_file(story_dir)
    if video is None:
        raise HTTPException(status_code=404, detail="This output has no video to post.")

    existing = youtube.read_state(story_dir)
    if existing.get("video_id") and not payload.force:
        raise HTTPException(status_code=409, detail="This video has already been posted to YouTube.")

    env = config_store.get_raw_env()
    try:
        access_token = youtube.refresh_access_token(
            env.get("YOUTUBE_CLIENT_ID", ""), env.get("YOUTUBE_CLIENT_SECRET", ""), env.get("YOUTUBE_REFRESH_TOKEN", "")
        )
    except youtube.YouTubeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        duration = get_audio_duration(video)
    except Exception:  # noqa: BLE001
        duration = None
    if duration and duration > youtube.MAX_SHORT_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"This video is {duration:.0f}s, longer than YouTube's {youtube.MAX_SHORT_SECONDS}s Shorts limit.",
        )

    title = payload.title.strip() or name.replace("_", " ").title()[:100]
    description = payload.description
    if not description.strip():
        caption_path = story_dir / "caption.txt"
        description = caption_path.read_text(encoding="utf-8") if caption_path.exists() else ""

    job = jobs.create_youtube_job(
        story_dir.name, video, title, description, story_dir, access_token, payload.privacy,
        thumbnail_path=thumbnail_file(story_dir),
    )
    return {"job_id": job.id, "name": story_dir.name}


@app.get("/api/outputs/{name}/youtube")
def youtube_status(name: str, refresh: bool = False) -> dict:
    story_dir = resolve_output_dir(name)
    state = youtube.read_state(story_dir)
    if not state.get("video_id"):
        return {"posted": False}

    if refresh:
        env = config_store.get_raw_env()
        try:
            access_token = youtube.refresh_access_token(
                env.get("YOUTUBE_CLIENT_ID", ""), env.get("YOUTUBE_CLIENT_SECRET", ""), env.get("YOUTUBE_REFRESH_TOKEN", "")
            )
            state["stats"] = youtube.get_stats(state["video_id"], access_token)
            try:
                analytics = youtube.get_analytics(env.get("YOUTUBE_CHANNEL_ID", ""), state["video_id"], access_token)
                if analytics:
                    state["analytics"] = analytics
            except youtube.YouTubeError:
                pass
            state["stats_at"] = datetime.now().isoformat(timespec="seconds")
            youtube.write_state(story_dir, state)
        except youtube.YouTubeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"posted": True, **state}


@app.get("/api/poem/limits")
def poem_limits() -> dict:
    return {"max_chars": MAX_POEM_CHARS, "max_lines": MAX_POEM_LINES}


@app.post("/api/poem/check")
def poem_check(payload: PoemRequest) -> dict:
    """Validate the poem the same way generation will, before spending minutes on an image."""
    try:
        lines = clean_poem(payload.poem_text)
    except PoemError as exc:
        return {"ok": False, "error": str(exc), "lines": [], "undrawable": []}

    text = " ".join(lines) + payload.handle
    return {
        "ok": True,
        "error": "",
        "lines": lines,
        "undrawable": undrawable_characters(text),
    }


UPLOAD_DIR = Path("output/_uploads")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".avif"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
KEEP_UPLOADS = 20


def resolve_upload(name: str) -> Path:
    root = UPLOAD_DIR.resolve()
    candidate = (root / Path(name).name).resolve()
    if candidate.parent != root or not candidate.is_file():
        raise HTTPException(status_code=404, detail="That uploaded image is no longer available.")
    return candidate


def prune_uploads() -> None:
    files = sorted(UPLOAD_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in files[KEEP_UPLOADS:]:
        stale.unlink(missing_ok=True)


def resolve_poem_background(payload: "PoemRequest") -> Optional[Path]:
    if payload.template_id:
        template = next((t for t in POEM_TEMPLATES if t["id"] == payload.template_id), None)
        if template is None:
            raise HTTPException(status_code=400, detail="That template no longer exists.")
        path = Path("assets/poem_templates") / f"{template['id']}.png"
        if not path.is_file():
            raise HTTPException(status_code=400, detail="That template's image is missing on disk.")
        return path
    if payload.background_file:
        return resolve_upload(payload.background_file)
    return None


PREVIEW_DIR = config.OUTPUT_DIR / "_preview"


@app.post("/api/poem/preview")
def preview_poem(payload: PoemRequest) -> dict:
    """Render the on-screen card(s) as still images, fast, so people can check text/emoji/
    segment settings before spending time and API calls on a full reel."""
    try:
        lines = clean_poem(payload.poem_text)
    except PoemError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_file = resolve_poem_background(payload)
    if background_file is None:
        raise HTTPException(status_code=400, detail="Pick a template or upload a background image to preview.")

    avatar_file = None
    poet_name = ""
    if payload.avatar_id:
        poet = next((p for p in POET_AVATARS if p["id"] == payload.avatar_id), None)
        if poet:
            avatar_file = POET_AVATARS_DIR / poet["file"]
            poet_name = poet["label"]

    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    prepared_bg = PREVIEW_DIR / "background.png"
    prepare_background(background_file, prepared_bg, payload.size, payload.focus_x, payload.focus_y, payload.zoom)

    segments = _segment_lines(lines, payload.lines_per_segment)
    stamp = int(datetime.now().timestamp())
    images = []
    for i, segment in enumerate(segments):
        filename = f"segment_{i:02d}.png"
        render_poem_card(
            prepared_bg, segment, PREVIEW_DIR / filename, payload.size, payload.handle, payload.text_scale,
            avatar_file, poet_name,
        )
        images.append(f"/output/_preview/{filename}?t={stamp}")

    return {"ok": True, "segments": len(segments), "images": images}


@app.post("/api/poem/background")
async def upload_background(file: UploadFile) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"{suffix or 'That file'} is not an image. Use JPG, PNG, WEBP or HEIC.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"That image is {len(data) / 1024 / 1024:.0f} MB. Keep it under 25 MB.",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stem = safe_slug(Path(file.filename or "image").stem)[:40] or "image"
    dest = UPLOAD_DIR / f"{stem}_{datetime.now():%H%M%S%f}{suffix}"
    dest.write_bytes(data)

    try:
        photo = load_photo(dest)
        width, height = photo.size
    except PoemError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if min(width, height) < MIN_BACKGROUND_EDGE:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"That image is only {width}x{height}. Use one at least {MIN_BACKGROUND_EDGE}px on each side.",
        )

    # HEIC and friends cannot be shown by the browser, so serve a JPEG for the crop preview.
    preview = dest.with_suffix(".preview.jpg")
    photo.copy().save(preview, "JPEG", quality=88)
    prune_uploads()

    return {
        "path": dest.name,
        "url": f"/output/_uploads/{preview.name}",
        "width": width,
        "height": height,
    }


@app.get("/api/outputs/{name}/download")
def download_output(name: str) -> FileResponse:
    story_dir = resolve_output_dir(name)
    video = video_file(story_dir)
    if video is None:
        raise HTTPException(status_code=404, detail="This output has no final video yet.")
    return FileResponse(video, media_type="video/mp4", filename=f"{story_dir.name}.mp4")


@app.delete("/api/outputs/{name}")
def delete_output(name: str) -> dict:
    story_dir = resolve_output_dir(name)
    shutil.rmtree(story_dir)
    return {"ok": True}


@app.post("/api/outputs/bulk_delete")
def bulk_delete_outputs(payload: BulkDeleteRequest) -> dict:
    deleted, failed = [], []
    for name in payload.names:
        try:
            story_dir = resolve_output_dir(name)
            shutil.rmtree(story_dir)
            deleted.append(name)
        except HTTPException:
            failed.append(name)
    return {"deleted": deleted, "failed": failed}


@app.post("/api/outputs/{name}/draft")
def mark_output_draft(name: str) -> dict:
    """Called right after a fresh generation finishes. Lets an abandoned reel be told
    apart from one you actually kept, so leaving without saving can clean up after itself."""
    story_dir = resolve_output_dir(name)
    (story_dir / ".draft").touch()
    return {"ok": True}


@app.post("/api/outputs/{name}/save")
def save_output(name: str) -> dict:
    story_dir = resolve_output_dir(name)
    (story_dir / ".draft").unlink(missing_ok=True)
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


@app.get("/api/poem/templates")
def poem_templates() -> dict:
    templates_dir = Path("assets/poem_templates")
    items = []
    for t in POEM_TEMPLATES:
        background = templates_dir / f"{t['id']}.png"
        if not background.exists():
            continue
        items.append({
            "id": t["id"],
            "label": t["label"],
            "thumbnail_url": f"/assets/poem_templates/{t['id']}_thumb.jpg",
            "background_url": f"/assets/poem_templates/{t['id']}.png",
            "music": t["music"],
        })
    return {"templates": items}


@app.get("/api/poem/avatars")
def poem_avatars() -> dict:
    avatars_dir = Path("assets/poets")
    items = []
    for a in POET_AVATARS:
        path = avatars_dir / a["file"]
        if path.is_file():
            items.append({"id": a["id"], "label": a["label"], "image_url": f"/assets/poets/{a['file']}"})
    return {"avatars": items}


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


class NoCacheStaticFiles(StaticFiles):
    """Serve files without caching, so regenerated media and UI updates appear on a refresh."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# Remixing rewrites final_video.mp4 in place, so the browser must revalidate it.
app.mount("/output", NoCacheStaticFiles(directory=str(config.OUTPUT_DIR)), name="output")

ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

if STATIC_DIR.exists():
    app.mount("/", NoCacheStaticFiles(directory=str(STATIC_DIR), html=True), name="static")
