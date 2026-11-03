"""Background worker for non-critical side effects: retries with backoff, alert on permanent failure."""
from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy.orm import Session

from .. import repo
from ..db import utcnow
from ..models import Submission, Widget
from . import notify

log = logging.getLogger("jobs")


class Worker:
    def __init__(self, ctx):
        self.ctx = ctx
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ---- handlers ----
    def _confirmation_email(self, s: Session, payload: dict) -> None:
        sub = s.get(Submission, payload["submission_id"])
        if sub is None:
            return
        data = json.loads(sub.data_json)
        to = data.get("email")
        if not to:
            return  # nothing to confirm to
        widget = s.get(Widget, sub.widget_id)
        notify.send_email(self.ctx.settings, self.ctx.faults, to, f"Thanks for contacting {widget.title if widget else 'us'}", "We received your submission.")

    HANDLERS = {"confirmation_email": "_confirmation_email"}

    # ---- one unit of work (sync, so tests can drive it deterministically) ----
    def process_one(self) -> bool:
        with self.ctx.session_factory() as s:
            job = repo.claim_due_job(s)
            if job is None:
                return False
            try:
                getattr(self, self.HANDLERS[job.kind])(s, json.loads(job.payload_json))
                job.status, job.last_error = "done", None
            except Exception as exc:
                job.attempts += 1
                job.last_error = f"{type(exc).__name__}: {exc}"[:500]
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    log.error("ALERT: job %s (%s) failed permanently after %d attempts: %s", job.id, job.kind, job.attempts, job.last_error)
                else:
                    job.status = "pending"
                    job.run_at = utcnow() + repo.retry_delay(self.ctx.settings.job_backoff_base, job.attempts)
                    log.warning("job %s failed (attempt %d/%d), retrying: %s", job.id, job.attempts, job.max_attempts, job.last_error)
            job.updated_at = utcnow()
            s.commit()
            return True

    def drain(self, limit: int = 100) -> int:
        n = 0
        while n < limit and self.process_one():
            n += 1
        return n

    # ---- lifecycle ----
    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = await asyncio.to_thread(self.process_one)
            except Exception:
                log.exception("worker loop error")
                worked = False
            if not worked:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.ctx.settings.job_poll_interval)
                except asyncio.TimeoutError:
                    pass

    def start(self) -> None:
        with self.ctx.session_factory() as s:
            repo.reset_running_jobs(s)  # recover jobs interrupted by a crash
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
