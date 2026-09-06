"""Turn a few lines of poetry into a vertical video ready for Instagram."""

from __future__ import annotations

import json
import re
import shutil
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
from .bookends import build_card_clip, concat_clips
from .image_gen import generate_image
from .tts import generate_voice_over
from .tts_elevenlabs import generate_voice_over_elevenlabs

ProgressCallback = Callable[[str, str], None]

MIN_REEL_SECONDS = 4.0
MAX_REEL_SECONDS = 60.0
MAX_POEM_CHARS = 600
MAX_POEM_LINES = 12
MIN_BACKGROUND_EDGE = 400
MAX_ZOOM = 3.0
VOICE_LEAD_IN = 0.9
VOICE_LEAD_OUT = 1.6

# A poem is carried by pace and silence, not by the voice alone. Reciting slows the
# reader down, drops the pitch, and leaves a real gap where the line break is.
DELIVERY = {
    "natural": {"rate": "+0%", "pitch": "+0Hz", "pause": 0.0, "speed": 1.0, "style": 0.30},
    "recitation": {"rate": "-18%", "pitch": "-4Hz", "pause": 0.85, "speed": 0.88, "style": 0.45},
    "slow": {"rate": "-32%", "pitch": "-6Hz", "pause": 1.30, "speed": 0.75, "style": 0.55},
}
DEFAULT_DELIVERY = "recitation"

# Pre-rendered backgrounds paired with a fitting track, so a reel needs no image-gen wait at
# all: pick or shuffle a template, write the poem, done. Backgrounds live in assets/poem_templates/
# and are served through the existing /assets static mount.
POEM_TEMPLATES = [
    {"id": "rain_dusk", "label": "Rain & Dusk", "music": "jaani-door-gaye.mp3"},
    {"id": "desert_night", "label": "Desert Night", "music": "arabic_desert_oud.mp3"},
    {"id": "old_delhi", "label": "Old Delhi Lane", "music": "bineleyas-indian-classical-flute-amp-tabla-mystcial-fusion-149963.mp3"},
    {"id": "misty_hills", "label": "Misty Hills", "music": "piano_gentle.mp3"},
    {"id": "empty_room", "label": "Empty Room", "music": "piano_emotional.mp3"},
    {"id": "ocean_dark", "label": "Ocean Dark", "music": "ambient_documentary.mp3"},
    {"id": "candlelight", "label": "Candlelight", "music": "piano_emotional.mp3"},
    {"id": "snowfall", "label": "Snowfall Window", "music": "piano_gentle.mp3"},
    {"id": "autumn_path", "label": "Autumn Path", "music": "cinematic_calm.mp3"},
    {"id": "rooftop_night", "label": "Rooftop Night", "music": "cinematic_drama.mp3"},
    {"id": "library", "label": "Old Library", "music": "ambient_reflective.mp3"},
    {"id": "train_window", "label": "Train Window", "music": "cinematic_wonder.mp3"},
    {"id": "courtyard", "label": "Moonlit Courtyard", "music": "indian_sitar_calm.mp3"},
    {"id": "village_well", "label": "Village Well", "music": "indian_traditional.mp3"},
    {"id": "mountain_sunrise", "label": "Mountain Sunrise", "music": "cinematic_uplift.mp3"},
    {"id": "old_letters", "label": "Old Letters", "music": "piano_emotional.mp3"},
    {"id": "empty_swing", "label": "Empty Swing", "music": "woh_tera_pyar.mp3"},
    {"id": "riverbank", "label": "Riverbank Dusk", "music": "naulo_suruwat.mp3"},
    {"id": "bazaar_lanterns", "label": "Bazaar Lanterns", "music": "indian_traditional.mp3"},
    {"id": "stormy_sky", "label": "Stormy Sky", "music": "cinematic_tension.mp3"},
]
POEM_TEMPLATES_DIR = Path("assets/poem_templates")

# An optional small "attributed to" tag for when you are sharing someone else's poem,
# not your own - a portrait plus name credited near the top, same idea as a printed
# quote card crediting its author. Off by default; add more poets by adding an entry
# and dropping a square portrait into assets/poets/.
POET_AVATARS = [
    {"id": "jaun_elia", "label": "Jaun Elia", "file": "jaun_elia_avatar.png"},
]
POET_AVATARS_DIR = Path("assets/poets")

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
    "#quotes #quoteoftheday #reels #instareels #wordsofwisdom "
    "#deepthoughts #thoughtoftheday #shortvideo #shareit #instagood"
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

# Apple Color Emoji is a bitmap ("sbix") font that only opens at these fixed strike
# sizes - anything else throws "invalid pixel size". We load the closest one at or
# above what we need and downscale the glyph, rather than trying arbitrary sizes.
EMOJI_FONT_PATH = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_STRIKE_SIZES = [20, 32, 40, 48, 64, 96, 160]
EMOJI_FONT_AVAILABLE = Path(EMOJI_FONT_PATH).is_file()

_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x1F1E6, 0x1F1FF),
    (0x2190, 0x21FF),
    (0x2B00, 0x2BFF),
    (0x1F000, 0x1F0FF),
    (0x2300, 0x23FF),
    (0xFE0F, 0xFE0F),
    (0x200D, 0x200D),
)


def _is_emoji_char(char: str) -> bool:
    if not EMOJI_FONT_AVAILABLE:
        return False
    code = ord(char)
    return any(lo <= code <= hi for lo, hi in _EMOJI_RANGES)


def _split_emoji_runs(line: str) -> list[tuple[str, bool]]:
    """Split a line into (text, is_emoji) runs, keeping their order."""
    runs: list[tuple[str, bool]] = []
    current = ""
    current_is_emoji = False
    for char in line:
        is_emoji = _is_emoji_char(char)
        if current and is_emoji != current_is_emoji:
            runs.append((current, current_is_emoji))
            current = ""
        current += char
        current_is_emoji = is_emoji
    if current:
        runs.append((current, current_is_emoji))
    return runs


_emoji_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _load_emoji_font(target_size: int) -> tuple[ImageFont.FreeTypeFont, int]:
    strike = next((s for s in EMOJI_STRIKE_SIZES if s >= target_size), EMOJI_STRIKE_SIZES[-1])
    if strike not in _emoji_font_cache:
        _emoji_font_cache[strike] = ImageFont.truetype(EMOJI_FONT_PATH, strike)
    return _emoji_font_cache[strike], strike


_emoji_render_cache: dict[tuple[str, int], Image.Image] = {}


def _render_emoji_run(text: str, target_size: int) -> Image.Image:
    """A small RGBA image of this emoji run, scaled to sit at the same visual height as
    the surrounding text."""
    cache_key = (text, target_size)
    if cache_key in _emoji_render_cache:
        return _emoji_render_cache[cache_key]

    font, strike = _load_emoji_font(target_size)
    pad = strike // 2
    canvas_size = (strike * max(1, len(text)) + pad * 2, strike + pad * 2)
    tmp = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((pad, pad), text, font=font, embedded_color=True)
    bbox = tmp.getbbox()
    tmp = tmp.crop(bbox) if bbox else Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    if strike != target_size and tmp.width > 1:
        scale = target_size / strike
        new_size = (max(1, round(tmp.width * scale)), max(1, round(tmp.height * scale)))
        tmp = tmp.resize(new_size, Image.LANCZOS)
    _emoji_render_cache[cache_key] = tmp
    return tmp


def _measure_line_width(draw: ImageDraw.ImageDraw, line: str, font: ImageFont.FreeTypeFont, emoji_size: int) -> float:
    """Width of a line that may mix ordinary text with emoji, which the text font can't draw."""
    if not any(_is_emoji_char(c) for c in line):
        return draw.textlength(line, font=font)
    total = 0.0
    for text, is_emoji in _split_emoji_runs(line):
        total += _render_emoji_run(text, emoji_size).width if is_emoji else draw.textlength(text, font=font)
    return total


def _draw_mixed_line(
    draw: ImageDraw.ImageDraw, canvas: Image.Image, x: float, y: float, line: str,
    font: ImageFont.FreeTypeFont, emoji_size: int, fill: tuple, shadow: bool,
) -> None:
    """Draw a line that may mix ordinary text with emoji glyphs pasted in inline."""
    if not any(_is_emoji_char(c) for c in line):
        if shadow:
            draw.text((x + 2, y + 3), line, font=font, fill=(0, 0, 0, 150))
        draw.text((x, y), line, font=font, fill=fill)
        return

    cursor = x
    for text, is_emoji in _split_emoji_runs(line):
        if is_emoji:
            glyph = _render_emoji_run(text, emoji_size)
            paste_y = int(y + (emoji_size - glyph.height) * 0.5)
            canvas.paste(glyph, (int(cursor), paste_y), glyph)
            cursor += glyph.width
        else:
            if shadow:
                draw.text((cursor + 2, y + 3), text, font=font, fill=(0, 0, 0, 150))
            draw.text((cursor, y), text, font=font, fill=fill)
            cursor += draw.textlength(text, font=font)


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
    delivery: str = DEFAULT_DELIVERY
    voice_provider: str = "edge"
    text_scale: float = 1.0
    avatar_id: str = ""
    lines_per_segment: int = 0
    transition: str = "cut"
    transition_seconds: float = 0.5


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
    """Characters no available font can draw; they would show up as empty boxes.
    Emoji are handled by their own dedicated font path, so they are never flagged here."""
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
        if char.isspace() or not char.isprintable() or _is_emoji_char(char):
            continue
        if not any(_covers(font, char) for font in fonts):
            missing.append(char)
    return missing


def strip_undrawable(lines: list[str]) -> list[str]:
    """Drop characters no font can draw, so unsupported glyphs never land on the card as
    boxes - emoji are kept, they are drawn through a separate colour font."""
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


def _recite(
    lines: list[str],
    voice: str,
    out_dir: Path,
    out_path: Path,
    delivery: str,
    provider: str = "edge",
    language: str = "English",
) -> tuple[Path, list[tuple[float, float]]]:
    """Read the poem a line at a time so the line breaks are audible as silence.

    Also returns each spoken line's (start, end) time within out_path, so the on-screen
    text can be synced to when it is actually being read rather than shown all at once.
    """
    settings = DELIVERY.get(delivery, DELIVERY[DEFAULT_DELIVERY])
    pause = settings["pause"]
    spoken = [line for line in lines if line.strip()]

    def synthesise(text: str, path: Path) -> None:
        if provider == "elevenlabs":
            generate_voice_over_elevenlabs(
                text, voice, path, language=language,
                style=settings["style"], speed=settings["speed"],
            )
        else:
            generate_voice_over(text, voice, path, rate=settings["rate"], pitch=settings["pitch"])

    if not pause or len(spoken) < 2:
        synthesise("\n".join(spoken), out_path)
        # No per-line audio to measure, so split the one recording by character count -
        # the same estimate used for word-level captions elsewhere in the app.
        total = get_audio_duration(out_path)
        weights = [max(len(line), 1) for line in spoken] or [1]
        total_weight = sum(weights)
        timings = []
        cursor = 0.0
        for weight in weights:
            share = total * (weight / total_weight)
            timings.append((cursor, cursor + share))
            cursor += share
        return out_path, timings

    parts_dir = out_dir / "voice_lines"
    parts_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for index, line in enumerate(spoken):
        part = parts_dir / f"line_{index:02d}.mp3"
        synthesise(line, part)
        parts.append(part)

    timings: list[tuple[float, float]] = []
    cursor = 0.0
    for part in parts:
        line_duration = get_audio_duration(part)
        timings.append((cursor, cursor + line_duration))
        cursor += line_duration + pause

    command = [config.FFMPEG_BIN, "-y", "-v", "error"]
    for part in parts:
        command += ["-i", str(part)]
    # Pad every line but the last, so the reel does not end on a hanging silence.
    pads = "".join(
        f"[{i}:a]apad=pad_dur={pause:.2f}[p{i}];" if i < len(parts) - 1 else f"[{i}:a]anull[p{i}];"
        for i in range(len(parts))
    )
    chain = "".join(f"[p{i}]" for i in range(len(parts)))
    command += [
        "-filter_complex", f"{pads}{chain}concat=n={len(parts)}:v=0:a=1[out]",
        "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2",
        str(out_path),
    ]
    subprocess.run(command, check=True, capture_output=True, stdin=subprocess.DEVNULL)
    return out_path, timings


def _fallback_plan(lines: list[str]) -> dict:
    return {
        "mood": "",
        "image_prompt": "",
        "palette": "",
        "caption": "\n".join(lines),
        "hashtags": FALLBACK_HASHTAGS,
    }


def _wrap_line(draw: ImageDraw.ImageDraw, line: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    emoji_size = font.size
    if _measure_line_width(draw, line, font, emoji_size) <= max_width:
        return [line]

    wrapped: list[str] = []
    current = ""
    for word in line.split(" "):
        candidate = f"{current} {word}".strip()
        if _measure_line_width(draw, candidate, font, emoji_size) <= max_width or not current:
            current = candidate
        else:
            wrapped.append(current)
            current = word
    if current:
        wrapped.append(current)

    # A single word can still be wider than the frame, so break it by characters.
    broken: list[str] = []
    for piece in wrapped:
        while _measure_line_width(draw, piece, font, emoji_size) > max_width and len(piece) > 1:
            cut = len(piece) - 1
            while cut > 1 and _measure_line_width(draw, piece[:cut], font, emoji_size) > max_width:
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
    text_scale: float = 1.0,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Largest font size that still fits, preferring to keep the poet's own line breaks.

    text_scale then nudges that auto-fit result bigger or smaller. It has to act on the
    *result*, not the search range: for a long line, width is what actually caps the size,
    so widening the search range alone changes nothing - the widest-fitting size wins either
    way. Scaling it up re-wraps at the new size instead, even if that means more lines.
    """
    max_text_width = int(width * 0.80)
    max_text_height = int(height * 0.52)
    spacing = LINE_SPACING.get(script, 1.6)
    full_sample = " ".join(lines)
    sample = "".join(c for c in full_sample if not _is_emoji_char(c)) or full_sample
    sizes = range(int(height * 0.055), int(height * 0.016), -2)

    natural_size = None

    # Pass one: no wrapping at all. Breaking a verse mid-line destroys its metre.
    for size in sizes:
        font = _load_font(script, size, sample)
        line_height = int(size * spacing)
        if line_height * len(lines) > max_text_height:
            continue
        if all(_measure_line_width(draw, line, font, size) <= max_text_width for line in lines):
            natural_size = size
            break

    # Pass two: a line is too long to ever fit, so wrapping is unavoidable.
    if natural_size is None:
        for size in sizes:
            font = _load_font(script, size, sample)
            rendered: list[str] = []
            for line in lines:
                rendered.extend(_wrap_line(draw, line, font, max_text_width))
            line_height = int(size * spacing)
            if line_height * len(rendered) <= max_text_height:
                natural_size = size
                break

    if natural_size is None:
        natural_size = int(height * 0.016)

    final_size = natural_size if text_scale == 1.0 else max(6, min(int(height * 0.09), round(natural_size * text_scale)))
    font = _load_font(script, final_size, sample)
    rendered = []
    for line in lines:
        rendered.extend(_wrap_line(draw, line, font, max_text_width))
    return font, rendered, int(final_size * spacing)


def _draw_poet_credit(
    canvas: Image.Image, avatar_file: Path, poet_name: str, left_x: float, bottom_y: float, width: int, height: int
) -> Image.Image:
    """A small 'shared from' credit sitting just above the poem, starting from the same left
    edge the poem's own first line starts from - not centered, so it reads as a caption for
    the words below it rather than a banner. A soft pill keeps it legible over any image."""
    avatar_size = int(height * 0.052)
    portrait = Image.open(avatar_file).convert("RGBA").resize((avatar_size, avatar_size), Image.LANCZOS)

    label_font = _load_font("latin", int(height * 0.0105), "shared from")
    name_font = _load_font("latin", int(height * 0.019), poet_name)
    measure = ImageDraw.Draw(canvas)
    name_width = measure.textlength(poet_name, font=name_font)
    label_width = measure.textlength("shared from", font=label_font)
    text_width = max(name_width, label_width)

    gap = int(width * 0.025)
    total_width = avatar_size + gap + text_width
    pad_x, pad_y = int(width * 0.035), int(height * 0.014)

    x = min(left_x, width - total_width - pad_x)
    y = max(int(height * 0.035), int(bottom_y - avatar_size - pad_y * 2 - height * 0.02))

    pill_box = [x - pad_x, y - pad_y, x + total_width + pad_x, y + avatar_size + pad_y]
    pill = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle(pill_box, radius=int(height * 0.012), fill=(46, 42, 38, 130))
    canvas = Image.alpha_composite(canvas, pill.filter(ImageFilter.GaussianBlur(width * 0.002)))

    canvas.paste(portrait, (int(x), int(y)), portrait)
    draw = ImageDraw.Draw(canvas)
    text_x = x + avatar_size + gap
    draw.text((text_x, y - height * 0.004), "shared from", font=label_font, fill=(190, 178, 162))
    draw.text((text_x, y + avatar_size * 0.34), poet_name, font=name_font, fill=(250, 247, 240))
    return canvas


def render_poem_card(
    background: Path,
    lines: list[str],
    out_path: Path,
    size: str = "1080x1920",
    handle: str = "",
    text_scale: float = 1.0,
    avatar_file: Optional[Path] = None,
    poet_name: str = "",
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
    font, rendered, line_height = _layout(measure, lines, script, width, height, text_scale)

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
        text_width = _measure_line_width(draw, line, font, font.size)
        x = (width - text_width) / 2
        _draw_mixed_line(draw, canvas, x, y, line, font, font.size, (250, 247, 240), shadow=True)
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

    if avatar_file and poet_name and avatar_file.is_file():
        first_line = rendered[0] if rendered else ""
        first_line_width = _measure_line_width(draw, first_line, font, font.size)
        first_line_x = (width - first_line_width) / 2
        canvas = _draw_poet_credit(canvas, avatar_file, poet_name, first_line_x, block_top, width, height)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, quality=95)
    return out_path


def _segment_lines(lines: list[str], lines_per_segment: int) -> list[list[str]]:
    """Group lines into on-screen pages. 0 (or covering everything anyway) means one static page."""
    if lines_per_segment <= 0 or lines_per_segment >= len(lines):
        return [lines]
    return [lines[i:i + lines_per_segment] for i in range(0, len(lines), lines_per_segment)]


def _segment_windows(
    segments: list[list[str]],
    total_duration: float,
    line_timings: Optional[list[tuple[float, float]]],
    lead_in: float,
) -> list[tuple[float, float]]:
    """Each segment's (start, end) in the final video. Timed to speech when narrating,
    otherwise split in proportion to how many lines each segment shows."""
    windows: list[tuple[float, float]] = []
    if line_timings is not None:
        idx = 0
        for segment in segments:
            last_line = idx + len(segment) - 1
            start = 0.0 if not windows else windows[-1][1]
            end = lead_in + line_timings[min(last_line, len(line_timings) - 1)][1]
            windows.append((start, max(end, start + 0.6)))
            idx += len(segment)
    else:
        total_lines = sum(len(s) for s in segments) or 1
        cursor = 0.0
        for segment in segments:
            share = total_duration * (len(segment) / total_lines)
            windows.append((cursor, cursor + share))
            cursor += share
    windows[-1] = (windows[-1][0], total_duration)
    return windows


def _build_music_track(duration: float, out_path: Path, music_file: Optional[Path], music_volume: float) -> Path:
    """A continuous audio track for the whole reel, independent of how many on-screen
    segments it is split into - segments must not restart the music at each cut."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if music_file and music_file.exists() and music_volume > 0:
        fade = min(0.3, duration / 6)
        command = [
            config.FFMPEG_BIN, "-y", "-v", "error",
            "-stream_loop", "-1", "-t", f"{duration:.3f}", "-i", str(music_file),
            "-af", f"volume={music_volume},afade=t=in:st=0:d={fade:.2f},afade=t=out:st={max(duration - fade, 0):.2f}:d={fade:.2f}",
            "-c:a", "aac",
            str(out_path),
        ]
    else:
        command = [
            config.FFMPEG_BIN, "-y", "-v", "error",
            "-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:a", "aac",
            str(out_path),
        ]
    subprocess.run(command, check=True, capture_output=True, stdin=subprocess.DEVNULL)
    return out_path


def _concat_segments(
    clips: list[Path], durations: list[float], out_path: Path, size: str, transition: str, transition_seconds: float
) -> Path:
    """Join segment clips with a hard cut, or a crossfade if there is room for one."""
    if len(clips) == 1:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(clips[0], out_path)
        return out_path

    if transition != "fade":
        return concat_clips(clips, out_path, size)

    fade = min(transition_seconds, min(durations) / 2, 1.5)
    if fade <= 0.05:
        return concat_clips(clips, out_path, size)

    width, height = (int(p) for p in size.split("x"))
    command = [config.FFMPEG_BIN, "-y", "-v", "error"]
    for clip in clips:
        command += ["-i", str(clip)]

    parts = []
    for i in range(len(clips)):
        parts.append(f"[{i}:v]scale={width}:{height},setsar=1,fps=25[v{i}];")
        parts.append(f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}];")

    running = durations[0]
    prev_v, prev_a = "v0", "a0"
    for i in range(1, len(clips)):
        offset = max(0.0, running - fade)
        out_v, out_a = f"vx{i}", f"ax{i}"
        parts.append(f"[{prev_v}][v{i}]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f}[{out_v}];")
        parts.append(f"[{prev_a}][a{i}]acrossfade=d={fade:.3f}[{out_a}];")
        prev_v, prev_a = out_v, out_a
        running += durations[i] - fade

    command += [
        "-filter_complex", "".join(parts),
        "-map", f"[{prev_v}]", "-map", f"[{prev_a}]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(command, check=True, capture_output=True, stdin=subprocess.DEVNULL)
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
    avatar_file = None
    poet_name = ""
    if options.avatar_id:
        poet = next((p for p in POET_AVATARS if p["id"] == options.avatar_id), None)
        if poet:
            avatar_file = POET_AVATARS_DIR / poet["file"]
            poet_name = poet["label"]

    segments = _segment_lines(lines, options.lines_per_segment)

    video_path = out_dir / "reel.mp4"
    voice_path: Optional[Path] = None
    line_timings: Optional[list[tuple[float, float]]] = None
    if options.narrate:
        voice = options.voice or default_poem_voice(options.language)
        report("voice", f"Reading the poem aloud ({voice})…")
        voice_path = out_dir / "voice.mp3"
        voice_path, line_timings = _recite(
            lines, voice, out_dir, voice_path, options.delivery,
            provider=options.voice_provider, language=options.language,
        )
        spoken = get_audio_duration(voice_path)
        duration = min(MAX_REEL_SECONDS, max(MIN_REEL_SECONDS, spoken + VOICE_LEAD_IN + VOICE_LEAD_OUT))
    else:
        duration = min(MAX_REEL_SECONDS, max(MIN_REEL_SECONDS, len(lines) * options.seconds_per_line))

    windows = _segment_windows(segments, duration, line_timings, VOICE_LEAD_IN if options.narrate else 0.0)
    durations = [max(0.6, end - start) for start, end in windows]

    segments_dir = out_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    segment_clips: list[Path] = []
    for i, (segment_lines, segment_duration) in enumerate(zip(segments, durations)):
        segment_card = segments_dir / f"card_{i:02d}.png"
        render_poem_card(
            background, segment_lines, segment_card, options.size, options.handle, options.text_scale,
            avatar_file, poet_name,
        )
        if i == 0:
            # card.png is the thumbnail/first-frame reference other code expects to find.
            shutil.copyfile(segment_card, out_dir / "card.png")
            card = out_dir / "card.png"
        segment_clip = segments_dir / f"clip_{i:02d}.mp4"
        build_card_clip(segment_card, segment_duration, segment_clip, size=options.size, music_volume=0, motion=False, fade_edges=False)
        segment_clips.append(segment_clip)

    report("video", f"Building a {duration:.0f}s reel…")
    silent = out_dir / "reel_silent.mp4"
    _concat_segments(segment_clips, durations, silent, options.size, options.transition, options.transition_seconds)

    if voice_path is not None:
        padded = _pad_voice(voice_path, out_dir / "voice_padded.m4a", VOICE_LEAD_IN, duration)
        audio_track = out_dir / "reel_audio.m4a"
        add_background_ambience(
            padded,
            audio_track,
            duration,
            ambience_volume=0.0,
            music_volume=options.music_volume,
            music_file=options.music_file,
        )
    else:
        audio_track = _build_music_track(duration, out_dir / "reel_audio.m4a", options.music_file, options.music_volume)
    mux_audio_video(silent, audio_track, video_path)

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
