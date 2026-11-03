"""Settings - everything comes from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _i(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass
class Settings:
    database_url: str = "sqlite:///./data/app.db"
    public_base_url: str = "http://localhost:8000"
    admin_cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5500", "http://127.0.0.1:5500"]
    )
    secret_key: str = "dev-only-change-me"
    allow_registration: bool = True
    token_ttl_hours: int = 168
    trust_proxy: bool = False
    max_body_bytes: int = 16 * 1024
    rl_ip_capacity: float = 10
    rl_ip_refill: float = 2
    rl_widget_capacity: float = 60
    rl_widget_refill: float = 5
    rl_auth_capacity: float = 5
    rl_auth_refill: float = 0.1
    min_fill_ms: int = 1500
    geo_mode: str = "mock"  # "mock" | "live"
    geo_timeout: float = 1.5
    smtp_host: str = ""
    smtp_port: int = 1025
    mail_from: str = "widgets@example.com"
    job_max_attempts: int = 3
    job_backoff_base: float = 5.0
    job_poll_interval: float = 1.0
    run_worker: bool = True
    debug_endpoints: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        origins = os.getenv("ADMIN_CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500")
        return cls(
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            public_base_url=os.getenv("PUBLIC_BASE_URL", cls.public_base_url).rstrip("/"),
            admin_cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
            secret_key=os.getenv("SECRET_KEY", cls.secret_key),
            allow_registration=_b("ALLOW_REGISTRATION", True),
            token_ttl_hours=_i("TOKEN_TTL_HOURS", 168),
            trust_proxy=_b("TRUST_PROXY", False),
            max_body_bytes=_i("MAX_BODY_BYTES", 16 * 1024),
            rl_ip_capacity=_f("RL_IP_CAPACITY", 10),
            rl_ip_refill=_f("RL_IP_REFILL", 2),
            rl_widget_capacity=_f("RL_WIDGET_CAPACITY", 60),
            rl_widget_refill=_f("RL_WIDGET_REFILL", 5),
            rl_auth_capacity=_f("RL_AUTH_CAPACITY", 5),
            rl_auth_refill=_f("RL_AUTH_REFILL", 0.1),
            min_fill_ms=_i("MIN_FILL_MS", 1500),
            geo_mode=os.getenv("GEO_MODE", "mock").lower(),
            geo_timeout=_f("GEO_TIMEOUT_SECONDS", 1.5),
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=_i("SMTP_PORT", 1025),
            mail_from=os.getenv("MAIL_FROM", "widgets@example.com"),
            job_max_attempts=_i("JOB_MAX_ATTEMPTS", 3),
            job_backoff_base=_f("JOB_BACKOFF_BASE_SECONDS", 5),
            job_poll_interval=_f("JOB_POLL_INTERVAL_SECONDS", 1.0),
            run_worker=_b("RUN_WORKER", True),
            debug_endpoints=_b("DEBUG_ENDPOINTS", False),
        )
