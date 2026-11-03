"""Abuse protection: a flood gets 429s, the service stays up, normal traffic recovers."""
import time

from conftest import ORIGIN, expect, expect_json_error, raw_submit, submit, GOOD


def test_burst_gets_429_and_service_stays_up(http, make_widget, hA):
    """40 rapid POSTs -> some 429 (with Retry-After + JSON + CORS), config/health stay 200, normal request works afterwards"""
    w = make_widget(hA)
    time.sleep(6)                       # let the per-IP bucket refill to full
    codes, tooMany = [], None
    for _ in range(40):
        r = http.post("/submissions", json={"widget_id": w["id"], "data": GOOD}, headers={"Origin": ORIGIN})
        codes.append(r.status_code)
        if r.status_code == 429 and tooMany is None:
            tooMany = r
    assert 429 in codes, f"no 429 in 40 rapid requests: {sorted(set(codes))}"
    assert codes.count(201) < 25, f"limiter let {codes.count(201)}/40 through"
    assert set(codes) <= {201, 429}, f"unexpected statuses under load: {sorted(set(codes))}"
    expect_json_error(tooMany, 429, code="rate_limited")
    assert int(tooMany.headers.get("retry-after", "0")) >= 1, "429 lacks Retry-After"
    assert tooMany.headers.get("access-control-allow-origin") in ("*", ORIGIN), "429 lacks CORS header (browser can't read it)"

    # service still serves everyone else while flooded
    expect(http.get(f"/widgets/{w['id']}/config"), 200)
    expect(http.get("/healthz"), 200)

    # and a normal request succeeds once the limiter refills
    time.sleep(3)
    r = http.post("/submissions", json={"widget_id": w["id"], "data": GOOD}, headers={"Origin": ORIGIN})
    expect(r, 201)


def test_junk_requests_also_count_against_the_limit(http, make_widget, hA):
    """A flood of INVALID requests is rate limited too (can't hammer validation for free)"""
    time.sleep(6)
    codes = [http.post("/submissions", content=b"{bad", headers={"Content-Type": "application/json", "Origin": ORIGIN}).status_code
             for _ in range(30)]
    assert 429 in codes, f"junk flood never limited: {sorted(set(codes))}"
    assert all(c in (400, 429) for c in codes), sorted(set(codes))
    time.sleep(4)
