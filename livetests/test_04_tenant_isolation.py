"""Tenant isolation: owner B must never see or touch owner A's widgets or submissions."""
from conftest import dash_items, expect, expect_json_error, submit


def test_b_cannot_read_or_modify_a_widget(http, hA, hB, wA):
    """B: GET/PATCH/DELETE/embed on A's widget -> 404 (and A's widget is untouched)"""
    wid = wA["id"]
    expect_json_error(http.get(f"/api/widgets/{wid}", headers=hB), 404)
    expect_json_error(http.get(f"/api/widgets/{wid}/embed", headers=hB), 404)
    expect_json_error(http.patch(f"/api/widgets/{wid}", json={"title": "HACKED"}, headers=hB), 404)
    expect_json_error(http.delete(f"/api/widgets/{wid}", headers=hB), 404)
    still = expect(http.get(f"/api/widgets/{wid}", headers=hA), 200).json()
    assert still["title"] == wA["title"], "A's widget was modified by B"


def test_b_widget_list_excludes_a(http, hA, hB, wA):
    """B: GET /api/widgets never lists A's widgets"""
    ids = [w["id"] for w in expect(http.get("/api/widgets", headers=hB), 200).json()["items"]]
    assert wA["id"] not in ids


def test_b_cannot_read_a_submissions(http, hA, hB, wA):
    """B: dashboard list/detail/stats cannot reach A's submissions"""
    r = expect(submit(http, wA["id"]), 201)
    sid = r.json()["id"]
    # filter by A's widget id -> 404 for B
    expect_json_error(http.get("/api/dashboard/submissions", params={"widget_id": wA["id"]}, headers=hB), 404)
    expect_json_error(http.get("/api/dashboard/stats", params={"widget_id": wA["id"]}, headers=hB), 404)
    # direct id lookup -> 404
    expect_json_error(http.get(f"/api/dashboard/submissions/{sid}", headers=hB), 404, code="submission_not_found")
    # unfiltered list for B must not contain it
    b_all = expect(http.get("/api/dashboard/submissions", params={"limit": 100}, headers=hB), 200).json()["items"]
    assert sid not in [i["id"] for i in b_all]
    # per-widget stats for B must not mention A's widget
    per = expect(http.get("/api/dashboard/stats", headers=hB), 200).json()["per_widget"]
    assert wA["id"] not in [p["widget_id"] for p in per]
    # sanity: A can see it
    assert sid in [i["id"] for i in dash_items(http, hA, wA["id"])]


def test_deleting_widget_removes_its_submissions(http, hA, make_widget):
    """DELETE widget cascades: its submissions are gone too"""
    w = make_widget(hA)
    sid = expect(submit(http, w["id"]), 201).json()["id"]
    expect(http.delete(f"/api/widgets/{w['id']}", headers=hA), 204)
    expect_json_error(http.get(f"/api/dashboard/submissions/{sid}", headers=hA), 404)
