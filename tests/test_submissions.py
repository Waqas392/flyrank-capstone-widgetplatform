import json
import time

import pytest

from .conftest import fresh_ip, submit

GOOD = {"name": "Ada", "email": "ada@example.com", "message": "Hello"}


def test_valid_submission_is_stored_enriched_and_visible_in_dashboard(client, auth, widget):
    r = submit(client, widget["id"], GOOD)
    assert r.status_code == 201 and r.json()["ok"] is True
    items = client.get("/api/dashboard/submissions", headers=auth).json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == r.json()["id"] and items[0]["widget_id"] == widget["id"]
    assert items[0]["data"] == GOOD
    assert items[0]["geo_provider"] == "mock-a" and items[0]["country"] == "Mockland"


def test_raw_ip_is_never_stored(client, ctx, widget):
    ip = "198.51.100.77"
    assert submit(client, widget["id"], GOOD, ip=ip).status_code == 201
    from sqlalchemy import text
    with ctx.engine.connect() as c:
        row = c.execute(text("select * from submissions")).mappings().one()
    assert ip not in json.dumps({k: str(v) for k, v in row.items()})


def test_malformed_json_is_400(client, widget):
    for raw in (b"{not json", b"", b"[1,2]", b'"str"', b"null", b"\xff\xfe\x00"):
        r = client.post("/submissions", content=raw, headers={"Content-Type": "application/json", "X-Forwarded-For": fresh_ip()})
        assert r.status_code == 400, (raw, r.status_code)
        assert r.json()["error"]["code"] == "invalid_json"


def test_oversized_payload_is_413(client, widget):
    big = json.dumps({"widget_id": widget["id"], "data": {"message": "x" * 50_000}})
    r = client.post("/submissions", content=big, headers={"Content-Type": "application/json", "X-Forwarded-For": fresh_ip()})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"

    def chunks():  # chunked upload with no Content-Length must be capped too
        for _ in range(10):
            yield b"a" * 5000
    r = client.post("/submissions", content=chunks(), headers={"Content-Type": "application/json", "X-Forwarded-For": fresh_ip()})
    assert r.status_code == 413


def test_oversized_field_is_422_not_500(client, widget):
    r = submit(client, widget["id"], {**GOOD, "message": "x" * 2001})
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["field"] == "message"


@pytest.mark.parametrize("data", [
    {}, {"email": "nope"}, {**GOOD, "email": "a@b"}, {**GOOD, "extra": "field"}, {**GOOD, "name": ""},
    {**GOOD, "name": 123}, {**GOOD, "name": ["x"]}, {**GOOD, "name": {"a": 1}}, {**GOOD, "message": None},
])
def test_invalid_field_values_are_422(client, widget, data):
    r = submit(client, widget["id"], data)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error" and r.json()["error"]["details"]


@pytest.mark.parametrize("payload", [
    {}, {"widget_id": None}, {"widget_id": 5, "data": {}}, {"widget_id": "../../etc/passwd", "data": {}},
    {"widget_id": "x" * 200, "data": {}}, {"widget_id": "abc"}, {"widget_id": "abc", "data": []},
    {"widget_id": "abc", "data": "str"}, {"widget_id": "abc", "data": {str(i): i for i in range(100)}},
    {"widget_id": "'; DROP TABLE widgets;--", "data": {}},
])
def test_junk_envelopes_never_500(client, widget, payload):
    r = client.post("/submissions", json=payload, headers={"X-Forwarded-For": fresh_ip()})
    assert 400 <= r.status_code < 500, r.text
    assert "error" in r.json()


def test_unknown_widget_is_404_and_bad_idempotency_key_422(client, widget):
    assert submit(client, "doesnotexist", GOOD).status_code == 404
    assert submit(client, widget["id"], GOOD, headers={"Idempotency-Key": "x" * 300}).status_code == 422


def test_control_characters_are_stripped(client, auth, widget):
    submit(client, widget["id"], {**GOOD, "name": "Ada\x00\x07Lovelace"})
    assert client.get("/api/dashboard/submissions", headers=auth).json()["items"][0]["data"]["name"] == "AdaLovelace"


def test_idempotency_key_stores_once_and_enqueues_one_email(client, auth, widget, ctx):
    h = {"Idempotency-Key": "form-render-123"}
    r1 = submit(client, widget["id"], GOOD, headers=h)
    r2 = submit(client, widget["id"], GOOD, headers=h)
    assert r1.status_code == 201 and r2.status_code == 200
    assert r2.json()["id"] == r1.json()["id"] and r2.json()["duplicate"] is True
    assert client.get("/api/dashboard/submissions", headers=auth).json()["total"] == 1
    assert ctx.worker.drain() == 1  # exactly one confirmation email job


# ---------------- abuse protection ----------------
def test_burst_gets_429s_service_stays_up_and_client_recovers(client, widget):
    attacker = fresh_ip()
    codes = [submit(client, widget["id"], GOOD, ip=attacker).status_code for _ in range(40)]
    assert 201 in codes and 429 in codes
    assert codes.count(201) <= 12  # burst capacity (10) + a little refill during the loop
    r = submit(client, widget["id"], GOOD, ip=attacker)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert r.json()["error"]["code"] == "rate_limited"
    # the service is still healthy for everyone else
    assert submit(client, widget["id"], GOOD).status_code == 201  # another visitor
    assert client.get(f"/widgets/{widget['id']}/config").status_code == 200
    assert client.get("/healthz").status_code == 200
    time.sleep(1.2)  # bucket refills (2 tokens/sec) -> the attacker's IP recovers by itself
    assert submit(client, widget["id"], GOOD, ip=attacker).status_code == 201


def test_per_widget_limit_protects_owner_from_distributed_flood(client, ctx, widget):
    ctx.widget_limiter.capacity = 5
    ctx.widget_limiter.refill = 0.01
    codes = [submit(client, widget["id"], GOOD).status_code for _ in range(12)]  # 12 different IPs
    assert codes.count(201) == 5 and codes.count(429) == 7


def test_honeypot_blocks_bot_silently(client, auth, widget):
    r = submit(client, widget["id"], {**GOOD, "website": "http://spam.example"})
    assert r.status_code == 201 and r.json()["ok"] is True  # bot is told nothing
    assert client.get("/api/dashboard/submissions", headers=auth).json()["total"] == 0
    assert client.get("/api/dashboard/stats", headers=auth).json()["totals"]["spam_blocked"] == 1
    # top-level honeypot also counts, and bad data doesn't reveal it either
    r = submit(client, widget["id"], {"email": "nope"}, website="x")
    assert r.status_code == 201
    assert client.get("/api/dashboard/stats", headers=auth).json()["totals"]["spam_blocked"] == 2


def test_other_spam_heuristics(client, auth, widget):
    assert submit(client, widget["id"], GOOD, elapsed_ms=200).status_code == 201   # too fast -> dropped
    assert submit(client, widget["id"], {**GOOD, "message": "http://a.co http://b.co http://c.co http://d.co"}).status_code == 201
    assert submit(client, widget["id"], GOOD, elapsed_ms=9000).status_code == 201  # human-speed -> kept
    s = client.get("/api/dashboard/stats", headers=auth).json()["totals"]
    assert s["spam_blocked"] == 2 and s["submissions"] == 1


# ---------------- resilience ----------------
def _set_faults(client, **body):
    assert client.post("/_debug/faults", json=body).status_code == 200


def test_geo_fallback_chain(client, auth, widget):
    submit(client, widget["id"], {**GOOD, "name": "all-up"})
    _set_faults(client, geo_down=["a"])
    submit(client, widget["id"], {**GOOD, "name": "a-down"})
    _set_faults(client, geo_down=["a", "b"])
    r = submit(client, widget["id"], {**GOOD, "name": "both-down"})
    assert r.status_code == 201  # degrade, never fail
    by_name = {i["data"]["name"]: i for i in client.get("/api/dashboard/submissions", headers=auth).json()["items"]}
    assert by_name["all-up"]["geo_provider"] == "mock-a"
    assert by_name["a-down"]["geo_provider"] == "mock-b" and by_name["a-down"]["city"] == "Beta City"
    assert by_name["both-down"]["geo_provider"] is None and by_name["both-down"]["country"] is None


def test_live_geo_chain_survives_real_provider_errors(monkeypatch):
    import asyncio
    from app.services import geo

    class Boom:
        name = "boom"
        async def lookup(self, ip):
            raise RuntimeError("network down")

    class Slow:
        name = "slow"
        async def lookup(self, ip):
            await asyncio.sleep(5)

    class Ok:
        name = "ok"
        async def lookup(self, ip):
            return geo.GeoResult("Pakistan", "Peshawar", "ok")

    assert asyncio.run(geo.GeoChain([Boom(), Slow(), Ok()], 0.05, False).enrich("8.8.8.8")).provider == "ok"
    assert asyncio.run(geo.GeoChain([Boom(), Slow()], 0.05, False).enrich("8.8.8.8")) is None
    assert asyncio.run(geo.GeoChain([Ok()], 0.05, True).enrich("10.0.0.1")) is None  # private IP: skip lookups


def test_failing_email_does_not_block_submission(client, auth, widget, ctx):
    _set_faults(client, email_fail=True)
    r = submit(client, widget["id"], GOOD)
    assert r.status_code == 201
    assert client.get("/api/dashboard/submissions", headers=auth).json()["total"] == 1
    ctx.worker.drain()  # worker retries with backoff, then gives up and raises an ALERT
    from sqlalchemy import text
    with ctx.engine.connect() as c:
        job = c.execute(text("select status, attempts, last_error from jobs")).one()
    assert job.status == "failed" and job.attempts == 3 and "fault injected" in job.last_error
    assert client.get("/healthz").json()["jobs"] == {"failed": 1}
    assert client.get("/api/dashboard/submissions", headers=auth).json()["total"] == 1  # still stored


def test_job_retries_then_succeeds_when_email_recovers(client, widget, ctx):
    _set_faults(client, email_fail=True)
    submit(client, widget["id"], GOOD)
    assert ctx.worker.process_one() is True          # attempt 1 fails -> back to pending
    _set_faults(client, email_fail=False)
    ctx.worker.drain()
    assert client.get("/healthz").json()["jobs"] == {"done": 1}


def test_job_alert_is_logged_on_permanent_failure(client, widget, ctx, caplog):
    _set_faults(client, email_fail=True)
    submit(client, widget["id"], GOOD)
    with caplog.at_level("ERROR"):
        ctx.worker.drain()
    assert any("ALERT" in r.message and "failed permanently" in r.message for r in caplog.records)
