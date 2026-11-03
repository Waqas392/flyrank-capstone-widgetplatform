"""HTTP helpers: client IP, bounded body reading, JSON parsing."""
from __future__ import annotations

import json

from fastapi import Request

from ..config import Settings
from ..errors import ApiError


def client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_proxy:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[-1].strip()  # last hop = the one our single trusted proxy appended
    return request.client.host if request.client else "unknown"


async def read_limited_body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > limit:
                raise ApiError(413, "payload_too_large", f"Request body exceeds {limit} bytes")
        except ValueError:
            raise ApiError(400, "bad_request", "Invalid Content-Length header")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise ApiError(413, "payload_too_large", f"Request body exceeds {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def parse_json_object(body: bytes) -> dict:
    try:
        obj = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ApiError(400, "invalid_json", "Request body must be valid JSON")
    if not isinstance(obj, dict):
        raise ApiError(400, "invalid_json", "Request body must be a JSON object")
    return obj
