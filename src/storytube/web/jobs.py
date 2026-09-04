from __future__ import annotations

import queue
import threading
import uuid
from pathlib import Path
from typing import Optional

from ..pipeline import PipelineOptions, run_pipeline


class Job:
    def __init__(self, job_id: str, story_name: str):
        self.id = job_id
        self.story_name = story_name
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.done = False
        self.error: Optional[str] = None
        self.result_path: Optional[Path] = None
        self.thread: Optional[threading.Thread] = None

    def start(self, story_text: str, options: PipelineOptions) -> None:
        def target() -> None:
            try:
                def on_progress(event: dict) -> None:
                    self.events.put({"type": "progress", **event})

                final_path = run_pipeline(story_text, self.story_name, options, on_progress=on_progress)
                self.result_path = final_path
                self.events.put({"type": "complete", "path": str(final_path)})
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)
                self.events.put({"type": "error", "message": str(exc)})
            finally:
                self.done = True
                self.events.put({"type": "end"})

        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()


_jobs: dict[str, Job] = {}


def create_job(story_name: str, story_text: str, options: PipelineOptions) -> Job:
    job_id = uuid.uuid4().hex[:12]
    job = Job(job_id, story_name)
    _jobs[job_id] = job
    job.start(story_text, options)
    return job


def get_job(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)
