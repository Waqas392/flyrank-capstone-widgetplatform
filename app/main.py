"""App factory: wires settings, DB + migrations, limiters, geo chain, worker, routers."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import repo
from .api import cors, dashboard, owner, public
from .config import Settings
from .db import make_engine, make_session_factory, run_migrations
from .errors import ApiError
from .services.faults import Faults
from .services.geo import GeoChain, build_chain
from .services.jobs import Worker
from .services.ratelimit import TokenBucketLimiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@dataclass
class Context:
    settings: Settings
    engine: object
    session_factory: object
    faults: Faults
    geo: GeoChain
    ip_limiter: TokenBucketLimiter
    widget_limiter: TokenBucketLimiter
    auth_limiter: TokenBucketLimiter
    bundle: public.Bundle
    worker: Worker | None = None


class FaultsBody(BaseModel):
    geo_down: list[str] | None = None
    email_fail: bool | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    run_migrations(engine)
    faults = Faults()
    ctx = Context(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        faults=faults,
        geo=build_chain(settings.geo_mode, faults, settings.geo_timeout),
        ip_limiter=TokenBucketLimiter(settings.rl_ip_capacity, settings.rl_ip_refill),
        widget_limiter=TokenBucketLimiter(settings.rl_widget_capacity, settings.rl_widget_refill),
        auth_limiter=TokenBucketLimiter(settings.rl_auth_capacity, settings.rl_auth_refill),
        bundle=public.load_bundle(),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.secret_key == "dev-only-change-me":
            log.warning("SECRET_KEY is the dev default - set a real one outside local development")
        if settings.run_worker:
            ctx.worker.start()
        yield
        if settings.run_worker:
            await ctx.worker.stop()

    app = FastAPI(title="Embeddable Widget & Lead-Capture Platform", lifespan=lifespan)
    app.state.ctx = ctx
    ctx.worker = Worker(ctx)  # started by lifespan when RUN_WORKER=1; tests drive it by hand
    cors.install(app)

    # ---- uniform JSON errors: nothing leaks as HTML or a stack trace ----
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(exc.body(), status_code=exc.status, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]) or "body", "problem": e["msg"]} for e in exc.errors()]
        return JSONResponse(ApiError(422, "validation_error", "Request failed validation", details).body(), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse({"error": {"code": code, "message": str(exc.detail)}}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.get("/healthz")
    def healthz():
        with ctx.session_factory() as s:
            return {"status": "ok", "jobs": repo.job_counts(s)}

    app.include_router(public.router)
    app.include_router(owner.router)
    app.include_router(dashboard.router)

    if settings.debug_endpoints:
        @app.get("/_debug/faults")
        def get_faults():
            return faults.snapshot()

        @app.post("/_debug/faults")
        def set_faults(body: FaultsBody):
            if body.geo_down is not None:
                bad = set(body.geo_down) - {"a", "b"}
                if bad:
                    raise ApiError(422, "validation_error", "geo_down may only contain 'a' and 'b'")
                faults.geo_down = set(body.geo_down)
            if body.email_fail is not None:
                faults.email_fail = body.email_fail
            return faults.snapshot()

        @app.post("/_debug/drain-jobs")
        def drain_jobs():
            return {"processed": ctx.worker.drain()}

    return app


def app_factory() -> FastAPI:  # uvicorn --factory app.main:app_factory
    return create_app()
