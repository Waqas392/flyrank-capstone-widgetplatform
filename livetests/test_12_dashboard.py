"""Owner dashboard API: lists, pagination, per-widget stats, geo breakdown, time series."""
import pytest

from conftest import dash_items, expect, expect_json_error, submit


@pytest.fixture()
def populated(http, hA, make_widget):
    w = make_widget(hA)
    ids = []
    for n in range(3):
        r = expect(submit(http, w["id"], {"name": f"P{n}", "email": f"p{n}@example.com", "message": "hi"}), 201)
        ids.append(r.json()["id"])
    return w, ids


def test_list_total_and_filter(http, hA, populated):
    """GET /api/dashboard/submissions?widget_id= -> exactly this widget's 3 rows, total=3"""
    w, ids = populated
    j = expect(http.get("/api/dashboard/submissions", params={"widget_id": w["id"]}, headers=hA), 200).json()
    assert j["total"] == 3 and {i["id"] for i in j["items"]} == set(ids)


def test_pagination(http, hA, populated):
    """limit/offset paginate and total stays 3"""
    w, _ = populated
    p1 = http.get("/api/dashboard/submissions", params={"widget_id": w["id"], "limit": 2}, headers=hA).json()
    p2 = http.get("/api/dashboard/submissions", params={"widget_id": w["id"], "limit": 2, "offset": 2}, headers=hA).json()
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1 and p1["total"] == p2["total"] == 3
    assert not ({i["id"] for i in p1["items"]} & {i["id"] for i in p2["items"]})


def test_newest_first(http, hA, populated):
    """Submissions are ordered newest first"""
    w, _ = populated
    ts = [i["created_at"] for i in dash_items(http, hA, w["id"])]
    assert ts == sorted(ts, reverse=True)


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"days": 0}, {"limit": "abc"}])
def test_list_bad_query_params_422(http, hA, params):
    """GET /api/dashboard/submissions invalid query params -> 422"""
    expect_json_error(http.get("/api/dashboard/submissions", params=params, headers=hA), 422)


def test_detail_and_privacy(http, hA, populated):
    """GET /api/dashboard/submissions/{id} -> row, without raw IP / hash"""
    w, ids = populated
    r = expect(http.get(f"/api/dashboard/submissions/{ids[0]}", headers=hA), 200).json()
    assert r["id"] == ids[0] and r["widget_id"] == w["id"]
    assert not any("ip" == k or k.startswith("ip_") for k in r), f"IP data exposed: {list(r)}"


def test_detail_unknown_404(http, hA):
    """GET /api/dashboard/submissions/<unknown> -> 404 submission_not_found"""
    expect_json_error(http.get("/api/dashboard/submissions/zzzz", headers=hA), 404, code="submission_not_found")


def test_stats_shape_and_counts(http, hA, populated):
    """GET /api/dashboard/stats?widget_id= -> totals, per_widget, by_day (30 days), by_country all consistent"""
    w, _ = populated
    s = expect(http.get("/api/dashboard/stats", params={"widget_id": w["id"]}, headers=hA), 200).json()
    assert s["totals"]["submissions"] == 3
    assert s["totals"]["geo_enriched"] <= 3
    assert [p["submissions"] for p in s["per_widget"] if p["widget_id"] == w["id"]] == [3]
    assert len(s["by_day"]) == s["range_days"] == 30
    assert sum(d["count"] for d in s["by_day"]) == 3, "time series does not add up to total"
    assert sum(c["count"] for c in s["by_country"]) == s["totals"]["geo_enriched"], "geo breakdown != enriched count"


def test_stats_range_param(http, hA, populated):
    """GET /api/dashboard/stats?days=7 -> 7-point series"""
    w, _ = populated
    s = expect(http.get("/api/dashboard/stats", params={"widget_id": w["id"], "days": 7}, headers=hA), 200).json()
    assert len(s["by_day"]) == 7 and s["by_day"][-1]["count"] == 3


@pytest.mark.parametrize("params", [{"days": 0}, {"days": 366}])
def test_stats_bad_range_422(http, hA, params):
    """GET /api/dashboard/stats with out-of-range days -> 422"""
    expect_json_error(http.get("/api/dashboard/stats", params=params, headers=hA), 422)


def test_stats_unknown_widget_404(http, hA):
    """GET /api/dashboard/stats?widget_id=<unknown> -> 404"""
    expect_json_error(http.get("/api/dashboard/stats", params={"widget_id": "nope"}, headers=hA), 404)


def test_overall_stats_include_all_widgets(http, hA, populated):
    """Unfiltered stats list every widget the owner has (even with zero submissions)"""
    w, _ = populated
    s = expect(http.get("/api/dashboard/stats", headers=hA), 200).json()
    assert w["id"] in [p["widget_id"] for p in s["per_widget"]]
