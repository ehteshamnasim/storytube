from pathlib import Path


def _format_srt_time(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, total_ms = divmod(total_ms, 3600000)
    minutes, total_ms = divmod(total_ms, 60000)
    secs, ms = divmod(total_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _render_chunk(index: int, chunk: list[dict], offset: float) -> str:
    start = offset + chunk[0]["start"]
    end = offset + chunk[-1]["start"] + chunk[-1]["duration"]
    text = " ".join(word["text"] for word in chunk)
    return f"{index}\n{_format_srt_time(start)} --> {_format_srt_time(end)}\n{text}\n"


def build_srt(
    scenes_words: list[list[dict]],
    scene_offsets: list[float],
    out_path: Path,
    max_words_per_line: int = 5,
) -> None:
    entries = []
    index = 1
    for words, offset in zip(scenes_words, scene_offsets):
        chunk: list[dict] = []
        for word in words:
            chunk.append(word)
            if len(chunk) >= max_words_per_line:
                entries.append(_render_chunk(index, chunk, offset))
                index += 1
                chunk = []
        if chunk:
            entries.append(_render_chunk(index, chunk, offset))
            index += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(entries), encoding="utf-8")
