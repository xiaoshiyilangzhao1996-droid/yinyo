"""Runtime job primitives for YINYO gateway dispatch."""

from __future__ import annotations

import threading
import time
import uuid
import json
import os
from dataclasses import asdict
from dataclasses import dataclass, field
from typing import Any, Callable

from .jsonl_store import append_jsonl


@dataclass
class RuntimeJob:
    id: str
    kind: str
    payload: dict[str, Any]
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    result: Any = None
    recovery_count: int = 0


class InMemoryJobQueue:
    """Small in-process queue used by the Feishu runtime gateway.

    It keeps the dispatch contract explicit without forcing a production queue
    dependency into the alpha package.
    """

    def __init__(self, max_workers: int = 4):
        self._jobs: dict[str, RuntimeJob] = {}
        self._lock = threading.Lock()
        self.max_workers = max(1, int(max_workers))
        self._active_workers = 0

    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
        *,
        run_async: bool = True,
    ) -> RuntimeJob:
        job = RuntimeJob(id=f"job_{uuid.uuid4().hex}", kind=kind, payload=payload)
        with self._lock:
            self._jobs[job.id] = job
            if run_async and self._active_workers >= self.max_workers:
                job.status = "rejected"
                job.finished_at = time.time()
                job.error = "job queue saturated"
                return job
            if run_async:
                self._active_workers += 1

        if run_async:
            threading.Thread(target=self._run, args=(job.id, handler), daemon=True).start()
        else:
            self._run(job.id, handler)
        return job

    def get(self, job_id: str) -> RuntimeJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job_id: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = time.time()

        try:
            result = handler(job.payload)
            with self._lock:
                job.result = result
                job.status = "succeeded"
        except Exception as exc:
            with self._lock:
                job.error = str(exc)
                job.status = "failed"
        finally:
            with self._lock:
                job.finished_at = time.time()
                if self._active_workers > 0:
                    self._active_workers -= 1


class JsonlJobQueue(InMemoryJobQueue):
    """In-process job queue with durable JSONL snapshots.

    Jobs still execute in the current process, but their lifecycle is written to
    disk so operators can inspect state after a restart or crash.
    """

    def __init__(self, path: str, max_workers: int = 4):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        super().__init__(max_workers=max_workers)
        self._load()

    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
        *,
        run_async: bool = True,
    ) -> RuntimeJob:
        job = RuntimeJob(id=f"job_{uuid.uuid4().hex}", kind=kind, payload=payload)
        with self._lock:
            self._jobs[job.id] = job
            self._append(job, "queued")
            if run_async and self._active_workers >= self.max_workers:
                job.status = "rejected"
                job.finished_at = time.time()
                job.error = "job queue saturated"
                self._append(job, "rejected_queue_saturated")
                return job
            if run_async:
                self._active_workers += 1

        if run_async:
            threading.Thread(target=self._run, args=(job.id, handler), daemon=True).start()
        else:
            self._run(job.id, handler)
        return job

    def _run(self, job_id: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = time.time()
            self._append(job, "running")

        try:
            result = handler(job.payload)
            with self._lock:
                job.result = result
                job.status = "succeeded"
                self._append(job, "succeeded")
        except Exception as exc:
            with self._lock:
                job.error = str(exc)
                job.status = "failed"
                self._append(job, "failed")
        finally:
            with self._lock:
                job.finished_at = time.time()
                self._append(job, "finished")
                if self._active_workers > 0:
                    self._active_workers -= 1

    def _append(self, job: RuntimeJob, event: str) -> None:
        record = asdict(job)
        record["event"] = event
        record["recorded_at"] = time.time()
        append_jsonl(self.path, record)

    def _load(self) -> None:
        if not os.path.isfile(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                job_id = item.get("id")
                if not job_id:
                    continue
                self._jobs[job_id] = RuntimeJob(
                    id=job_id,
                    kind=item.get("kind", ""),
                    payload=item.get("payload", {}),
                    status=item.get("status", "queued"),
                    created_at=item.get("created_at", time.time()),
                    started_at=item.get("started_at"),
                    finished_at=item.get("finished_at"),
                    error=item.get("error"),
                    result=item.get("result"),
                    recovery_count=int(item.get("recovery_count", 0) or 0),
                )
        self._recover_unfinished_after_restart()

    def _recover_unfinished_after_restart(self) -> None:
        """Mark jobs that cannot still have an in-process worker after reload."""
        now = time.time()
        for job in list(self._jobs.values()):
            if job.status not in {"queued", "running"}:
                continue
            job.status = "abandoned"
            job.finished_at = now
            job.error = "job abandoned after runtime restart before completion"
            job.recovery_count += 1
            self._append(job, "abandoned_after_restart")
