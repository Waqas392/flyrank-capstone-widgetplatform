"""Spam controls: honeypot, too-fast timing, link stuffing. Blocked spam is never stored and is counted."""
from conftest import GOOD, dash_items, expect, submit


def _spam_count(http, hA, wid) -> int:
    return http.get("/api/dashboard/stats", params={"widget_id": wid}, headers=hA).json()["totals"]["spam_blocked"]


def _names(http, hA, wid):
    return [i["data"].get("name") for i in dash_items(http, hA, wid)]


def test_honeypot_filled_is_dropped_and_counted(http, hA, wA):
    """Filled honeypot field -> not stored, counted as spam, bot still sees a normal-looking response"""
    before = _spam_count(http, hA, wA["id"])
    r = submit(http, wA["id"], {**GOOD, "name": "BOT-HP", "website": "http://buy-pills.example"})
    assert r.status_code in (200, 201, 202, 400, 422), f"unexpected HTTP {r.status_code}"
    assert "BOT-HP" not in _names(http, hA, wA["id"]), "honeypot submission was stored"
    assert _spam_count(http, hA, wA["id"]) == before + 1, "spam event was not counted"


def test_honeypot_response_does_not_reveal_the_trap(http, wA):
    """Honeypot hit gets no message mentioning 'honeypot'/'spam'/the field name"""
    r = submit(http, wA["id"], {**GOOD, "website": "x"})
    low = r.text.lower()
    assert "honeypot" not in low and "spam" not in low and "website" not in low, r.text


def test_honeypot_at_top_level_also_caught(http, hA, wA):
    """Bot putting the honeypot value outside 'data' is also dropped"""
    r = submit(http, wA["id"], {**GOOD, "name": "BOT-TOP"}, website="spam")
    assert r.status_code in (200, 201, 202, 400, 422)
    assert "BOT-TOP" not in _names(http, hA, wA["id"])


def test_too_fast_submission_blocked(http, hA, wA):
    """elapsed_ms=50 (faster than a human) -> not stored, counted"""
    before = _spam_count(http, hA, wA["id"])
    submit(http, wA["id"], {**GOOD, "name": "BOT-FAST"}, elapsed_ms=50)
    assert "BOT-FAST" not in _names(http, hA, wA["id"])
    assert _spam_count(http, hA, wA["id"]) == before + 1


def test_human_pace_submission_accepted(http, hA, wA):
    """elapsed_ms=8000 (human) -> stored normally"""
    r = expect(submit(http, wA["id"], {**GOOD, "name": "HUMAN"}, elapsed_ms=8000), 201)
    assert "HUMAN" in _names(http, hA, wA["id"])


def test_link_stuffing_blocked(http, hA, wA):
    """Message with 5 URLs -> not stored, counted"""
    before = _spam_count(http, hA, wA["id"])
    msg = " ".join(f"http://spam{i}.example" for i in range(5))
    submit(http, wA["id"], {**GOOD, "name": "BOT-LINKS", "message": msg})
    assert "BOT-LINKS" not in _names(http, hA, wA["id"])
    assert _spam_count(http, hA, wA["id"]) == before + 1


def test_one_legit_link_is_fine(http, hA, wA):
    """A message with a single URL is not treated as spam"""
    expect(submit(http, wA["id"], {**GOOD, "name": "ONE-LINK", "message": "see https://example.com please"}), 201)
    assert "ONE-LINK" in _names(http, hA, wA["id"])


def test_custom_honeypot_name_respected(http, hA, make_widget):
    """Widget with its own honeypot_field name: filling it is caught"""
    w = make_widget(hA, honeypot_field="confirm_url")
    before = _spam_count(http, hA, w["id"])
    submit(http, w["id"], {**GOOD, "name": "BOT-CUSTOM", "confirm_url": "x"})
    assert "BOT-CUSTOM" not in _names(http, hA, w["id"])
    assert _spam_count(http, hA, w["id"]) == before + 1
