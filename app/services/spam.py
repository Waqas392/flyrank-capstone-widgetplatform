"""Spam controls: honeypot field, too-fast-to-be-human timing, link stuffing."""
from __future__ import annotations

import re

_URL = re.compile(r"https?://", re.I)


def check_spam(*, honeypot_values: list, data: dict, elapsed_ms, min_fill_ms: int) -> str | None:
    """Returns a short reason string if the submission looks like spam, else None."""
    if any(v not in (None, "", False, 0) for v in honeypot_values):
        return "honeypot"
    if isinstance(elapsed_ms, (int, float)) and not isinstance(elapsed_ms, bool) and 0 <= elapsed_ms < min_fill_ms:
        return "too_fast"
    links = sum(len(_URL.findall(v)) for v in data.values() if isinstance(v, str))
    if links > 3:
        return "link_stuffing"
    return None
