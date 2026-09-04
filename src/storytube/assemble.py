import json
import subprocess
from pathlib import Path

from .config import FFMPEG_BIN, FFPROBE_BIN


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    # stdin must be detached: ffmpeg reads it for interactive keys, and in a background
    # process group that read raises SIGTTIN and silently suspends the whole render.
    subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=cwd, stdin=subprocess.DEVNULL)


def get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            FFPROBE_BIN,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        stdin=subprocess.DEVNULL,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def pad_audio_with_silence(audio_path: Path, out_path: Path, pad_seconds: float) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(audio_path),
        "-af", f"apad=pad_dur={pad_seconds:.3f}",
        "-c:a", "aac",
        str(out_path),
    ]
    _run(cmd)


def _motion_filter(motion: str, duration: float, fps: int, width: str, height: str) -> str:
    total_frames = max(round(duration * fps) - 1, 1)
    if motion == "zoom_in":
        z_expr = "min(zoom+0.0015,1.2)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion == "zoom_out":
        z_expr = "if(eq(on,0),1.2,max(1.0,zoom-0.0015))"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion == "pan_right":
        z_expr = "1.15"
        x_expr = f"(iw-iw/zoom)*on/{total_frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        z_expr = "1.15"
        x_expr = f"(iw-iw/zoom)*(1-on/{total_frames})"
        y_expr = "ih/2-(ih/zoom/2)"

    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='{z_expr}':d=1:"
        f"x='{x_expr}':y='{y_expr}':s={width}x{height}:fps={fps}"
    )


def build_scene_video_clip(
    image_path: Path,
    duration: float,
    out_path: Path,
    motion: str = "zoom_in",
    fps: int = 25,
    size: str = "1920x1080",
) -> None:
    width, height = size.split("x")
    vf = _motion_filter(motion, duration, fps, width, height)
    cmd = [
        FFMPEG_BIN, "-y",
        "-loop", "1", "-i", str(image_path),
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", f"{duration:.3f}",
        str(out_path),
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(cmd)


def crossfade_concat_videos(
    clip_paths: list[Path],
    durations: list[float],
    out_path: Path,
    transition: float = 0.6,
    fps: int = 25,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(clip_paths) == 1:
        _run([FFMPEG_BIN, "-y", "-i", str(clip_paths[0]), "-c", "copy", str(out_path)])
        return

    inputs = []
    for p in clip_paths:
        inputs += ["-i", str(p)]

    filter_parts = []
    cumulative = durations[0]
    prev_label = "0:v"
    last_index = len(clip_paths) - 1
    for i in range(1, len(clip_paths)):
        offset = max(cumulative - transition, 0.0)
        out_label = f"v{i}" if i < last_index else "vout"
        filter_parts.append(
            f"[{prev_label}][{i}:v]xfade=transition=fade:duration={transition:.3f}:"
            f"offset={offset:.3f}[{out_label}]"
        )
        cumulative = cumulative + durations[i] - transition
        prev_label = out_label

    cmd = [
        FFMPEG_BIN, "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "[vout]",
        "-r", str(fps),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    _run(cmd)


def crossfade_concat_audios(
    audio_paths: list[Path],
    out_path: Path,
    transition: float = 0.6,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(audio_paths) == 1:
        _run([FFMPEG_BIN, "-y", "-i", str(audio_paths[0]), "-c:a", "aac", str(out_path)])
        return

    inputs = []
    for p in audio_paths:
        inputs += ["-i", str(p)]

    filter_parts = []
    prev_label = "0:a"
    last_index = len(audio_paths) - 1
    for i in range(1, len(audio_paths)):
        out_label = f"a{i}" if i < last_index else "aout"
        filter_parts.append(f"[{prev_label}][{i}:a]acrossfade=d={transition:.3f}[{out_label}]")
        prev_label = out_label

    cmd = [
        FFMPEG_BIN, "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "[aout]",
        "-c:a", "aac",
        str(out_path),
    ]
    _run(cmd)


def add_background_ambience(
    voice_path: Path,
    out_path: Path,
    duration: float,
    ambience_volume: float = 0.1,
    music_volume: float = 0.0,
    music_style: str = "arabic",
    music_file: Path | None = None,
    percussion_period: float = 1.4,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    layers = ["[voice]"]
    filter_parts = [
        f"anoisesrc=color=pink:amplitude=1:duration={duration:.3f}[noise]",
        f"[noise]lowpass=f=600,highpass=f=80,tremolo=f=0.15:d=0.4,volume={ambience_volume}[amb]",
        "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[voice]",
    ]
    layers.append("[amb]")

    extra_inputs: list[str] = []
    if music_volume > 0 and music_file is not None:
        extra_inputs += ["-stream_loop", "-1", "-i", str(music_file)]
        filter_parts.append(
            f"[1:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={max(duration - 2, 0):.3f}:d=2,"
            f"volume={music_volume:.3f}[music]"
        )
        layers.append("[music]")
    elif music_volume > 0 and music_style == "arabic":
        filter_parts.append(
            f"aevalsrc=exprs='0.5*sin(2*PI*110*t)+0.25*sin(2*PI*165*t)':s=44100:d={duration:.3f}[droneraw]"
        )
        filter_parts.append(f"[droneraw]lowpass=f=500,volume={music_volume:.3f}[drone]")
        filter_parts.append(
            f"aevalsrc=exprs='if(lt(mod(t\\,{percussion_period:.3f})\\,0.35)"
            f"\\,exp(-7*mod(t\\,{percussion_period:.3f}))*sin(2*PI*90*t)\\,0)':s=44100:d={duration:.3f}[percraw]"
        )
        filter_parts.append(f"[percraw]volume={(music_volume * 1.3):.3f}[perc]")
        layers.extend(["[drone]", "[perc]"])

    filter_parts.append(
        f"{''.join(layers)}amix=inputs={len(layers)}:duration=first:dropout_transition=2[mixed]"
    )
    filter_complex = ";".join(filter_parts)
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(voice_path),
        *extra_inputs,
        "-filter_complex", filter_complex,
        "-map", "[mixed]",
        "-c:a", "aac",
        str(out_path),
    ]
    _run(cmd)


def mux_audio_video(video_path: Path, audio_path: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac",
        "-shortest",
        str(out_path),
    ]
    _run(cmd)


def burn_captions(video_path: Path, srt_path: Path, out_path: Path) -> None:
    style = (
        "FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=3,Outline=2,"
        "Alignment=2,MarginV=60"
    )
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", video_path.name,
        "-vf", f"subtitles=filename={srt_path.name}:force_style='{style}'",
        "-c:a", "copy",
        "-movflags", "+faststart",
        out_path.name,
    ]
    _run(cmd, cwd=video_path.parent)
