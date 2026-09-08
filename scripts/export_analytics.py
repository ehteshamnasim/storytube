"""Build one markdown report of every posted output's text, music and platform numbers.

Reads only what is already saved on disk (instagram.json / youtube.json / meta.json /
poem.txt / caption.txt / scenes.json) - no API calls, so it is instant and needs no keys.

Usage:
    python scripts/export_analytics.py
    python scripts/export_analytics.py --out output/_analysis/my_report.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from storytube import config  # noqa: E402
from storytube.analytics import collect_posted  # noqa: E402


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
    entries = collect_posted(output_dir)
    ig_count = sum(1 for e in entries if e["instagram"])
    yt_count = sum(1 for e in entries if e["youtube"])

    lines = [
        "# Storytube analytics report",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} · {len(entries)} posted outputs "
        f"({ig_count} on Instagram, {yt_count} on YouTube)",
        "",
    ]

    for entry in entries:
        lines.append(f"## {entry['name']}")
        lines.append("")
        if entry["text"]:
            lines.append("**Written:**")
            lines.append("")
            for line in entry["text"].splitlines():
                lines.append(f"> {line}" if line.strip() else ">")
            lines.append("")
        lines.append(f"**Music:** {entry['music'] or 'none'}")
        lines.append("")
        lines.append("| Platform | Title/Link | Views | Likes | Comments | Other |")
        lines.append("|---|---|---|---|---|---|")
        if entry["instagram"]:
            lines.append(instagram_row(entry["instagram"]))
        if entry["youtube"]:
            lines.append(youtube_row(entry["youtube"]))
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
