"""Build one markdown report of every posted output's text, music and platform numbers.

Reads only what is already saved on disk (instagram.json / youtube.json / meta.json /
poem.txt / caption.txt / scenes.json) - no API calls, so it is instant and needs no keys.

Usage:
    python scripts/export_analytics.py
    python scripts/export_analytics.py --out output/_analysis/my_report.md
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from storytube import config  # noqa: E402


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def written_text(out_dir: Path) -> str:
    poem_file = out_dir / "poem.txt"
    if poem_file.is_file():
        return poem_file.read_text(encoding="utf-8").strip()

    caption_file = out_dir / "caption.txt"
    if caption_file.is_file():
        return caption_file.read_text(encoding="utf-8").strip()

    scenes = load_json(out_dir / "scenes.json")
    lines = [s.get("narration", "") for s in scenes.get("scenes", [])]
    return "\n".join(line for line in lines if line).strip()


def instagram_row(state: dict) -> str:
    stats = state.get("stats", {})
    link = state.get("permalink", "")
    label = f"[Reel]({link})" if link else "Reel"
    numbers = ", ".join(
        f"{k} {v}" for k, v in stats.items() if k not in ("likes", "views", "comments")
    )
    return (
        f"| Instagram | {label} | {stats.get('views', '—')} | {stats.get('likes', '—')} | "
        f"{stats.get('comments', '—')} | {numbers or '—'} |"
    )


def youtube_row(state: dict) -> str:
    stats = state.get("stats", {})
    analytics = state.get("analytics", {})
    link = state.get("url", "")
    title = state.get("title", "")
    label = f"[{title}]({link})" if link else title or "Short"
    views = stats.get("viewCount", analytics.get("views", "—"))
    likes = stats.get("likeCount", analytics.get("likes", "—"))
    comments = stats.get("commentCount", analytics.get("comments", "—"))
    extra = []
    if analytics.get("estimatedMinutesWatched") is not None:
        extra.append(f"{analytics['estimatedMinutesWatched']} min watched")
    if analytics.get("averageViewDuration") is not None:
        extra.append(f"avg view {analytics['averageViewDuration']}s")
    return f"| YouTube | {label} | {views} | {likes} | {comments} | {', '.join(extra) or '—'} |"


def build_report(output_dir: Path) -> str:
    posted_dirs = sorted(
        d for d in output_dir.iterdir()
        if d.is_dir() and ((d / "instagram.json").is_file() or (d / "youtube.json").is_file())
    )

    ig_count = sum(1 for d in posted_dirs if (d / "instagram.json").is_file())
    yt_count = sum(1 for d in posted_dirs if (d / "youtube.json").is_file())

    lines = [
        "# Storytube analytics report",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} · {len(posted_dirs)} posted outputs "
        f"({ig_count} on Instagram, {yt_count} on YouTube)",
        "",
    ]

    for out_dir in posted_dirs:
        meta = load_json(out_dir / "meta.json")
        ig_state = load_json(out_dir / "instagram.json")
        yt_state = load_json(out_dir / "youtube.json")
        text = written_text(out_dir)
        music = Path(meta.get("music_file", "")).stem.replace("_", " ") if meta.get("music_file") else ""

        lines.append(f"## {out_dir.name}")
        lines.append("")
        if text:
            lines.append("**Written:**")
            lines.append("")
            for line in text.splitlines():
                lines.append(f"> {line}" if line.strip() else ">")
            lines.append("")
        lines.append(f"**Music:** {music or 'none'}")
        lines.append("")
        lines.append("| Platform | Title/Link | Views | Likes | Comments | Other |")
        lines.append("|---|---|---|---|---|---|")
        if ig_state:
            lines.append(instagram_row(ig_state))
        if yt_state:
            lines.append(youtube_row(yt_state))
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=config.OUTPUT_DIR / "_analysis" / "report.md")
    args = parser.parse_args()

    report = build_report(config.OUTPUT_DIR)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
