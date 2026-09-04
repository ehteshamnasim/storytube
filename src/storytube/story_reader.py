from pathlib import Path


def read_story(story_path: Path) -> str:
    text = story_path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Story file is empty: {story_path}")
    return text
