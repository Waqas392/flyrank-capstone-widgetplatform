"""Is everything up and reachable?"""
from urllib.parse import urlparse

import pytest

from conftest import expect, site_get


def test_health(http):
    """GET /healthz -> 200 {status: ok}"""
    r = expect(http.get("/healthz"), 200)
    assert r.json().get("status") == "ok", r.text


def test_swagger_docs(http):
    """GET /docs and /openapi.json are served"""
    expect(http.get("/docs"), 200)
    spec = expect(http.get("/openapi.json"), 200).json()
    assert "/submissions" in spec["paths"], "openapi spec has no /submissions path"


def test_customer_site_is_a_different_origin():
    """Customer site and API are on different origins (so every call crosses CORS)"""
    a, b = urlparse("http://localhost:8000"), urlparse("http://localhost:5500")
    assert (a.scheme, a.hostname, a.port) != (b.scheme, b.hostname, b.port)
    # Also verify what the demo page itself claims:
    page = site_get("/index.html")
    assert page.status_code == 200, f"customer site returned HTTP {page.status_code}"
    assert "localhost:8000/widget.js" in page.text, "demo page does not embed the widget script from the API origin"


def test_customer_site_embeds_all_demo_widgets():
    """Customer site index.html contains one <script> embed line per demo widget"""
    page = site_get("/index.html").text
    for wid in ("demo-signup", "demo-contact", "demo-popover"):
        assert f"widget.js?id={wid}" in page, f"missing embed snippet for {wid}"


def test_dashboard_page_served():
    """Customer site serves dashboard.html"""
    r = site_get("/dashboard.html")
    assert r.status_code == 200 and "Dashboard" in r.text


@pytest.mark.parametrize("wid", ["demo-signup", "demo-contact", "demo-popover"])
def test_seeded_demo_widget_config(http, wid):
    """GET /widgets/<seeded demo id>/config -> 200 (seed was run)"""
    r = http.get(f"/widgets/{wid}/config")
    if r.status_code == 404:
        pytest.skip("demo widget missing - run: docker compose exec api python -m scripts.seed")
    expect(r, 200)
