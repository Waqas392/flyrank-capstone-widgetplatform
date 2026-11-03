"""Authenticated owner API: accounts + widget CRUD + embed snippet."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import Owner, Widget
from ..schemas import Credentials, WidgetCreate, WidgetUpdate
from ..services import auth
from ..services import widgets as svc
from .deps import current_owner, get_ctx, get_session
from .http import client_ip

router = APIRouter(prefix="/api")


def embed_snippet(ctx, widget_id: str) -> str:
    return f'<script src="{ctx.settings.public_base_url}/widget.js?id={widget_id}" async></script>'


def widget_out(ctx, w: Widget) -> dict:
    return {
        "id": w.id,
        "type": w.type,
        "title": w.title,
        "description": w.description,
        "button_text": w.button_text,
        "fields": svc.fields_of(w),
        "display": svc.display_of(w),
        "honeypot_field": w.honeypot_field,
        "is_active": w.is_active,
        "version": w.version,
        "embed_snippet": embed_snippet(ctx, w.id),
        "created_at": w.created_at.isoformat() + "Z",
        "updated_at": w.updated_at.isoformat() + "Z",
    }


def _auth_limit(request: Request, ctx) -> None:
    ok, retry = ctx.auth_limiter.allow(client_ip(request, ctx.settings))
    if not ok:
        raise ApiError(429, "rate_limited", "Too many attempts", headers={"Retry-After": str(max(1, int(retry + 0.999)))})


@router.post("/auth/register", status_code=201)
def register(body: Credentials, request: Request, ctx=Depends(get_ctx), s: Session = Depends(get_session)):
    if not ctx.settings.allow_registration:
        raise ApiError(403, "registration_disabled", "Registration is disabled")
    _auth_limit(request, ctx)
    owner, token = auth.register(s, body.email, body.password, ctx.settings.token_ttl_hours)
    return {"owner": {"id": owner.id, "email": owner.email}, "token": token}


@router.post("/auth/login")
def login(body: Credentials, request: Request, ctx=Depends(get_ctx), s: Session = Depends(get_session)):
    _auth_limit(request, ctx)
    owner, token = auth.login(s, body.email, body.password, ctx.settings.token_ttl_hours)
    return {"owner": {"id": owner.id, "email": owner.email}, "token": token}


@router.post("/widgets", status_code=201)
def create_widget(body: WidgetCreate, owner: Owner = Depends(current_owner), ctx=Depends(get_ctx), s: Session = Depends(get_session)):
    return widget_out(ctx, svc.create(s, owner.id, body))


@router.get("/widgets")
def list_widgets(owner: Owner = Depends(current_owner), ctx=Depends(get_ctx), s: Session = Depends(get_session)):
    from .. import repo

    return {"items": [widget_out(ctx, w) for w in repo.list_widgets(s, owner.id)]}


@router.get("/widgets/{widget_id}")
def get_widget(widget_id: str, owner: Owner = Depends(current_owner), ctx=Depends(get_ctx), s: Session = Depends(get_session)):
    return widget_out(ctx, svc.get(s, owner.id, widget_id))


@router.patch("/widgets/{widget_id}")
def update_widget(widget_id: str, body: WidgetUpdate, owner: Owner = Depends(current_owner), ctx=Depends(get_ctx), s: Session = Depends(get_session)):
    return widget_out(ctx, svc.update(s, owner.id, widget_id, body))


@router.delete("/widgets/{widget_id}", status_code=204)
def delete_widget(widget_id: str, owner: Owner = Depends(current_owner), s: Session = Depends(get_session)):
    svc.delete(s, owner.id, widget_id)


@router.get("/widgets/{widget_id}/embed")
def get_embed(widget_id: str, owner: Owner = Depends(current_owner), ctx=Depends(get_ctx), s: Session = Depends(get_session)):
    w = svc.get(s, owner.id, widget_id)
    return {"widget_id": w.id, "embed_snippet": embed_snippet(ctx, w.id)}
