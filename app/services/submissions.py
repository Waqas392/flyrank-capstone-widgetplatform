"""The hardened submission path: validate -> protect -> dedupe -> enrich -> store (+outbox)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pydantic import TypeAdapter, EmailStr, ValidationError
from sqlalchemy.exc import IntegrityError

from .. import repo
from ..db import utcnow
from ..errors import ApiError
from ..models import Job, SpamEvent, Submission
from . import security, spam
from . import widgets as widget_svc

_WID_RE = re.compile(r"^[A-Za-z0-9_-]{1,16}$")
_EMAIL = TypeAdapter(EmailStr)
_PHONE_RE = re.compile(r"^[0-9+()\-.\s]{5,32}$")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass
class Result:
    id: str
    duplicate: bool = False


def _bad(message: str, details=None) -> ApiError:
    return ApiError(422, "validation_error", message, details)


def validate_data(widget, data: dict) -> dict:
    """Check submitted values against the widget's field definitions. Returns the clean dict."""
    specs = {f["name"]: f for f in widget_svc.fields_of(widget)}
    problems: list[dict] = []
    for key in data:
        if key not in specs:
            problems.append({"field": key, "problem": "unknown field"})
    clean: dict = {}
    for name, spec in specs.items():
        raw = data.get(name)
        empty = raw is None or (isinstance(raw, str) and raw.strip() == "")
        if spec["type"] == "checkbox":
            if raw is not None and not isinstance(raw, bool):
                problems.append({"field": name, "problem": "must be true or false"})
            elif raw is True or (raw is None and not spec["required"]):
                clean[name] = bool(raw)
            elif spec["required"]:
                problems.append({"field": name, "problem": "required"})
            continue
        if empty:
            if spec["required"]:
                problems.append({"field": name, "problem": "required"})
            continue
        if not isinstance(raw, str):
            problems.append({"field": name, "problem": "must be a string"})
            continue
        val = _CTRL.sub("", raw).strip()
        if len(val) > spec["max_length"]:
            problems.append({"field": name, "problem": f"longer than {spec['max_length']} characters"})
            continue
        if spec["type"] == "email":
            try:
                val = str(_EMAIL.validate_python(val))
            except ValidationError:
                problems.append({"field": name, "problem": "not a valid email address"})
                continue
        elif spec["type"] == "tel" and not _PHONE_RE.match(val):
            problems.append({"field": name, "problem": "not a valid phone number"})
            continue
        clean[name] = val
    if problems:
        raise _bad("Submission failed validation", problems)
    return clean


async def handle(ctx, payload: dict, ip: str, idem_key: str | None) -> Result:
    # ---- shape of the envelope ----
    wid = payload.get("widget_id")
    if not isinstance(wid, str) or not _WID_RE.match(wid):
        raise _bad("widget_id is required", [{"field": "widget_id", "problem": "missing or malformed"}])
    data = payload.get("data")
    if not isinstance(data, dict) or len(data) > 40:
        raise _bad("data must be an object", [{"field": "data", "problem": "must be an object with at most 40 keys"}])
    if idem_key is not None and not (1 <= len(idem_key) <= 128 and idem_key.isprintable()):
        raise _bad("Invalid Idempotency-Key header")

    with ctx.session_factory() as s:
        widget = repo.get_widget_public(s, wid)
        if widget is None:
            raise ApiError(404, "widget_not_found", "Widget not found")

        # ---- per-widget flood protection ----
        ok, retry = ctx.widget_limiter.allow(widget.id)
        if not ok:
            raise ApiError(429, "rate_limited", "This widget is receiving too many submissions", headers={"Retry-After": str(max(1, int(retry + 0.999)))})

        # ---- spam: honeypot (in data or top-level), timing, link stuffing ----
        hp_name = widget.honeypot_field
        hp_values = [payload.get(hp_name), data.get(hp_name)]
        data = {k: v for k, v in data.items() if k != hp_name}
        reason = spam.check_spam(honeypot_values=hp_values, data=data, elapsed_ms=payload.get("elapsed_ms"), min_fill_ms=ctx.settings.min_fill_ms)
        if reason:
            s.add(SpamEvent(id=security.new_id(), widget_id=widget.id, reason=reason, created_at=utcnow()))
            s.commit()
            # Look like success: don't teach the bot what tripped the filter.
            return Result(id=security.new_id())

        clean = validate_data(widget, data)

        # ---- idempotency: a retried submission is stored once ----
        if idem_key:
            existing = repo.find_by_idempotency_key(s, widget.id, idem_key)
            if existing:
                return Result(existing.id, duplicate=True)

        owner_id, widget_id = widget.owner_id, widget.id

    # ---- enrichment (never raises; may return None) ----
    geo = await ctx.geo.enrich(ip)

    now = utcnow()
    sub = Submission(
        id=security.new_id(),
        widget_id=widget_id,
        owner_id=owner_id,
        data_json=json.dumps(clean),
        ip_hash=security.hash_ip(ip, ctx.settings.secret_key),
        country=geo.country if geo else None,
        city=geo.city if geo else None,
        geo_provider=geo.provider if geo else None,
        idempotency_key=idem_key,
        created_at=now,
    )
    with ctx.session_factory() as s:
        s.add(sub)
        # Outbox: the side effect is only *recorded* here; the worker performs it later,
        # so a broken mail server can never fail or slow this request.
        s.add(Job(id=security.new_id(), kind="confirmation_email", payload_json=json.dumps({"submission_id": sub.id}),
                  status="pending", attempts=0, max_attempts=ctx.settings.job_max_attempts, run_at=now, created_at=now, updated_at=now))
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            if idem_key:  # lost a race with an identical retry
                existing = repo.find_by_idempotency_key(s, widget_id, idem_key)
                if existing:
                    return Result(existing.id, duplicate=True)
            raise
    return Result(sub.id)
