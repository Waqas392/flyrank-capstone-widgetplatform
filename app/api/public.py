"""Public surface: loader, versioned bundle, cached config, hardened submission endpoint."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import repo
from ..errors import ApiError
from ..services import submissions
from ..services import widgets as widget_svc
from .deps import get_ctx, get_session
from .http import client_ip, parse_json_object, read_limited_body

STATIC = Path(__file__).resolve().parent.parent.parent / "static"
router = APIRouter()

JS_TYPE = "application/javascript; charset=utf-8"
IMMUTABLE = "public, max-age=31536000, immutable"
LOADER_CACHE = "public, max-age=300"
CONFIG_CACHE = "public, max-age=60, stale-while-revalidate=300"


@dataclass
class Bundle:
    name: str
    body: bytes
    etag: str
    loader: bytes
    loader_etag: str


def load_bundle() -> Bundle:
    body = (STATIC / "widget.js").read_bytes()
    digest = hashlib.sha256(body).hexdigest()[:10]
    name = f"widget.{digest}.js"  # content hash in the URL = safe to cache forever, busts on change
    loader = (STATIC / "loader.js").read_text().replace("__BUNDLE__", name).encode()
    return Bundle(name, body, f'"{digest}"', loader, f'"{hashlib.sha256(loader).hexdigest()[:10]}"')


def _not_modified(request: Request, etag: str) -> bool:
    inm = request.headers.get("if-none-match", "")
    mine = etag.removeprefix("W/")
    return mine in [t.strip().removeprefix("W/") for t in inm.split(",")]


@router.get("/widget.js")
def loader(request: Request, ctx=Depends(get_ctx)):
    b: Bundle = ctx.bundle
    headers = {"Cache-Control": LOADER_CACHE, "ETag": b.loader_etag}
    if _not_modified(request, b.loader_etag):
        return Response(status_code=304, headers=headers)
    return Response(b.loader, media_type=JS_TYPE, headers=headers)


@router.get("/assets/{filename}")
def asset(filename: str, ctx=Depends(get_ctx)):
    b: Bundle = ctx.bundle
    if filename != b.name:
        raise ApiError(404, "not_found", "Unknown asset")
    return Response(b.body, media_type=JS_TYPE, headers={"Cache-Control": IMMUTABLE, "ETag": b.etag})


@router.get("/widgets/{widget_id}/config")
def widget_config(widget_id: str, request: Request, s: Session = Depends(get_session)):
    w = repo.get_widget_public(s, widget_id)
    if w is None:
        raise ApiError(404, "widget_not_found", "Widget not found", headers={"Cache-Control": "public, max-age=10"})
    etag = f'W/"{w.id}-v{w.version}"'
    headers = {"Cache-Control": CONFIG_CACHE, "ETag": etag}
    if _not_modified(request, etag):
        return Response(status_code=304, headers=headers)
    return Response(json.dumps(widget_svc.public_config(w)), media_type="application/json", headers=headers)


@router.post("/submissions")
async def create_submission(request: Request, ctx=Depends(get_ctx)):
    ip = client_ip(request, ctx.settings)
    # 1. cheapest check first: per-IP flood protection (also counts junk requests)
    ok, retry = ctx.ip_limiter.allow(ip)
    if not ok:
        raise ApiError(429, "rate_limited", "Too many requests - slow down", headers={"Retry-After": str(max(1, int(retry + 0.999)))})
    # 2. bounded read, then strict parse
    body = await read_limited_body(request, ctx.settings.max_body_bytes)
    payload = parse_json_object(body)
    # 3. validation, spam, dedupe, enrichment, store
    result = await submissions.handle(ctx, payload, ip, request.headers.get("idempotency-key"))
    return JSONResponse({"ok": True, "id": result.id, "duplicate": result.duplicate}, status_code=200 if result.duplicate else 201)
