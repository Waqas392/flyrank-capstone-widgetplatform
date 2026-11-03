"""CORS: public surface open to any site (incl. preflight); admin surface locked to known origins."""
from conftest import EVIL, ORIGIN, expect, expect_json_error, submit


def _pre(http, path, origin, method="POST", headers="content-type,idempotency-key"):
    return http.options(path, headers={"Origin": origin, "Access-Control-Request-Method": method, "Access-Control-Request-Headers": headers})


def test_preflight_submissions_from_customer_site(http):
    """OPTIONS /submissions (preflight) -> 204 + Allow-Origin/Methods/Headers"""
    r = expect(_pre(http, "/submissions", ORIGIN), 204)
    assert r.headers.get("access-control-allow-origin") in ("*", ORIGIN)
    assert "POST" in r.headers.get("access-control-allow-methods", "")
    allow = r.headers.get("access-control-allow-headers", "").lower()
    assert "content-type" in allow and "idempotency-key" in allow, f"allow-headers={allow!r}"


def test_preflight_works_for_arbitrary_customer_origin(http):
    """OPTIONS /submissions from a random third-party site -> allowed (any site may embed)"""
    expect(_pre(http, "/submissions", "https://some-random-customer.example"), 204)


def test_preflight_does_not_allow_unlisted_headers(http):
    """Preflight allow-list does not blindly echo arbitrary request headers"""
    r = _pre(http, "/submissions", ORIGIN, headers="x-evil-header")
    assert "x-evil-header" not in r.headers.get("access-control-allow-headers", "").lower()


def test_post_response_has_cors_header(http, wA):
    """POST /submissions response carries Access-Control-Allow-Origin"""
    r = expect(submit(http, wA["id"]), 201)
    assert r.headers.get("access-control-allow-origin") in ("*", ORIGIN)


def test_error_responses_also_have_cors_header(http, wA):
    """422 and 404 errors carry CORS headers too (so the widget JS can read the message)"""
    bad = submit(http, wA["id"], {"email": "nope"})
    expect_json_error(bad, 422)
    assert bad.headers.get("access-control-allow-origin") in ("*", ORIGIN), "422 missing ACAO"
    nf = http.get("/widgets/nope-nope/config", headers={"Origin": ORIGIN})
    assert nf.status_code == 404 and nf.headers.get("access-control-allow-origin") in ("*", ORIGIN), "404 missing ACAO"


def test_config_and_loader_have_cors_header(http, wA):
    """GET config + widget.js + bundle carry Access-Control-Allow-Origin"""
    for path in (f"/widgets/{wA['id']}/config", "/widget.js"):
        r = expect(http.get(path, headers={"Origin": ORIGIN}), 200)
        assert r.headers.get("access-control-allow-origin") in ("*", ORIGIN), f"{path} lacks ACAO"


def test_admin_preflight_blocked_for_evil_origin(http):
    """OPTIONS /api/widgets from an unlisted origin -> refused, no Allow-Origin"""
    r = _pre(http, "/api/widgets", EVIL, method="GET", headers="authorization")
    assert r.status_code in (403, 400, 404) or not r.headers.get("access-control-allow-origin"), f"HTTP {r.status_code}"
    assert not r.headers.get("access-control-allow-origin"), "evil origin was granted access to the admin API"


def test_admin_preflight_allowed_for_dashboard_origin(http):
    """OPTIONS /api/widgets from the allow-listed dashboard origin -> 204 echoing that origin"""
    r = expect(_pre(http, "/api/widgets", ORIGIN, method="GET", headers="authorization"), 204)
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert "authorization" in r.headers.get("access-control-allow-headers", "").lower()


def test_admin_responses_never_wildcard_and_never_for_evil(http, hA):
    """Authenticated /api/* response: ACAO is the exact allowed origin, never '*', absent for evil origin"""
    ok = expect(http.get("/api/widgets", headers={**hA, "Origin": ORIGIN}), 200)
    assert ok.headers.get("access-control-allow-origin") == ORIGIN
    bad = expect(http.get("/api/widgets", headers={**hA, "Origin": EVIL}), 200)
    assert bad.headers.get("access-control-allow-origin") is None, "admin API echoes/grants an unlisted origin"
