from .conftest import submit

ORIGIN = "http://localhost:5500"


def test_preflight_for_submissions_is_answered(client):
    r = client.options("/submissions", headers={
        "Origin": ORIGIN, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,idempotency-key"})
    assert r.status_code == 204
    assert r.headers["access-control-allow-origin"] == "*"
    assert "POST" in r.headers["access-control-allow-methods"]
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "content-type" in allowed and "idempotency-key" in allowed
    assert r.headers["access-control-max-age"] == "86400"


def test_actual_responses_carry_cors_headers_even_on_errors(client, widget):
    ok = submit(client, widget["id"])
    assert ok.status_code == 201 and ok.headers["access-control-allow-origin"] == "*"
    bad = submit(client, widget["id"], data={"email": "nope"})
    assert bad.status_code == 422 and bad.headers["access-control-allow-origin"] == "*"
    cfg = client.get(f"/widgets/{widget['id']}/config", headers={"Origin": ORIGIN})
    assert cfg.headers["access-control-allow-origin"] == "*"
    js = client.get("/widget.js?id=x", headers={"Origin": ORIGIN})
    assert js.headers["access-control-allow-origin"] == "*"


def test_admin_api_is_not_open_to_arbitrary_origins(client, auth):
    evil = {"Origin": "https://evil.example"}
    r = client.options("/api/widgets", headers={**evil, "Access-Control-Request-Method": "GET"})
    assert r.status_code == 403 and "access-control-allow-origin" not in r.headers
    r = client.get("/api/widgets", headers={**auth, **evil})
    assert "access-control-allow-origin" not in r.headers
    good = client.get("/api/widgets", headers={**auth, "Origin": ORIGIN})
    assert good.headers["access-control-allow-origin"] == ORIGIN
    pre = client.options("/api/widgets", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET",
                                                  "Access-Control-Request-Headers": "authorization"})
    assert pre.status_code == 204 and "Authorization" in pre.headers["access-control-allow-headers"]
