from __future__ import annotations

import queue
import threading
import uuid
from pathlib import Path
from typing import Callable, Optional

from ..pipeline import PipelineOptions, run_pipeline
from ..poetry import PoemOptions, generate_poem_reel


class Job:
    def __init__(self, job_id: str, story_name: str):
        self.id = job_id
        self.story_name = story_name
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.done = False
        self.error: Optional[str] = None
        self.result_path: Optional[Path] = None
        self.thread: Optional[threading.Thread] = None

    def _run(self, work: "Callable[[], Path]") -> None:
        def target() -> None:
            try:
                self.result_path = work()
                self.events.put({"type": "complete", "path": str(self.result_path)})
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)
                self.events.put({"type": "error", "message": str(exc)})
            finally:
                self.done = True
                self.events.put({"type": "end"})

        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()

    def start(self, story_text: str, options: PipelineOptions) -> None:
        def work() -> Path:
            def on_progress(event: dict) -> None:
                self.events.put({"type": "progress", **event})

            return run_pipeline(story_text, self.story_name, options, on_progress=on_progress)

        self._run(work)

    def start_poem(self, poem_text: str, options: PoemOptions) -> None:
        def work() -> Path:
            def on_progress(stage: str, message: str) -> None:
                self.events.put({"type": "progress", "stage": stage, "message": message})

            return generate_poem_reel(poem_text, self.story_name, options, on_progress=on_progress).video_path

        self._run(work)


_jobs: dict[str, Job] = {}


def create_job(story_name: str, story_text: str, options: PipelineOptions) -> Job:
    job_id = uuid.uuid4().hex[:12]
    job = Job(job_id, story_name)
    _jobs[job_id] = job
    job.start(story_text, options)
    return job


def create_poem_job(name: str, poem_text: str, options: PoemOptions) -> Job:
    job_id = uuid.uuid4().hex[:12]
    job = Job(job_id, name)
    _jobs[job_id] = job
    job.start_poem(poem_text, options)
    return job


def get_job(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)
