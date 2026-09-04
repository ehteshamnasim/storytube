import argparse
from datetime import datetime
from pathlib import Path

from . import config
from .poetry import PoemError, PoemOptions, generate_poem_reel


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Turn a few lines of poetry into a vertical video ready for Instagram."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="The poem itself, with \\n between lines")
    source.add_argument("--file", type=Path, help="Path to a .txt file containing the poem")

    parser.add_argument("--name", default="", help="Output folder name; defaults to a slug of the first line")
    parser.add_argument("--language", default="Hindi", help="Language the poem is written in")
    parser.add_argument(
        "--style",
        default="cinematic atmospheric photography, painterly, muted tones",
        help="Visual style for the background image",
    )
    parser.add_argument("--size", default="1080x1920", help="Frame size; 1080x1920 is the Reels shape")
    parser.add_argument("--music-file", type=Path, default=None, help="Background music track")
    parser.add_argument("--music-volume", type=float, default=0.35, help="Music level, 0 to 1")
    parser.add_argument("--handle", default="", help="Handle printed under the poem, e.g. @your.poetry")
    parser.add_argument("--seconds-per-line", type=float, default=2.6, help="Reel length per poem line")
    parser.add_argument("--seed", type=int, default=0, help="Image seed; change it for a different picture")
    parser.add_argument("--force-image", action="store_true", help="Redraw the background even if one exists")

    args = parser.parse_args()

    if args.file:
        if not args.file.exists():
            parser.error(f"No such file: {args.file}")
        poem_text = args.file.read_text(encoding="utf-8")
    else:
        poem_text = args.text.replace("\\n", "\n")

    name = args.name.strip() or _slug(poem_text)

    options = PoemOptions(
        style=args.style,
        language=args.language,
        size=args.size,
        seconds_per_line=args.seconds_per_line,
        music_file=args.music_file,
        music_volume=args.music_volume,
        handle=args.handle,
        seed=args.seed,
        force_image=args.force_image,
    )

    try:
        result = generate_poem_reel(poem_text, name, options, on_progress=lambda s, m: print(f"[{s}] {m}"))
    except PoemError as exc:
        parser.error(str(exc))

    print()
    print(f"Reel     {result.video_path}")
    print(f"Card     {result.card_path}")
    print(f"Caption  {result.out_dir / 'caption.txt'}")
    print(f"Mood     {result.mood}  ({result.duration:.0f}s)")


def _slug(poem_text: str) -> str:
    first = next((line for line in poem_text.splitlines() if line.strip()), "")
    kept = [c if (c.isalnum() and c.isascii()) or c in "-_" else "_" for c in first.strip()[:40]]
    slug = "".join(kept).strip("_").lower()
    # Devanagari, Nastaliq and friends leave nothing behind, so fall back to the time.
    base = f"poem_{slug}" if len(slug) >= 3 else f"poem_{datetime.now():%Y%m%d_%H%M%S}"
    name = base
    counter = 2
    while (config.OUTPUT_DIR / name).exists():
        name = f"{base}_{counter}"
        counter += 1
    return name
