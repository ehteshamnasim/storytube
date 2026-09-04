import json
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .assemble import (
    add_background_ambience,
    build_scene_video_clip,
    burn_captions,
    crossfade_concat_audios,
    crossfade_concat_videos,
    get_audio_duration,
    mux_audio_video,
    pad_audio_with_silence,
)
from .captions import build_srt
from . import config
from .bookends import build_card_clip, build_title_card, concat_clips
from .image_gen import generate_image
from .scene_planner import plan_scenes
from .tts import generate_voice_over
from .tts_indicf5 import generate_voice_over_indicf5
from .tts_sarvam import estimate_word_boundaries, generate_voice_over_sarvam

MOTION_CYCLE = ["zoom_in", "zoom_out", "pan_right", "pan_left"]

ProgressCallback = Callable[[dict], None]


@dataclass
class PipelineOptions:
    style: str = "anime/manga style"
    language: str = "English"
    category: str = "general"

    tts_provider: str = "edge"
    voice: str = "en-US-AriaNeural"
    voice_rate: str = "+0%"
    voice_pitch: str = "+0Hz"
    sarvam_speaker: str = "shubh"
    sarvam_pace: float = 1.0
    sarvam_temperature: float = 0.6
    indicf5_voice: str = "mar_m"

    size: str = "1920x1080"
    transition: float = 0.6
    scene_pause: float = 0.6
    ambience_volume: float = 0.1
    music_volume: float = 0.0
    music_style: str = "arabic"
    music_file: Optional[Path] = None

    force_replan: bool = False
    force_images: bool = False
    force_voice: bool = False

    intro_enabled: bool = True
    intro_title: str = ""
    intro_subtitle: str = ""
    intro_seconds: float = 3.5
    outro_enabled: bool = True
    outro_title: str = "Thank you for watching"
    outro_subtitle: str = "Subscribe for more stories"
    outro_seconds: float = 4.0


def titleize(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").strip().title()


def _emit(callback: Optional[ProgressCallback], **kwargs) -> None:
    if callback is not None:
        callback(kwargs)


def run_pipeline(
    story_text: str,
    story_name: str,
    options: PipelineOptions,
    on_progress: Optional[ProgressCallback] = None,
) -> Path:
    out_dir = config.OUTPUT_DIR / story_name
    images_dir = out_dir / "images"
    audio_dir = out_dir / "audio"
    clips_dir = out_dir / "clips"

    out_dir.mkdir(parents=True, exist_ok=True)
    scenes_path = out_dir / "scenes.json"
    # Kept so the output can be re-rendered later without the original stories/ file.
    (out_dir / "story.txt").write_text(story_text, encoding="utf-8")

    if scenes_path.exists() and not options.force_replan:
        _emit(on_progress, stage="plan", message=f"Reusing existing scene plan: {scenes_path}")
        plan = json.loads(scenes_path.read_text(encoding="utf-8"))
    else:
        _emit(
            on_progress,
            stage="plan",
            message=f"Planning scenes for '{story_name}' ({options.category}, {options.language})...",
        )
        plan = plan_scenes(
            story_text, style=options.style, language=options.language, category=options.category
        )
        scenes_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        _emit(on_progress, stage="plan", message=f"Saved scene plan: {scenes_path}")

    character_sheet = plan["character_sheet"]
    scenes = plan["scenes"]
    seed = zlib.crc32(story_name.encode("utf-8")) % 2_147_483_647
    video_w, video_h = (int(part) for part in options.size.split("x"))
    total = len(scenes)
    _emit(on_progress, stage="plan_done", message=f"Processing {total} scenes (seed={seed})...", total=total)

    video_clip_paths = []
    audio_paths = []
    durations = []
    scenes_words = []

    for i, scene in enumerate(scenes):
        scene_id = scene["id"]
        image_path = images_dir / f"scene_{scene_id:02d}.png"
        if image_path.exists() and not options.force_images:
            _emit(
                on_progress,
                stage="image",
                scene=scene_id,
                total=total,
                message=f"scene {scene_id}: reusing existing image",
            )
        else:
            if scene.get("include_character_sheet", True):
                full_prompt = f"{options.style}, {character_sheet}. {scene['image_prompt']}"
            else:
                full_prompt = f"{options.style}, {scene['image_prompt']}"
            # Generate at the video's own resolution so frames are never upscaled.
            generate_image(full_prompt, image_path, seed=seed + scene_id, width=video_w, height=video_h)
            _emit(on_progress, stage="image", scene=scene_id, total=total, message=f"scene {scene_id}: image done")

        audio_path = audio_dir / f"scene_{scene_id:02d}.mp3"
        words_path = audio_dir / f"scene_{scene_id:02d}_words.json"

        if audio_path.exists() and words_path.exists() and not options.force_voice:
            words = json.loads(words_path.read_text(encoding="utf-8"))
            duration = get_audio_duration(audio_path)
            _emit(
                on_progress,
                stage="voice",
                scene=scene_id,
                total=total,
                message=f"scene {scene_id}: reusing existing voice-over",
            )
        elif options.tts_provider == "indicf5":
            generate_voice_over_indicf5(scene["narration"], options.indicf5_voice, audio_path)
            duration = get_audio_duration(audio_path)
            words = estimate_word_boundaries(scene["narration"], duration)
        elif options.tts_provider == "sarvam":
            language_code_map = {"hindi": "hi-IN", "urdu": "hi-IN", "english": "en-IN"}
            language_code = language_code_map.get(options.language.lower(), "hi-IN")
            generate_voice_over_sarvam(
                scene["narration"],
                options.sarvam_speaker,
                audio_path,
                language_code=language_code,
                pace=options.sarvam_pace,
                temperature=options.sarvam_temperature,
            )
            duration = get_audio_duration(audio_path)
            words = estimate_word_boundaries(scene["narration"], duration)
        else:
            words = generate_voice_over(
                scene["narration"],
                options.voice,
                audio_path,
                rate=options.voice_rate,
                pitch=options.voice_pitch,
            )
            duration = get_audio_duration(audio_path)

        words_path.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")

        if options.scene_pause > 0:
            padded_path = audio_dir / f"scene_{scene_id:02d}_padded.m4a"
            pad_audio_with_silence(audio_path, padded_path, options.scene_pause)
            audio_path = padded_path
            duration += options.scene_pause
        _emit(
            on_progress,
            stage="voice",
            scene=scene_id,
            total=total,
            message=f"scene {scene_id}: voice-over done ({duration:.1f}s)",
        )

        motion = MOTION_CYCLE[i % len(MOTION_CYCLE)]
        video_clip_path = clips_dir / f"scene_{scene_id:02d}_video.mp4"
        build_scene_video_clip(image_path, duration, video_clip_path, motion=motion, size=options.size)
        _emit(
            on_progress,
            stage="video_clip",
            scene=scene_id,
            total=total,
            message=f"scene {scene_id}: video clip done ({motion})",
        )

        video_clip_paths.append(video_clip_path)
        audio_paths.append(audio_path)
        durations.append(duration)
        scenes_words.append(words)

    scene_offsets = []
    cumulative_time = 0.0
    for d in durations:
        scene_offsets.append(cumulative_time)
        cumulative_time += d
    adjusted_offsets = [
        max(0.0, offset - i * options.transition) for i, offset in enumerate(scene_offsets)
    ]

    _emit(on_progress, stage="captions", message="Building captions...")
    srt_path = out_dir / "captions.srt"
    build_srt(scenes_words, adjusted_offsets, srt_path)

    _emit(on_progress, stage="crossfade_video", message="Crossfading video clips...")
    concatenated_video_path = out_dir / "concatenated_video.mp4"
    crossfade_concat_videos(
        video_clip_paths, durations, concatenated_video_path, transition=options.transition
    )

    _emit(on_progress, stage="crossfade_audio", message="Crossfading voice-over audio...")
    concatenated_audio_path = out_dir / "concatenated_audio.m4a"
    crossfade_concat_audios(audio_paths, concatenated_audio_path, transition=options.transition)

    total_duration = sum(durations) - (len(durations) - 1) * options.transition
    final_audio_path = out_dir / "final_audio.m4a"
    if options.ambience_volume > 0 or options.music_volume > 0:
        _emit(on_progress, stage="mixing", message="Mixing background ambience/music...")
        add_background_ambience(
            concatenated_audio_path,
            final_audio_path,
            total_duration,
            ambience_volume=options.ambience_volume,
            music_volume=options.music_volume,
            music_style=options.music_style,
            music_file=options.music_file,
        )
    else:
        final_audio_path = concatenated_audio_path

    _emit(on_progress, stage="muxing", message="Muxing video and audio...")
    concatenated_path = out_dir / "concatenated.mp4"
    mux_audio_video(concatenated_video_path, final_audio_path, concatenated_path)

    _emit(on_progress, stage="burning", message="Burning captions into final video...")
    final_path = out_dir / "final_video.mp4"
    captioned_path = out_dir / "captioned.mp4"
    burn_captions(concatenated_path, srt_path, captioned_path)

    if options.intro_enabled or options.outro_enabled:
        _emit(on_progress, stage="bookends", message="Adding intro and outro...")
        parts: list[Path] = []

        if options.intro_enabled:
            card = build_title_card(
                images_dir / "scene_01.png",
                options.intro_title or titleize(story_name),
                options.intro_subtitle,
                out_dir / "intro_card.png",
                size=options.size,
            )
            parts.append(
                build_card_clip(
                    card,
                    options.intro_seconds,
                    clips_dir / "intro.mp4",
                    size=options.size,
                    music_file=options.music_file,
                    music_volume=max(0.18, options.music_volume),
                )
            )

        parts.append(captioned_path)

        if options.outro_enabled:
            last_image = images_dir / f"scene_{scenes[-1]['id']:02d}.png"
            card = build_title_card(
                last_image if last_image.exists() else images_dir / "scene_01.png",
                options.outro_title,
                options.outro_subtitle,
                out_dir / "outro_card.png",
                size=options.size,
            )
            parts.append(
                build_card_clip(
                    card,
                    options.outro_seconds,
                    clips_dir / "outro.mp4",
                    size=options.size,
                    music_file=options.music_file,
                    music_volume=max(0.18, options.music_volume),
                    music_offset=20.0,
                )
            )

        concat_clips(parts, final_path, size=options.size)
        total_duration += (options.intro_seconds if options.intro_enabled else 0) + (
            options.outro_seconds if options.outro_enabled else 0
        )
    else:
        captioned_path.replace(final_path)

    meta = {
        "story_name": story_name,
        "description": story_text.strip().splitlines()[0][:200] if story_text.strip() else "",
        "style": options.style,
        "language": options.language,
        "category": options.category,
        "tts_provider": options.tts_provider,
        "voice": {
            "sarvam": options.sarvam_speaker,
            "indicf5": options.indicf5_voice,
        }.get(options.tts_provider, options.voice),
        "scene_count": total,
        "duration_seconds": round(total_duration, 1),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    _emit(on_progress, stage="done", message=f"Done. Final video: {final_path}")
    return final_path
