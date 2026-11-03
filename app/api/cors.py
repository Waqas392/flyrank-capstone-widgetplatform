"""Path-aware CORS.

* Public surface (widget.js, assets, config, submissions): any origin, because the whole point is
  that it is embedded on sites we don't control. Safe because these endpoints use no cookies or
  ambient credentials, so `*` leaks nothing a direct request couldn't get.
* Owner/admin surface (/api/*): only origins listed in ADMIN_CORS_ORIGINS.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

log = logging.getLogger("cors")

PUBLIC_METHODS = "GET, POST, OPTIONS"
PUBLIC_HEADERS = "Content-Type, Idempotency-Key"
ADMIN_METHODS = "GET, POST, PATCH, DELETE, OPTIONS"
ADMIN_HEADERS = "Authorization, Content-Type"


def is_public(path: str) -> bool:
    return path in ("/submissions", "/widget.js", "/healthz") or path.startswith(("/widgets/", "/assets/"))


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def cors_middleware(request: Request, call_next):
        origin = request.headers.get("origin")
        public = is_public(request.url.path)
        allow_origin = None
        if origin:
            allow_origin = "*" if public else (origin if origin in request.app.state.ctx.settings.admin_cors_origins else None)

        # Preflight: answer it ourselves, before routing.
        if request.method == "OPTIONS" and origin and request.headers.get("access-control-request-method"):
            if allow_origin is None:
                return Response(status_code=403)
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": allow_origin,
                    "Access-Control-Allow-Methods": PUBLIC_METHODS if public else ADMIN_METHODS,
                    "Access-Control-Allow-Headers": PUBLIC_HEADERS if public else ADMIN_HEADERS,
                    "Access-Control-Max-Age": "86400",
                    "Vary": "Origin",
                },
            )

        try:
            response = await call_next(request)
        except Exception:  # last line of defence: still a JSON body, still CORS headers
            log.exception("unhandled error on %s %s", request.method, request.url.path)
            response = JSONResponse({"error": {"code": "internal_error", "message": "Internal server error"}}, status_code=500)

        if allow_origin:
            response.headers["Access-Control-Allow-Origin"] = allow_origin
            response.headers["Access-Control-Expose-Headers"] = "Retry-After, ETag"
            if allow_origin != "*":
                response.headers["Vary"] = "Origin"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response
