"""Turn a few lines of poetry into a vertical video ready for Instagram."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

try:  # iPhone photos are HEIC by default, which Pillow cannot read on its own.
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover - HEIC uploads are simply rejected instead
    pass

from . import config
from .assemble import add_background_ambience, get_audio_duration, mux_audio_video
from .bookends import build_card_clip
from .image_gen import generate_image
from .tts import generate_voice_over

ProgressCallback = Callable[[str, str], None]

MIN_REEL_SECONDS = 4.0
MAX_REEL_SECONDS = 60.0
MAX_POEM_CHARS = 600
MAX_POEM_LINES = 12
MIN_BACKGROUND_EDGE = 400
MAX_ZOOM = 3.0
VOICE_LEAD_IN = 0.9
VOICE_LEAD_OUT = 1.6

# edge-tts is free and has a real Urdu (Pakistan) voice, which the local models lack.
POEM_VOICES = {
    "urdu": "ur-PK-AsadNeural",
    "hindi": "hi-IN-MadhurNeural",
    "hinglish": "hi-IN-MadhurNeural",
    "english": "en-IN-PrabhatNeural",
    "bengali": "bn-IN-BashkarNeural",
    "punjabi": "hi-IN-MadhurNeural",
}
DEFAULT_POEM_VOICE = "en-IN-PrabhatNeural"


def default_poem_voice(language: str) -> str:
    return POEM_VOICES.get(language.strip().lower(), DEFAULT_POEM_VOICE)
FALLBACK_HASHTAGS = (
    "#poetry #shayari #poem #poetrycommunity #writersofinstagram "
    "#poetsofinstagram #words #verse #spokenword #lines"
)

DEVANAGARI_FONTS = [
    "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
    "/System/Library/Fonts/Supplemental/Kohinoor.ttc",
]
# Nastaliq is the script Urdu poetry is traditionally set in. Geeza Pro is
# deliberately absent: FreeType cannot open it, which silently falls through to a
# font with no Urdu glyphs and renders empty boxes.
ARABIC_FONTS = [
    "/System/Library/Fonts/NotoNastaliq.ttc",
    "/System/Library/Fonts/SFArabic.ttf",
    "/System/Library/Fonts/Supplemental/Al Nile.ttc",
]
LATIN_FONTS = [
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
# Nastaliq slopes steeply and has deep descenders, so it needs more room per line.
LINE_SPACING = {"arabic": 2.05, "devanagari": 1.62, "latin": 1.5}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "mood": {"type": "string"},
        "image_prompt": {"type": "string"},
        "palette": {"type": "string"},
        "caption": {"type": "string"},
        "hashtags": {"type": "string"},
    },
    "required": ["mood", "image_prompt", "palette", "caption", "hashtags"],
}


@dataclass
class PoemOptions:
    style: str = "cinematic atmospheric photography, painterly, muted tones"
    language: str = "Hindi"
    size: str = "1080x1920"
    seconds_per_line: float = 2.6
    music_file: Optional[Path] = None
    music_volume: float = 0.35
    handle: str = ""
    seed: int = 0
    force_image: bool = False
    background_file: Optional[Path] = None
    focus_x: float = 0.5
    focus_y: float = 0.5
    zoom: float = 1.0
    narrate: bool = False
    voice: str = ""


@dataclass
class PoemResult:
    name: str
    out_dir: Path
    video_path: Path
    card_path: Path
    background_path: Path
    caption: str
    hashtags: str
    mood: str
    duration: float
    lines: list[str] = field(default_factory=list)


class PoemError(ValueError):
    """Raised when the poem itself cannot be turned into a post."""


def _script_of(text: str) -> str:
    if re.search(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF]", text):
        return "arabic"
    if re.search(r"[\u0900-\u097F]", text):
        return "devanagari"
    return "latin"


def _font_candidates(script: str) -> list[str]:
    if script == "arabic":
        return ARABIC_FONTS + DEVANAGARI_FONTS + LATIN_FONTS
    if script == "devanagari":
        return DEVANAGARI_FONTS + LATIN_FONTS
    return LATIN_FONTS + DEVANAGARI_FONTS


# A codepoint in the Private Use Area is absent from every real font, so whatever
# it renders as IS that font's .notdef box. Any glyph matching it is missing.
NOTDEF_PROBE = "\ue000"


def _glyph_signature(font: ImageFont.FreeTypeFont, char: str) -> tuple:
    mask = font.getmask(char)
    return (mask.size, bytes(mask) if mask.size[0] else b"")


def _covers(font: ImageFont.FreeTypeFont, text: str) -> bool:
    try:
        notdef = _glyph_signature(font, NOTDEF_PROBE)
    except OSError:
        return False
    for char in set(text):
        if char.isspace():
            continue
        try:
            # A missing glyph still has a bounding box, so compare shapes not emptiness.
            if _glyph_signature(font, char) == notdef:
                return False
        except OSError:
            return False
    return True


def _load_font(script: str, size: int, text: str = "") -> ImageFont.FreeTypeFont:
    """First font that both opens and can draw every character, so nothing renders as a box."""
    fallback: Optional[ImageFont.FreeTypeFont] = None
    for path in _font_candidates(script):
        if not Path(path).exists():
            continue
        try:
            font = ImageFont.truetype(path, size)
        except OSError:
            continue
        if not text or _covers(font, text):
            return font
        fallback = fallback or font
    return fallback or ImageFont.load_default(size)


def clean_poem(poem_text: str) -> list[str]:
    """Normalise pasted poetry into display lines, keeping the poet's own line breaks."""
    if not poem_text or not poem_text.strip():
        raise PoemError("Write a line or two of poetry first.")

    text = poem_text.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > MAX_POEM_CHARS:
        raise PoemError(
            f"That is {len(text)} characters. Keep it under {MAX_POEM_CHARS} so the words stay readable on the image."
        )

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        raise PoemError("Write a line or two of poetry first.")
    if len(lines) > MAX_POEM_LINES:
        raise PoemError(
            f"That is {len(lines)} lines. Keep it to {MAX_POEM_LINES} or fewer so every line fits on one screen."
        )
    return lines


def plan_poem(poem_text: str, options: PoemOptions) -> dict:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it in Settings.")

    template_path = config.PROMPTS_DIR / "poem_planning.txt"
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")

    prompt = (
        template_path.read_text(encoding="utf-8")
        .replace("{{STYLE}}", options.style)
        .replace("{{LANGUAGE}}", options.language)
        .replace("{{POEM_TEXT}}", poem_text)
    )

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    )
    return json.loads(response.text)


def undrawable_characters(text: str) -> list[str]:
    """Characters no available font can draw; they would show up as empty boxes."""
    script = _script_of(text)
    fonts = []
    for path in _font_candidates(script):
        if not Path(path).exists():
            continue
        try:
            fonts.append(ImageFont.truetype(path, 48))
        except OSError:
            continue
    if not fonts:
        return []

    missing = []
    for char in dict.fromkeys(text):
        if char.isspace() or not char.isprintable():
            continue
        if not any(_covers(font, char) for font in fonts):
            missing.append(char)
    return missing


def strip_undrawable(lines: list[str]) -> list[str]:
    """Drop characters no font can draw, so emoji never land on the card as boxes."""
    missing = set(undrawable_characters(" ".join(lines)))
    if not missing:
        return lines
    cleaned = []
    for line in lines:
        text = re.sub(r"\s{2,}", " ", "".join(c for c in line if c not in missing)).strip()
        if text:
            cleaned.append(text)
    return cleaned or lines


def load_photo(source: Path) -> Image.Image:
    """Open any supported photo upright, flattened and in RGB."""
    try:
        image = Image.open(source)
        image.load()
    except Exception as exc:  # noqa: BLE001
        raise PoemError("That image could not be read. Try a JPG or PNG.") from exc

    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        # Dropping alpha alone leaves whatever colour hid under it, so flatten on dark.
        backdrop = Image.new("RGBA", image.size, (18, 16, 14, 255))
        image = Image.alpha_composite(backdrop, image.convert("RGBA"))
    return image.convert("RGB")


def prepare_background(
    source: Path,
    out_path: Path,
    size: str,
    focus_x: float = 0.5,
    focus_y: float = 0.5,
    zoom: float = 1.0,
) -> Path:
    """Fit a photo to the frame, keeping the part of it the user framed."""
    width, height = (int(p) for p in size.split("x"))
    image = load_photo(source)

    if image.width < MIN_BACKGROUND_EDGE or image.height < MIN_BACKGROUND_EDGE:
        raise PoemError(
            f"That image is only {image.width}x{image.height}. "
            f"Use one at least {MIN_BACKGROUND_EDGE}px on each side or it will look blurry."
        )

    zoom = min(MAX_ZOOM, max(1.0, zoom))
    focus_x = min(1.0, max(0.0, focus_x))
    focus_y = min(1.0, max(0.0, focus_y))

    scale = max(width / image.width, height / image.height) * zoom
    resized = image.resize(
        (max(width, round(image.width * scale)), max(height, round(image.height * scale))),
        Image.LANCZOS,
    )

    left = round((resized.width - width) * focus_x)
    top = round((resized.height - height) * focus_y)
    cropped = resized.crop((left, top, left + width, top + height))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out_path)
    return out_path


def _pad_voice(source: Path, out_path: Path, lead_in: float, total: float) -> Path:
    """Delay the narration so it does not start on frame one, and run it to the full length."""
    delay_ms = int(lead_in * 1000)
    subprocess.run(
        [
            config.FFMPEG_BIN, "-y", "-v", "error",
            "-i", str(source),
            "-af", f"adelay={delay_ms}|{delay_ms},apad=whole_dur={total:.3f}",
            "-c:a", "aac",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    return out_path


def _fallback_plan(lines: list[str]) -> dict:
    return {
        "mood": "",
        "image_prompt": "",
        "palette": "",
        "caption": "\n".join(lines),
        "hashtags": FALLBACK_HASHTAGS,
    }


def _wrap_line(draw: ImageDraw.ImageDraw, line: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if draw.textlength(line, font=font) <= max_width:
        return [line]

    wrapped: list[str] = []
    current = ""
    for word in line.split(" "):
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            wrapped.append(current)
            current = word
    if current:
        wrapped.append(current)

    # A single word can still be wider than the frame, so break it by characters.
    broken: list[str] = []
    for piece in wrapped:
        while draw.textlength(piece, font=font) > max_width and len(piece) > 1:
            cut = len(piece) - 1
            while cut > 1 and draw.textlength(piece[:cut], font=font) > max_width:
                cut -= 1
            broken.append(piece[:cut])
            piece = piece[cut:]
        broken.append(piece)
    return broken


def _layout(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    script: str,
    width: int,
    height: int,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Largest font size that still fits, preferring to keep the poet's own line breaks."""
    max_text_width = int(width * 0.80)
    max_text_height = int(height * 0.52)
    spacing = LINE_SPACING.get(script, 1.6)
    sample = " ".join(lines)
    sizes = range(int(height * 0.055), int(height * 0.016), -2)

    # Pass one: no wrapping at all. Breaking a verse mid-line destroys its metre.
    for size in sizes:
        font = _load_font(script, size, sample)
        line_height = int(size * spacing)
        if line_height * len(lines) > max_text_height:
            continue
        if all(draw.textlength(line, font=font) <= max_text_width for line in lines):
            return font, list(lines), line_height

    # Pass two: a line is too long to ever fit, so wrapping is unavoidable.
    for size in sizes:
        font = _load_font(script, size, sample)
        rendered: list[str] = []
        for line in lines:
            rendered.extend(_wrap_line(draw, line, font, max_text_width))
        line_height = int(size * spacing)
        if line_height * len(rendered) <= max_text_height:
            return font, rendered, line_height

    size = int(height * 0.016)
    font = _load_font(script, size, sample)
    rendered = []
    for line in lines:
        rendered.extend(_wrap_line(draw, line, font, max_text_width))
    return font, rendered, int(size * spacing)


def render_poem_card(
    background: Path,
    lines: list[str],
    out_path: Path,
    size: str = "1080x1920",
    handle: str = "",
) -> Path:
    width, height = (int(p) for p in size.split("x"))

    base = Image.open(background).convert("RGB")
    scale = max(width / base.width, height / base.height)
    base = base.resize((round(base.width * scale), round(base.height * scale)), Image.LANCZOS)
    left = (base.width - width) // 2
    top = (base.height - height) // 2
    base = base.crop((left, top, left + width, top + height))
    base = base.filter(ImageFilter.GaussianBlur(width * 0.005))

    canvas = base.convert("RGBA")
    lines = strip_undrawable(lines)
    script = _script_of(" ".join(lines))
    measure = ImageDraw.Draw(canvas)
    font, rendered, line_height = _layout(measure, lines, script, width, height)

    block_height = line_height * len(rendered)
    block_top = (height - block_height) / 2

    # A soft band behind the text keeps it legible whatever the image does underneath.
    scrim = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    scrim_draw = ImageDraw.Draw(scrim)
    band_top = int(block_top - height * 0.10)
    band_bottom = int(block_top + block_height + height * 0.10)
    scrim_draw.rectangle([0, band_top, width, band_bottom], fill=(14, 12, 11, 165))
    scrim = scrim.filter(ImageFilter.GaussianBlur(width * 0.06))
    canvas = Image.alpha_composite(canvas, scrim)
    canvas = Image.alpha_composite(canvas, Image.new("RGBA", (width, height), (14, 12, 11, 60)))

    draw = ImageDraw.Draw(canvas)
    y = block_top
    for line in rendered:
        text_width = draw.textlength(line, font=font)
        x = (width - text_width) / 2
        draw.text((x + 2, y + 3), line, font=font, fill=(0, 0, 0, 150))
        draw.text((x, y), line, font=font, fill=(250, 247, 240))
        y += line_height

    rule_width = int(width * 0.12)
    rule_y = int(block_top + block_height + height * 0.035)
    draw.line(
        [((width - rule_width) / 2, rule_y), ((width + rule_width) / 2, rule_y)],
        fill=(217, 119, 87),
        width=max(2, int(height * 0.002)),
    )

    if handle:
        handle_font = _load_font("latin", int(height * 0.020), handle)
        handle_width = draw.textlength(handle, font=handle_font)
        draw.text(
            ((width - handle_width) / 2, rule_y + height * 0.028),
            handle,
            font=handle_font,
            fill=(226, 214, 196),
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, quality=95)
    return out_path


def generate_poem_reel(
    poem_text: str,
    name: str,
    options: PoemOptions,
    on_progress: Optional[ProgressCallback] = None,
) -> PoemResult:
    def report(stage: str, message: str) -> None:
        if on_progress:
            on_progress(stage, message)

    lines = clean_poem(poem_text)
    width, height = (int(p) for p in options.size.split("x"))

    out_dir = config.OUTPUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "poem.txt").write_text("\n".join(lines), encoding="utf-8")

    own_image = options.background_file is not None
    report("planning", "Writing the caption…" if own_image else "Reading the poem and designing the image…")
    try:
        plan = plan_poem("\n".join(lines), options)
    except Exception as exc:  # noqa: BLE001
        # With a supplied image there is still a whole reel to make, so carry on without Gemini.
        if not own_image:
            raise
        report("planning", f"Caption skipped ({type(exc).__name__}); using the poem as the caption")
        plan = _fallback_plan(lines)
    (out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    background = out_dir / "background.png"
    if own_image:
        report("image", "Fitting your image to the frame…")
        prepare_background(
            options.background_file,
            background,
            options.size,
            options.focus_x,
            options.focus_y,
            options.zoom,
        )
    elif background.exists() and not options.force_image:
        report("image", "Reusing the existing background image")
    else:
        report("image", f"Painting the background ({plan['mood']})…")
        generate_image(
            plan["image_prompt"],
            background,
            seed=options.seed,
            width=width,
            height=height,
        )

    report("typography", "Writing the poem onto the image…")
    card = render_poem_card(background, lines, out_dir / "card.png", options.size, options.handle)

    video_path = out_dir / "reel.mp4"
    voice_path: Optional[Path] = None
    if options.narrate:
        voice = options.voice or default_poem_voice(options.language)
        report("voice", f"Reading the poem aloud ({voice})…")
        voice_path = out_dir / "voice.mp3"
        generate_voice_over("\n".join(lines), voice, voice_path)
        spoken = get_audio_duration(voice_path)
        duration = min(MAX_REEL_SECONDS, max(MIN_REEL_SECONDS, spoken + VOICE_LEAD_IN + VOICE_LEAD_OUT))
    else:
        duration = min(MAX_REEL_SECONDS, max(MIN_REEL_SECONDS, len(lines) * options.seconds_per_line))

    report("video", f"Building a {duration:.0f}s reel…")
    if voice_path is not None:
        padded = _pad_voice(voice_path, out_dir / "voice_padded.m4a", VOICE_LEAD_IN, duration)
        mixed = out_dir / "reel_audio.m4a"
        add_background_ambience(
            padded,
            mixed,
            duration,
            ambience_volume=0.0,
            music_volume=options.music_volume,
            music_file=options.music_file,
        )
        silent = out_dir / "reel_silent.mp4"
        build_card_clip(card, duration, silent, size=options.size, music_volume=0, motion=False)
        mux_audio_video(silent, mixed, video_path)
    else:
        build_card_clip(
            card,
            duration,
            video_path,
            size=options.size,
            music_file=options.music_file,
            music_volume=options.music_volume,
            motion=False,
        )

    caption = plan["caption"].strip()
    hashtags = " ".join(dict.fromkeys(plan["hashtags"].split())).strip()
    (out_dir / "caption.txt").write_text(f"{caption}\n\n{hashtags}\n", encoding="utf-8")

    meta = {
        "kind": "poem",
        "name": name,
        "mood": plan["mood"],
        "palette": plan.get("palette", ""),
        "language": options.language,
        "style": "" if own_image else options.style,
        "size": options.size,
        "duration_seconds": round(duration, 1),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "own_image": own_image,
        "narrated": bool(options.narrate),
        "voice": (options.voice or default_poem_voice(options.language)) if options.narrate else "",
        "music_file": str(options.music_file) if options.music_file else "",
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    report("done", "Reel ready")
    return PoemResult(
        name=name,
        out_dir=out_dir,
        video_path=video_path,
        card_path=card,
        background_path=background,
        caption=caption,
        hashtags=hashtags,
        mood=plan["mood"],
        duration=duration,
        lines=lines,
    )
