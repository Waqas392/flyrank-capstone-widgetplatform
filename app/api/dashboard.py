"""Authenticated owner dashboard: submissions + analytics."""
from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import repo
from ..db import utcnow
from ..errors import ApiError
from ..models import Owner, Submission
from ..services import widgets as widget_svc
from .deps import current_owner, get_session

router = APIRouter(prefix="/api/dashboard")


def _sub_out(sub: Submission) -> dict:
    return {
        "id": sub.id,
        "widget_id": sub.widget_id,
        "data": json.loads(sub.data_json),
        "country": sub.country,
        "city": sub.city,
        "geo_provider": sub.geo_provider,
        "created_at": sub.created_at.isoformat() + "Z",
    }


@router.get("/submissions")
def list_submissions(
    widget_id: str | None = Query(None, max_length=16),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    days: int | None = Query(None, ge=1, le=3650),
    owner: Owner = Depends(current_owner),
    s: Session = Depends(get_session),
):
    if widget_id:
        widget_svc.get(s, owner.id, widget_id)  # 404 if it isn't yours
    since = utcnow() - timedelta(days=days) if days else None
    rows, total = repo.list_submissions(s, owner.id, widget_id, since, None, limit, offset)
    return {"items": [_sub_out(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: str, owner: Owner = Depends(current_owner), s: Session = Depends(get_session)):
    sub = repo.get_submission_for_owner(s, owner.id, submission_id)
    if sub is None:
        raise ApiError(404, "submission_not_found", "Submission not found")
    return _sub_out(sub)


@router.get("/stats")
def stats(
    widget_id: str | None = Query(None, max_length=16),
    days: int = Query(30, ge=1, le=365),
    owner: Owner = Depends(current_owner),
    s: Session = Depends(get_session),
):
    if widget_id:
        widget_svc.get(s, owner.id, widget_id)
    now = utcnow()
    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    st = repo.stats(s, owner.id, widget_id, since)
    series = []
    for i in range(days):  # fill zero days so charts don't have gaps
        d = (since + timedelta(days=i)).date().isoformat()
        series.append({"date": d, "count": st["by_day"].get(d, 0)})
    return {
        "range_days": days,
        "totals": {"submissions": st["total"], "geo_enriched": st["enriched"], "spam_blocked": st["spam"]},
        "per_widget": st["per_widget"],
        "by_day": series,
        "by_country": st["by_country"],
    }
