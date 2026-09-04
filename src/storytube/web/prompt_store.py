from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import config


def _current_path(category: str) -> Path:
    return config.PROMPTS_DIR / f"scene_planning_{category}.txt"


def _versions_dir(category: str) -> Path:
    return config.PROMPTS_DIR / "versions" / category


def list_categories() -> list[str]:
    categories = []
    for path in sorted(config.PROMPTS_DIR.glob("scene_planning_*.txt")):
        match = re.match(r"scene_planning_(.+)\.txt", path.name)
        if match:
            categories.append(match.group(1))
    return categories


def get_current(category: str) -> str:
    path = _current_path(category)
    if not path.exists():
        raise FileNotFoundError(f"No prompt template found for category '{category}'")
    return path.read_text(encoding="utf-8")


def list_versions(category: str) -> list[dict[str, Any]]:
    versions_dir = _versions_dir(category)
    if not versions_dir.exists():
        return []
    entries = []
    for path in sorted(versions_dir.glob("*.txt"), reverse=True):
        text = path.read_text(encoding="utf-8")
        entries.append(
            {
                "id": path.stem,
                "preview": text.strip().splitlines()[0][:120] if text.strip() else "",
            }
        )
    return entries


def get_version(category: str, version_id: str) -> str:
    path = _versions_dir(category) / f"{version_id}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Version '{version_id}' not found for category '{category}'")
    return path.read_text(encoding="utf-8")


def _archive_current(category: str) -> None:
    current_path = _current_path(category)
    if not current_path.exists():
        return
    versions_dir = _versions_dir(category)
    versions_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    (versions_dir / f"{timestamp}.txt").write_text(current_path.read_text(encoding="utf-8"), encoding="utf-8")


def save_new_version(category: str, text: str) -> None:
    _archive_current(category)
    current_path = _current_path(category)
    current_path.parent.mkdir(parents=True, exist_ok=True)
    current_path.write_text(text, encoding="utf-8")


def restore_version(category: str, version_id: str) -> None:
    text = get_version(category, version_id)
    save_new_version(category, text)
