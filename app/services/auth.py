from __future__ import annotations

from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import repo
from ..db import utcnow
from ..errors import ApiError
from ..models import ApiToken, Owner
from . import security


def _issue_token(s: Session, owner_id: str, ttl_hours: int) -> str:
    raw, hashed = security.new_token()
    now = utcnow()
    s.add(ApiToken(token_hash=hashed, owner_id=owner_id, created_at=now, expires_at=now + timedelta(hours=ttl_hours)))
    return raw


def register(s: Session, email: str, password: str, ttl_hours: int) -> tuple[Owner, str]:
    owner = Owner(id=security.new_id(), email=email.lower(), password_hash=security.hash_password(password), created_at=utcnow())
    s.add(owner)
    try:
        s.flush()
    except IntegrityError:
        s.rollback()
        raise ApiError(409, "email_taken", "An account with this email already exists")
    token = _issue_token(s, owner.id, ttl_hours)
    s.commit()
    return owner, token


def login(s: Session, email: str, password: str, ttl_hours: int) -> tuple[Owner, str]:
    owner = repo.get_owner_by_email(s, email)
    if owner is None:
        security.burn_password_check(password)
    if owner is None or not security.verify_password(password, owner.password_hash):
        raise ApiError(401, "invalid_credentials", "Invalid email or password")
    token = _issue_token(s, owner.id, ttl_hours)
    s.commit()
    return owner, token


def authenticate(s: Session, raw_token: str) -> Owner:
    owner = repo.get_owner_by_token_hash(s, security.hash_token(raw_token))
    if owner is None:
        raise ApiError(401, "unauthorized", "Missing or invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    return owner
