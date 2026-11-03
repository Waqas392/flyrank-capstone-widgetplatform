from app.db import run_migrations

from .conftest import submit


def test_dashboard_stats_shape(client, auth, widget):
    for i in range(3):
        submit(client, widget["id"], {"name": f"n{i}", "email": f"n{i}@example.com", "message": "hi"})
    client.post("/_debug/faults", json={"geo_down": ["a", "b"]})
    submit(client, widget["id"], {"name": "x", "email": "x@example.com", "message": "hi"})
    st = client.get("/api/dashboard/stats?days=7", headers=auth).json()
    assert st["totals"] == {"submissions": 4, "geo_enriched": 3, "spam_blocked": 0}
    assert st["per_widget"] == [{"widget_id": widget["id"], "title": "Contact us", "submissions": 4}]
    assert len(st["by_day"]) == 7 and sum(d["count"] for d in st["by_day"]) == 4
    assert st["by_country"] == [{"country": "Mockland", "count": 3}]


def test_dashboard_pagination_and_filters(client, auth, widget):
    for i in range(5):
        submit(client, widget["id"], {"name": f"n{i}", "email": f"n{i}@example.com", "message": "hi"})
    page = client.get("/api/dashboard/submissions?limit=2&offset=2", headers=auth).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    assert client.get("/api/dashboard/submissions?limit=0", headers=auth).status_code == 422
    assert client.get("/api/dashboard/submissions?limit=101", headers=auth).status_code == 422


def test_migrations_are_idempotent(app, ctx):
    assert run_migrations(ctx.engine) == []  # create_app already applied them


def test_deleting_widget_removes_its_submissions(client, auth, widget):
    submit(client, widget["id"])
    client.delete(f"/api/widgets/{widget['id']}", headers=auth)
    assert client.get("/api/dashboard/submissions", headers=auth).json()["total"] == 0


def test_errors_are_json_never_html(client):
    for r in (client.get("/nope"), client.put("/submissions"), client.get("/api/widgets/../x")):
        assert r.headers["content-type"].startswith("application/json")
        assert "error" in r.json()


def test_debug_endpoints_absent_when_disabled(tmp_path):
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    s = Settings(database_url=f"sqlite:///{tmp_path}/d.db", run_worker=False, debug_endpoints=False)
    with TestClient(create_app(s)) as c:
        assert c.get("/_debug/faults").status_code == 404
        assert c.post("/_debug/faults", json={}).status_code in (404, 405)
