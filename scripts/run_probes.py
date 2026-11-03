"""Runs the six acceptance probes against a live server and prints a transcript.

    python -m scripts.run_probes --base http://localhost:8000

Needs the demo seed (scripts/seed.py) and DEBUG_ENDPOINTS=1 with GEO_MODE=mock (fault injection).
"""
from __future__ import annotations

import argparse
import sys
import time

import httpx

ORIGIN = "http://localhost:5500"  # the "customer site"
GOOD = {"name": "Ada", "email": "ada@example.com", "message": "Hello from the second origin"}
results: list[tuple[str, bool]] = []


def line(msg=""):
    print(msg, flush=True)


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok))
    line(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def post(c, base, data=None, headers=None, **extra):
    body = {"widget_id": "demo-contact", "data": GOOD if data is None else data, **extra}
    return c.post(f"{base}/submissions", json=body, headers={"Origin": ORIGIN, **(headers or {})})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    c = httpx.Client(timeout=15)
    tok = c.post(f"{base}/api/auth/login", json={"email": "demo@example.com", "password": "demo-password-123"}).json()["token"]
    auth = {"Authorization": f"Bearer {tok}"}
    c.post(f"{base}/_debug/faults", json={"geo_down": [], "email_fail": False})

    line("PROBE 1 - cross-origin submission -> stored, 2xx, visible via dashboard API")
    pre = c.options(f"{base}/submissions", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,idempotency-key"})
    line(f"  OPTIONS /submissions -> {pre.status_code} ACAO={pre.headers.get('access-control-allow-origin')} ACAH={pre.headers.get('access-control-allow-headers')}")
    r = post(c, base, headers={"Idempotency-Key": f"probe-{time.time()}"})
    line(f"  POST /submissions -> {r.status_code} {r.text}")
    d = c.get(f"{base}/api/dashboard/submissions?widget_id=demo-contact&limit=1", headers=auth).json()
    line(f"  GET dashboard -> newest: {d['items'][0]['id']} geo={d['items'][0]['geo_provider']}")
    check("preflight answered", pre.status_code == 204 and pre.headers.get("access-control-allow-origin") == "*")
    check("submission 2xx with CORS header", r.status_code == 201 and r.headers.get("access-control-allow-origin") == "*")
    check("visible in dashboard", d["items"][0]["id"] == r.json()["id"])

    line("\nPROBE 2 - malformed and oversized payloads -> clean 4xx JSON, never 500")
    time.sleep(1)
    m = c.post(f"{base}/submissions", content=b"{oops", headers={"Content-Type": "application/json"})
    o = c.post(f"{base}/submissions", content=b'{"widget_id":"demo-contact","data":{"message":"' + b"x" * 60000 + b'"}}', headers={"Content-Type": "application/json"})
    v = post(c, base, data={"email": "not-an-email"})
    for label, resp in (("malformed JSON", m), ("oversized body", o), ("invalid field", v)):
        line(f"  {label} -> {resp.status_code} {resp.text[:140]}")
    check("malformed -> 400 JSON", m.status_code == 400 and "error" in m.json())
    check("oversized -> 413 JSON", o.status_code == 413 and "error" in o.json())
    check("invalid field -> 422 JSON", v.status_code == 422 and "error" in v.json())

    line("\nPROBE 3 - burst -> 429s appear, a normal request right after still succeeds")
    time.sleep(2)
    codes = [post(c, base).status_code for _ in range(40)]
    line(f"  40 rapid POSTs -> {codes.count(201)}x 201, {codes.count(429)}x 429")
    cfg = c.get(f"{base}/widgets/demo-contact/config")
    health = c.get(f"{base}/healthz")
    line(f"  GET config during/after flood -> {cfg.status_code}; /healthz -> {health.status_code}")
    time.sleep(1.5)
    after = post(c, base)
    line(f"  normal POST 1.5s later -> {after.status_code}")
    check("429s returned", 429 in codes)
    check("service stays up (config + health 200)", cfg.status_code == 200 and health.status_code == 200)
    check("normal request succeeds afterwards", after.status_code == 201)

    line("\nPROBE 4 - geo provider fallback")
    time.sleep(3)
    res = {}
    for label, down in (("all up", []), ("A down", ["a"]), ("A+B down", ["a", "b"])):
        c.post(f"{base}/_debug/faults", json={"geo_down": down})
        r = post(c, base, data={**GOOD, "name": label})
        res[label] = r
        time.sleep(0.6)
    c.post(f"{base}/_debug/faults", json={"geo_down": []})
    items = {i["data"]["name"]: i for i in c.get(f"{base}/api/dashboard/submissions?widget_id=demo-contact&limit=20", headers=auth).json()["items"]}
    for label in res:
        i = items.get(label, {})
        line(f"  {label:9} -> HTTP {res[label].status_code}, stored geo_provider={i.get('geo_provider')} city={i.get('city')}")
    check("A up -> enriched by A", items["all up"]["geo_provider"] == "mock-a")
    check("A down -> enriched by B", items["A down"]["geo_provider"] == "mock-b")
    check("both down -> stored without geo", res["A+B down"].status_code == 201 and items["A+B down"]["geo_provider"] is None)

    line("\nPROBE 5 - failing email side effect does not block the submission")
    c.post(f"{base}/_debug/faults", json={"email_fail": True})
    r = post(c, base, data={**GOOD, "name": "email-down"})
    line(f"  POST with email forced to fail -> {r.status_code} {r.text}")
    drained = c.post(f"{base}/_debug/drain-jobs").json()
    line(f"  worker drain -> {drained}; /healthz jobs={c.get(f'{base}/healthz').json()['jobs']}")
    stored = any(i["id"] == r.json()["id"] for i in c.get(f"{base}/api/dashboard/submissions?widget_id=demo-contact&limit=20", headers=auth).json()["items"])
    c.post(f"{base}/_debug/faults", json={"email_fail": False})
    check("submission returned 201", r.status_code == 201)
    check("submission stored despite email failure", stored)

    line("\nPROBE 6 - honeypot filled like a bot")
    time.sleep(1)
    before = c.get(f"{base}/api/dashboard/stats", headers=auth).json()["totals"]
    r = post(c, base, data={**GOOD, "name": "BOT", "website": "http://buy-pills.example"})
    after_t = c.get(f"{base}/api/dashboard/stats", headers=auth).json()["totals"]
    names = [i["data"].get("name") for i in c.get(f"{base}/api/dashboard/submissions?widget_id=demo-contact&limit=100", headers=auth).json()["items"]]
    line(f"  POST with website=... -> {r.status_code} {r.text}")
    line(f"  spam_blocked {before['spam_blocked']} -> {after_t['spam_blocked']}; 'BOT' stored? {'BOT' in names}")
    check("bot row not stored", "BOT" not in names)
    check("spam counted", after_t["spam_blocked"] == before["spam_blocked"] + 1)

    failed = [n for n, ok in results if not ok]
    line(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
