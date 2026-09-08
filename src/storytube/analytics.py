"""Read-only summary of every posted output's text, music and platform numbers.

Reads only what generation and publishing already saved to disk (meta.json,
poem.txt/caption.txt/scenes.json, instagram.json, youtube.json) - no API calls,
so this is instant and needs no keys. Shared by scripts/export_analytics.py
and the web app's Analytics page.
"""

from __future__ import annotations

import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _written_text(out_dir: Path) -> str:
    poem_file = out_dir / "poem.txt"
    if poem_file.is_file():
        return poem_file.read_text(encoding="utf-8").strip()

    caption_file = out_dir / "caption.txt"
    if caption_file.is_file():
        return caption_file.read_text(encoding="utf-8").strip()

    scenes = _load_json(out_dir / "scenes.json")
    lines = [s.get("narration", "") for s in scenes.get("scenes", [])]
    return "\n".join(line for line in lines if line).strip()


def collect_posted(output_dir: Path) -> list[dict]:
    """One entry per output that has been posted to Instagram and/or YouTube."""
    if not output_dir.is_dir():
        return []

    entries = []
    for out_dir in sorted(output_dir.iterdir()):
        if not out_dir.is_dir():
            continue
        instagram_state = _load_json(out_dir / "instagram.json")
        youtube_state = _load_json(out_dir / "youtube.json")
        if not instagram_state and not youtube_state:
            continue

        meta = _load_json(out_dir / "meta.json")
        music_file = meta.get("music_file", "")
        entries.append({
            "name": out_dir.name,
            "text": _written_text(out_dir),
            "music": Path(music_file).stem.replace("_", " ").replace("-", " ") if music_file else "",
            "created_at": meta.get("created_at", ""),
            "instagram": instagram_state or None,
            "youtube": youtube_state or None,
        })

    entries.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    return entries
