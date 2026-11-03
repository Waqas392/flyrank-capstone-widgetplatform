"""Misc hardening: errors are JSON (never HTML/stack traces), odd URLs don't 500."""
import pytest

from conftest import expect


@pytest.mark.parametrize("path", ["/nope", "/api/nope", "/widgets/%00/config", "/widgets/..%2f..%2fetc%2fpasswd/config",
                                  "/widgets/" + "a" * 3000 + "/config", "/assets/", "/submissions/123"])
def test_odd_urls_never_500(http, path):
    """GET odd/hostile URLs -> 4xx, never 5xx"""
    r = http.get(path)
    assert r.status_code < 500, f"{path[:60]} -> {r.status_code}"


def test_404_is_json(http):
    """Unknown route -> JSON 404 error envelope"""
    r = expect(http.get("/definitely/not/here"), 404)
    assert "json" in r.headers["content-type"] and "error" in r.json()


def test_405_is_json(http):
    """Wrong method on /submissions -> JSON 405 error envelope"""
    r = expect(http.delete("/submissions"), 405)
    assert "error" in r.json()


def test_no_stack_trace_or_server_banner_in_errors(http):
    """Error bodies contain no Python tracebacks / file paths"""
    for r in (http.post("/api/auth/login", content=b"{bad", headers={"Content-Type": "application/json"}),
              http.get("/widgets/%00/config"), http.get("/api/dashboard/stats?days=abc", headers={"Authorization": "Bearer x"})):
        assert "Traceback" not in r.text and "/srv/" not in r.text and "site-packages" not in r.text, r.text[:200]


def test_nosniff_header_present(http):
    """Responses carry X-Content-Type-Options: nosniff"""
    assert http.get("/healthz").headers.get("x-content-type-options") == "nosniff"


def test_healthz_survives_after_all_the_abuse(http):
    """GET /healthz still 200 after the fuzzing above"""
    expect(http.get("/healthz"), 200)


@pytest.mark.parametrize("path", ["/api/widgets/%00", "/api/widgets/%00/embed", "/api/dashboard/submissions/%00",
                                  "/api/dashboard/submissions?widget_id=%00", "/api/dashboard/stats?widget_id=%00"])
def test_nul_byte_in_authed_ids_never_500(http, hA, path):
    """Authenticated routes given a NUL byte in an id -> 404/422, never 500 (Postgres rejects NUL)"""
    r = http.get(path, headers=hA)
    assert 400 <= r.status_code < 500, f"{path} -> {r.status_code}: {r.text[:150]}"
