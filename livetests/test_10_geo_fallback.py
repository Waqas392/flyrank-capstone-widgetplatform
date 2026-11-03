"""IP -> geo enrichment fallback chain: A -> B -> store anyway. Uses the dev fault switches (mock providers)."""
import pytest

from conftest import dash_items, expect, submit


@pytest.fixture()
def faults(http, debug_ok):
    if not debug_ok:
        pytest.skip("/_debug/faults not available (DEBUG_ENDPOINTS=0)")

    def set_down(down):
        r = http.post("/_debug/faults", json={"geo_down": down})
        assert r.status_code == 200, r.text
        return r.json()

    yield set_down
    http.post("/_debug/faults", json={"geo_down": []})


def _stored(http, hA, wid, sid):
    return next(i for i in dash_items(http, hA, wid) if i["id"] == sid)


def _require_mock(row):
    if row["geo_provider"] and not str(row["geo_provider"]).startswith("mock-"):
        pytest.skip("API runs with GEO_MODE=live; fallback proof needs GEO_MODE=mock")


def test_provider_a_used_when_healthy(http, hA, wA, faults):
    """Both providers up -> submission enriched by provider A"""
    faults([])
    r = expect(submit(http, wA["id"]), 201)
    row = _stored(http, hA, wA["id"], r.json()["id"])
    _require_mock(row)
    assert row["geo_provider"] == "mock-a" and row["country"], row


def test_provider_b_answers_when_a_down(http, hA, wA, faults):
    """Provider A down -> 201 and enriched by provider B"""
    assert faults(["a"])["geo_down"] == ["a"]
    r = expect(submit(http, wA["id"]), 201)
    row = _stored(http, hA, wA["id"], r.json()["id"])
    _require_mock(row)
    assert row["geo_provider"] == "mock-b" and row["country"], row


def test_both_down_still_stores_without_geo(http, hA, wA, faults):
    """Providers A+B down -> still 201, stored, geo fields empty"""
    faults(["a", "b"])
    r = expect(submit(http, wA["id"]), 201)
    row = _stored(http, hA, wA["id"], r.json()["id"])
    assert row["geo_provider"] is None and row["country"] is None and row["city"] is None, row


def test_only_b_down_uses_a(http, hA, wA, faults):
    """Provider B down (A up) -> A still answers"""
    faults(["b"])
    r = expect(submit(http, wA["id"]), 201)
    row = _stored(http, hA, wA["id"], r.json()["id"])
    _require_mock(row)
    assert row["geo_provider"] == "mock-a"


def test_recovery_after_outage(http, hA, wA, faults):
    """After the outage ends, enrichment resumes"""
    faults(["a", "b"])
    expect(submit(http, wA["id"], {**{"name": "during", "email": "a@example.com", "message": "m"}}), 201)
    faults([])
    r = expect(submit(http, wA["id"], {"name": "after", "email": "a@example.com", "message": "m"}), 201)
    row = _stored(http, hA, wA["id"], r.json()["id"])
    assert row["geo_provider"] is not None, "enrichment did not resume"


def test_geo_outage_is_reflected_in_stats(http, hA, make_widget, faults):
    """Stats: geo_enriched counts only the submissions that got geo"""
    w = make_widget(hA)
    faults([])
    expect(submit(http, w["id"]), 201)
    faults(["a", "b"])
    expect(submit(http, w["id"]), 201)
    t = http.get("/api/dashboard/stats", params={"widget_id": w["id"]}, headers=hA).json()["totals"]
    assert t["submissions"] == 2 and t["geo_enriched"] == 1, t


def test_fault_endpoint_rejects_nonsense(http, debug_ok):
    """POST /_debug/faults with unknown provider -> 422 (no 500)"""
    if not debug_ok:
        pytest.skip("debug endpoints disabled")
    expect(http.post("/_debug/faults", json={"geo_down": ["zzz"]}), 422)
