from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import Owner
from ..services import auth


def get_ctx(request: Request):
    return request.app.state.ctx


def get_session(ctx=Depends(get_ctx)):
    with ctx.session_factory() as s:
        yield s


def current_owner(request: Request, s: Session = Depends(get_session)) -> Owner:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "unauthorized", "Missing or invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    return auth.authenticate(s, token.strip())
