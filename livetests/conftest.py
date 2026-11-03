"""Live end-to-end test harness for the Widget Platform.

Runs against an ALREADY RUNNING stack (docker compose up). It talks to the real HTTP API,
never imports the app, and changes no application behaviour.

Environment (all optional):
  LIVE_BASE_URL   API base URL as seen by the test runner     (default http://localhost:8000)
  LIVE_SITE_URL   customer-site URL as seen by the runner     (default http://localhost:5500)
  LIVE_ORIGIN     value sent as the browser "Origin" header   (default http://localhost:5500)

Test data: two throw-away owners (livetest-a / livetest-b) and widgets created per test, all
deleted at the end (submissions cascade). The seeded demo owner's data is never modified.
"""
from __future__ import annotations

import html
import os
import re
import time
from datetime import datetime
from pathlib import Path

import httpx
import pytest

BASE = os.getenv("LIVE_BASE_URL", "http://localhost:8000").rstrip("/")
SITE = os.getenv("LIVE_SITE_URL", "http://localhost:5500").rstrip("/")
ORIGIN = os.getenv("LIVE_ORIGIN", "http://localhost:5500").rstrip("/")
EVIL = "http://evil.example"

DEMO = ("demo@example.com", "demo-password-123")
TENANT_A = ("livetest-a@example.com", "livetest-pass-A-1")
TENANT_B = ("livetest-b@example.com", "livetest-pass-B-1")

GOOD = {"name": "Ada Lovelace", "email": "ada@example.com", "message": "Hello from the live test suite"}

# --------------------------------------------------------------------------------------
# HTTP helpers (rate-limit aware: the API allows ~2 submissions/s per IP, 1 login per 10 s)
# --------------------------------------------------------------------------------------
_last_ip_post = [0.0]


def _sleep_for_retry(r: httpx.Response, cap: float = 15.0) -> None:
    try:
        wait = float(r.headers.get("retry-after", "1"))
    except ValueError:
        wait = 1.0
    time.sleep(min(wait + 0.3, cap))


def pace(gap: float = 0.6) -> None:
    """Keep under the per-IP bucket (refill 2/s) so tests don't trip it by accident."""
    d = time.monotonic() - _last_ip_post[0]
    if d < gap:
        time.sleep(gap - d)
    _last_ip_post[0] = time.monotonic()


def auth_call(http: httpx.Client, path: str, creds: tuple[str, str], tries: int = 8) -> httpx.Response:
    """POST to an auth endpoint; waits out the (deliberately strict) auth rate limit."""
    r = None
    for _ in range(tries):
        r = http.post(path, json={"email": creds[0], "password": creds[1]})
        if r.status_code != 429:
            return r
        _sleep_for_retry(r)
    return r


def submit(http, widget_id, data=None, *, headers=None, retry=True, **extra) -> httpx.Response:
    """POST /submissions the way a browser on the customer site would."""
    body = {"widget_id": widget_id, "data": GOOD if data is None else data, **extra}
    h = {"Origin": ORIGIN, **(headers or {})}
    return raw_submit(http, json=body, headers=h, retry=retry)


def raw_submit(http, *, retry=True, headers=None, **kw) -> httpx.Response:
    h = {"Origin": ORIGIN, **(headers or {})}
    for _ in range(6):
        pace()
        r = http.post("/submissions", headers=h, **kw)
        if r.status_code != 429 or not retry:
            return r
        _sleep_for_retry(r)
    return r


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def dash_items(http, headers, widget_id, limit=100) -> list[dict]:
    r = http.get("/api/dashboard/submissions", params={"widget_id": widget_id, "limit": limit}, headers=headers)
    assert r.status_code == 200, f"dashboard list failed: {r.status_code} {r.text[:200]}"
    return r.json()["items"]


def expect(r: httpx.Response, *codes: int) -> httpx.Response:
    assert r.status_code in codes, f"expected HTTP {'/'.join(map(str, codes))}, got {r.status_code}: {r.text[:240]}"
    return r


def expect_json_error(r: httpx.Response, *codes: int, code: str | None = None) -> dict:
    expect(r, *codes)
    try:
        body = r.json()
    except ValueError:
        raise AssertionError(f"error response is not JSON (HTTP {r.status_code}): {r.text[:160]!r}")
    assert isinstance(body, dict) and "error" in body, f"missing {{'error': ...}} envelope: {body}"
    if code:
        assert body["error"].get("code") == code, f"expected error.code={code!r}, got {body['error']}"
    return body


def site_get(path: str) -> httpx.Response:
    """Fetch a page from the customer-site container.

    If LIVE_SITE_URL was set explicitly (run_tests.bat does this) an unreachable site is a real FAILURE.
    If it was left at the default (e.g. pytest run by hand inside the api container, where localhost:5500
    is not the customer site) the check is SKIPPED with an explanation instead of failing.
    """
    try:
        return httpx.get(f"{SITE}{path}", timeout=10)
    except httpx.TransportError as exc:
        if os.getenv("LIVE_SITE_URL"):
            raise
        pytest.skip(f"customer site not reachable at {SITE} ({type(exc).__name__}). "
                    "Run run_tests.bat, or set LIVE_SITE_URL=http://customer-site:5500 when inside Docker.")


# --------------------------------------------------------------------------------------
# Session fixtures
# --------------------------------------------------------------------------------------
@pytest.fixture(scope="session")
def http():
    c = httpx.Client(base_url=BASE, timeout=20)
    try:
        r = c.get("/healthz")
        assert r.status_code == 200
    except Exception as exc:  # noqa: BLE001
        pytest.exit(
            f"\n\nCannot reach the API at {BASE} ({type(exc).__name__}).\n"
            "Start the stack first:  docker compose up --build   (then wait for 'Application startup complete')\n",
            returncode=3,
        )
    yield c
    c.close()


@pytest.fixture(scope="session")
def debug_ok(http) -> bool:
    return http.get("/_debug/faults").status_code == 200


@pytest.fixture(scope="session", autouse=True)
def _clean_faults(http):
    def reset():
        try:
            http.post("/_debug/faults", json={"geo_down": [], "email_fail": False})
        except Exception:  # noqa: BLE001
            pass

    reset()
    yield
    reset()


def _login_or_register(http, creds) -> str:
    r = auth_call(http, "/api/auth/register", creds)
    if r.status_code == 409:
        r = auth_call(http, "/api/auth/login", creds)
    assert r.status_code in (200, 201), f"could not obtain a token for {creds[0]}: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def hA(http):
    return bearer(_login_or_register(http, TENANT_A))


@pytest.fixture(scope="session")
def hB(http):
    return bearer(_login_or_register(http, TENANT_B))


_created: list[tuple[str, dict]] = []


@pytest.fixture(scope="session", autouse=True)
def _cleanup_widgets(http):
    yield
    for wid, h in _created:
        try:
            http.delete(f"/api/widgets/{wid}", headers=h)
        except Exception:  # noqa: BLE001
            pass


@pytest.fixture()
def make_widget(http):
    def _make(headers, **overrides):
        body = {"type": "contact_form", "title": "LiveTest widget", **overrides}
        r = http.post("/api/widgets", json=body, headers=headers)
        assert r.status_code == 201, f"widget create failed: {r.status_code} {r.text[:300]}"
        w = r.json()
        _created.append((w["id"], headers))
        return w

    return _make


@pytest.fixture()
def wA(make_widget, hA):
    return make_widget(hA)


# --------------------------------------------------------------------------------------
# Report: console summary + report/report.html + report/report.md
# --------------------------------------------------------------------------------------
_META: dict[str, tuple[str, str]] = {}
_ROWS: list[dict] = []
_started = [time.time()]


def pytest_collection_modifyitems(items):
    for it in items:
        mod = it.module.__name__.split(".")[-1]
        m = re.match(r"test_(\d+)_(.+)", mod)
        cat = m.group(2).replace("_", " ").title() if m else mod
        doc = (it.function.__doc__ or it.name).strip().splitlines()[0]
        if getattr(it, "callspec", None):
            doc += f"  [{it.callspec.id}]"
        _META[it.nodeid] = (f"{m.group(1)} - {cat}" if m else cat, doc)


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome in ("skipped", "failed")):
        cat, doc = _META.get(report.nodeid, ("?", report.nodeid))
        status = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[report.outcome]
        detail = ""
        if report.outcome == "failed":
            lr = report.longrepr
            detail = getattr(getattr(lr, "reprcrash", None), "message", None) or str(lr)[-400:]
            detail = detail.replace("AssertionError: ", "")
        elif report.outcome == "skipped":
            lr = report.longrepr
            detail = (lr[2] if isinstance(lr, tuple) else str(lr)).replace("Skipped: ", "")
        _ROWS.append({"cat": cat, "check": doc, "status": status, "detail": detail[:600], "secs": report.duration})


def pytest_sessionfinish(session, exitstatus):
    if not _ROWS:
        return
    out = Path(__file__).parent / "report"
    out.mkdir(exist_ok=True)
    n = {k: sum(1 for r in _ROWS if r["status"] == k) for k in ("PASS", "FAIL", "SKIP")}
    total = len(_ROWS)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    secs = time.time() - _started[0]

    # ---- markdown ----
    md = [f"# Live test report\n", f"Run: {stamp} | target: {BASE} | origin: {ORIGIN} | {secs:.0f}s\n",
          f"**{n['PASS']} passed, {n['FAIL']} failed, {n['SKIP']} skipped** (of {total})\n"]
    cats: dict[str, list[dict]] = {}
    for r in _ROWS:
        cats.setdefault(r["cat"], []).append(r)
    for cat in sorted(cats):
        md.append(f"\n## {cat}\n\n| Result | Check | Detail |\n|---|---|---|")
        for r in cats[cat]:
            md.append(f"| {r['status']} | {r['check']} | {r['detail'].replace('|', '/').replace(chr(10), ' ')} |")
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")

    # ---- html ----
    color = {"PASS": "#0a7d33", "FAIL": "#b00020", "SKIP": "#8a6d00"}
    parts = [
        "<!doctype html><meta charset=utf-8><title>Live test report</title>",
        "<style>body{font:14px/1.45 system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#1a1a1a}"
        "table{border-collapse:collapse;width:100%;margin-bottom:22px}td,th{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}"
        "th{background:#f4f4f8}.b{display:inline-block;padding:2px 8px;border-radius:10px;color:#fff;font-weight:700;font-size:12px}"
        ".big{display:flex;gap:12px;margin:14px 0}.big div{padding:12px 20px;border-radius:8px;color:#fff;font-size:22px;font-weight:700}"
        "small{display:block;font-weight:400;font-size:12px}</style>",
        f"<h1>Live test report</h1><p>{html.escape(stamp)} &middot; target <code>{html.escape(BASE)}</code> &middot; "
        f"origin <code>{html.escape(ORIGIN)}</code> &middot; {secs:.0f}s</p>",
        f"<div class=big><div style='background:{color['PASS']}'>{n['PASS']}<small>passed</small></div>"
        f"<div style='background:{color['FAIL']}'>{n['FAIL']}<small>failed</small></div>"
        f"<div style='background:{color['SKIP']}'>{n['SKIP']}<small>skipped</small></div></div>",
    ]
    fails = [r for r in _ROWS if r["status"] == "FAIL"]
    if fails:
        parts.append("<h2>Failures</h2><table><tr><th>Area</th><th>Check</th><th>Why it failed</th></tr>")
        for r in fails:
            parts.append(f"<tr><td>{html.escape(r['cat'])}</td><td>{html.escape(r['check'])}</td><td>{html.escape(r['detail'])}</td></tr>")
        parts.append("</table>")
    for cat in sorted(cats):
        parts.append(f"<h2>{html.escape(cat)}</h2><table><tr><th width=70>Result</th><th>Check</th><th>Detail</th></tr>")
        for r in cats[cat]:
            parts.append(
                f"<tr><td><span class=b style='background:{color[r['status']]}'>{r['status']}</span></td>"
                f"<td>{html.escape(r['check'])}</td><td>{html.escape(r['detail'])}</td></tr>"
            )
        parts.append("</table>")
    (out / "report.html").write_text("\n".join(parts), encoding="utf-8")

    # ---- console ----
    print("\n" + "=" * 70)
    for cat in sorted(cats):
        rs = cats[cat]
        p = sum(1 for r in rs if r["status"] == "PASS")
        flag = "OK  " if all(r["status"] != "FAIL" for r in rs) else "FAIL"
        print(f"  [{flag}] {cat:<34} {p}/{len(rs)} passed")
    print("=" * 70)
    print(f"  TOTAL: {n['PASS']} passed, {n['FAIL']} failed, {n['SKIP']} skipped   ({secs:.0f}s)")
    for r in fails:
        print(f"   - FAIL [{r['cat']}] {r['check']}\n       {r['detail'][:300]}")
    print(f"  Report: {out / 'report.html'}")
    print("=" * 70)
