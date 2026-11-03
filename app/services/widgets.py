"""Widget business logic. Tenant isolation: every lookup is scoped by owner_id; others get 404."""
from __future__ import annotations

import json
import secrets

from sqlalchemy.orm import Session

from .. import repo
from ..db import utcnow
from ..errors import ApiError
from ..models import Widget
from ..schemas import Display, FieldSpec, WidgetCreate, WidgetUpdate

DEFAULT_FIELDS = {
    "signup_form": [FieldSpec(name="email", label="Email", type="email", required=True)],
    "contact_form": [
        FieldSpec(name="name", label="Name", type="text", required=True),
        FieldSpec(name="email", label="Email", type="email", required=True),
        FieldSpec(name="message", label="Message", type="textarea", required=True, max_length=2000),
    ],
    "cta_popover": [FieldSpec(name="email", label="Email", type="email", required=True)],
}
DEFAULT_HONEYPOT = "website"


def fields_of(w: Widget) -> list[dict]:
    return json.loads(w.fields_json)


def display_of(w: Widget) -> dict:
    return json.loads(w.display_json)


def _not_found() -> ApiError:
    return ApiError(404, "widget_not_found", "Widget not found")


def create(s: Session, owner_id: str, body: WidgetCreate) -> Widget:
    fields = body.fields or DEFAULT_FIELDS[body.type]
    honeypot = body.honeypot_field or DEFAULT_HONEYPOT
    if any(f.name == honeypot for f in fields):
        raise ApiError(422, "validation_error", "A field may not use the honeypot field name", [{"field": "fields"}])
    display = body.display or Display(mode="popover" if body.type == "cta_popover" else "inline", delay_seconds=3 if body.type == "cta_popover" else 0)
    now = utcnow()
    w = Widget(
        id=secrets.token_urlsafe(8),
        owner_id=owner_id,
        type=body.type,
        title=body.title,
        description=body.description,
        button_text=body.button_text,
        fields_json=json.dumps([f.model_dump() for f in fields]),
        display_json=json.dumps(display.model_dump()),
        honeypot_field=honeypot,
        is_active=body.is_active,
        version=1,
        created_at=now,
        updated_at=now,
    )
    s.add(w)
    s.commit()
    return w


def get(s: Session, owner_id: str, widget_id: str) -> Widget:
    w = repo.get_widget_for_owner(s, owner_id, widget_id)
    if w is None:
        raise _not_found()
    return w


def update(s: Session, owner_id: str, widget_id: str, body: WidgetUpdate) -> Widget:
    w = get(s, owner_id, widget_id)
    patch = body.model_dump(exclude_unset=True)
    honeypot = patch.get("honeypot_field") or w.honeypot_field
    new_fields = body.fields if body.fields is not None else [FieldSpec(**f) for f in fields_of(w)]
    if any(f.name == honeypot for f in new_fields):
        raise ApiError(422, "validation_error", "A field may not use the honeypot field name", [{"field": "fields"}])
    for key in ("title", "description", "button_text", "is_active"):
        if patch.get(key) is not None:
            setattr(w, key, patch[key])
    if body.fields is not None:
        w.fields_json = json.dumps([f.model_dump() for f in body.fields])
    if body.display is not None:
        w.display_json = json.dumps(body.display.model_dump())
    if patch.get("honeypot_field"):
        w.honeypot_field = patch["honeypot_field"]
    w.version += 1
    w.updated_at = utcnow()
    s.commit()
    return w


def delete(s: Session, owner_id: str, widget_id: str) -> None:
    w = get(s, owner_id, widget_id)
    s.delete(w)
    s.commit()


def public_config(w: Widget) -> dict:
    """What an anonymous page may see. No owner info, no internals."""
    return {
        "id": w.id,
        "type": w.type,
        "title": w.title,
        "description": w.description,
        "button_text": w.button_text,
        "fields": fields_of(w),
        "display": display_of(w),
        "honeypot_field": w.honeypot_field,
        "version": w.version,
    }
