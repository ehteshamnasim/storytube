from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import FFMPEG_BIN

# Devanagari-capable first, so Hindi and Urdu titles are not rendered as empty boxes.
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(size: int, prefer_latin: bool = False) -> ImageFont.FreeTypeFont:
    candidates = FONT_CANDIDATES[1:] + FONT_CANDIDATES[:1] if prefer_latin else FONT_CANDIDATES
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def build_title_card(
    background: Path,
    title: str,
    subtitle: str,
    out_path: Path,
    size: str = "1920x1080",
) -> Path:
    width, height = (int(p) for p in size.split("x"))

    base = Image.open(background).convert("RGB")
    scale = max(width / base.width, height / base.height)
    base = base.resize((round(base.width * scale), round(base.height * scale)), Image.LANCZOS)
    left = (base.width - width) // 2
    top = (base.height - height) // 2
    base = base.crop((left, top, left + width, top + height))

    base = base.filter(ImageFilter.GaussianBlur(width * 0.004))
    overlay = Image.new("RGBA", (width, height), (18, 16, 14, 150))
    card = Image.alpha_composite(base.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(card)
    title_font = _load_font(int(height * 0.085))
    subtitle_font = _load_font(int(height * 0.032))

    max_text_width = int(width * 0.78)
    lines = _wrap(draw, title, title_font, max_text_width)
    line_height = int(height * 0.105)
    block_height = line_height * len(lines) + (int(height * 0.06) if subtitle else 0)
    y = (height - block_height) / 2

    for line in lines:
        text_width = draw.textlength(line, font=title_font)
        x = (width - text_width) / 2
        draw.text((x + 2, y + 3), line, font=title_font, fill=(0, 0, 0, 130))
        draw.text((x, y), line, font=title_font, fill=(250, 247, 240))
        y += line_height

    if subtitle:
        y += int(height * 0.012)
        rule_width = int(width * 0.09)
        rule_y = int(y)
        draw.line(
            [((width - rule_width) / 2, rule_y), ((width + rule_width) / 2, rule_y)],
            fill=(217, 119, 87),
            width=max(2, int(height * 0.004)),
        )
        y += int(height * 0.035)
        sub_width = draw.textlength(subtitle, font=subtitle_font)
        draw.text(((width - sub_width) / 2, y), subtitle, font=subtitle_font, fill=(226, 214, 196))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    card.convert("RGB").save(out_path)
    return out_path


def build_card_clip(
    image: Path,
    duration: float,
    out_path: Path,
    size: str = "1920x1080",
    music_file: Path | None = None,
    music_volume: float = 0.18,
    music_offset: float = 0.0,
    motion: bool = True,
) -> Path:
    width, height = (int(p) for p in size.split("x"))
    fade = min(0.8, duration / 3)

    zoom = (
        f"zoompan=z='min(zoom+0.0008,1.08)':d={int(duration * 25)}:s={width}x{height}:fps=25,"
        if motion
        else ""
    )
    video_filter = (
        f"scale={width}:{height},"
        f"{zoom}"
        f"fade=t=in:st=0:d={fade},fade=t=out:st={duration - fade}:d={fade},format=yuv420p"
    )

    command = [FFMPEG_BIN, "-y", "-v", "error", "-loop", "1", "-t", f"{duration}", "-i", str(image)]

    if music_file and music_file.exists() and music_volume > 0:
        command += ["-ss", f"{music_offset}", "-t", f"{duration}", "-i", str(music_file)]
        audio_filter = (
            f"volume={music_volume},afade=t=in:st=0:d={fade},afade=t=out:st={duration - fade}:d={fade}"
        )
    else:
        command += ["-f", "lavfi", "-t", f"{duration}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        audio_filter = "anull"

    command += [
        "-filter_complex", f"[0:v]{video_filter}[v];[1:a]{audio_filter}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", "25",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(out_path),
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True, capture_output=True, stdin=subprocess.DEVNULL)
    return out_path


def concat_clips(clips: list[Path], out_path: Path, size: str = "1920x1080") -> Path:
    """Join finished clips that may differ in encoding, by re-encoding through the concat filter."""
    width, height = (int(p) for p in size.split("x"))

    command = [FFMPEG_BIN, "-y", "-v", "error"]
    for clip in clips:
        command += ["-i", str(clip)]

    parts = []
    for index in range(len(clips)):
        parts.append(
            f"[{index}:v]scale={width}:{height},setsar=1,fps=25[v{index}];"
            f"[{index}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{index}]"
        )
    streams = "".join(f"[v{i}][a{i}]" for i in range(len(clips)))
    filter_complex = ";".join(parts) + f";{streams}concat=n={len(clips)}:v=1:a=1[v][a]"

    command += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]

    subprocess.run(command, check=True, capture_output=True, stdin=subprocess.DEVNULL)
    return out_path
