"""Data layer: every query that touches tenant data takes owner_id and filters on it."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .db import utcnow
from .models import ApiToken, Job, Owner, SpamEvent, Submission, Widget


# ---------- owners / tokens ----------
def get_owner_by_email(s: Session, email: str) -> Owner | None:
    return s.scalar(select(Owner).where(Owner.email == email.lower()))


def get_owner_by_token_hash(s: Session, token_hash: str) -> Owner | None:
    return s.scalar(
        select(Owner)
        .join(ApiToken, ApiToken.owner_id == Owner.id)
        .where(ApiToken.token_hash == token_hash, ApiToken.expires_at > utcnow())
    )


# ---------- widgets ----------
def list_widgets(s: Session, owner_id: str) -> list[Widget]:
    return list(s.scalars(select(Widget).where(Widget.owner_id == owner_id).order_by(Widget.created_at)))


def get_widget_for_owner(s: Session, owner_id: str, widget_id: str) -> Widget | None:
    return s.scalar(select(Widget).where(Widget.id == widget_id, Widget.owner_id == owner_id))


def get_widget_public(s: Session, widget_id: str) -> Widget | None:
    return s.scalar(select(Widget).where(Widget.id == widget_id, Widget.is_active.is_(True)))


# ---------- submissions ----------
def find_by_idempotency_key(s: Session, widget_id: str, key: str) -> Submission | None:
    return s.scalar(select(Submission).where(Submission.widget_id == widget_id, Submission.idempotency_key == key))


def _sub_filters(owner_id, widget_id, since, until):
    conds = [Submission.owner_id == owner_id]
    if widget_id:
        conds.append(Submission.widget_id == widget_id)
    if since:
        conds.append(Submission.created_at >= since)
    if until:
        conds.append(Submission.created_at < until)
    return conds


def list_submissions(s: Session, owner_id, widget_id, since, until, limit, offset):
    conds = _sub_filters(owner_id, widget_id, since, until)
    total = s.scalar(select(func.count()).select_from(Submission).where(*conds)) or 0
    rows = s.scalars(
        select(Submission).where(*conds).order_by(Submission.created_at.desc(), Submission.id).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def get_submission_for_owner(s: Session, owner_id: str, sub_id: str) -> Submission | None:
    return s.scalar(select(Submission).where(Submission.id == sub_id, Submission.owner_id == owner_id))


def stats(s: Session, owner_id: str, widget_id: str | None, since: datetime) -> dict:
    conds = _sub_filters(owner_id, widget_id, since, None)
    total = s.scalar(select(func.count()).select_from(Submission).where(*conds)) or 0
    enriched = (
        s.scalar(select(func.count()).select_from(Submission).where(*conds, Submission.country.is_not(None))) or 0
    )
    per_widget = s.execute(
        select(Widget.id, Widget.title, func.count(Submission.id))
        .select_from(Widget)
        .outerjoin(Submission, (Submission.widget_id == Widget.id) & (Submission.created_at >= since))
        .where(Widget.owner_id == owner_id, *([Widget.id == widget_id] if widget_id else []))
        .group_by(Widget.id, Widget.title)
        .order_by(func.count(Submission.id).desc(), Widget.id)
    ).all()
    day = func.date(Submission.created_at)
    by_day = s.execute(select(day, func.count()).where(*conds).group_by(day).order_by(day)).all()
    by_country = s.execute(
        select(Submission.country, func.count())
        .where(*conds, Submission.country.is_not(None))
        .group_by(Submission.country)
        .order_by(func.count().desc())
    ).all()
    spam_conds = [Widget.owner_id == owner_id, SpamEvent.created_at >= since]
    if widget_id:
        spam_conds.append(Widget.id == widget_id)
    spam = s.scalar(
        select(func.count()).select_from(SpamEvent).join(Widget, Widget.id == SpamEvent.widget_id).where(*spam_conds)
    ) or 0
    return {
        "total": total,
        "enriched": enriched,
        "spam": spam,
        "per_widget": [{"widget_id": a, "title": b, "submissions": c} for a, b, c in per_widget],
        "by_day": {str(d): c for d, c in by_day},
        "by_country": [{"country": c, "count": n} for c, n in by_country],
    }


# ---------- jobs (outbox) ----------
def claim_due_job(s: Session) -> Job | None:
    job = s.scalar(
        select(Job).where(Job.status == "pending", Job.run_at <= utcnow()).order_by(Job.run_at).limit(1).with_for_update(skip_locked=True)
    )
    if job:
        job.status, job.updated_at = "running", utcnow()
        s.commit()
    return job


def reset_running_jobs(s: Session) -> None:
    s.execute(update(Job).where(Job.status == "running").values(status="pending"))
    s.commit()


def job_counts(s: Session) -> dict:
    rows = s.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    return {st: n for st, n in rows}


def retry_delay(base: float, attempts: int) -> timedelta:
    return timedelta(seconds=base * (2 ** (attempts - 1)))
