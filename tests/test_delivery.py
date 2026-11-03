import re


def test_config_is_public_small_and_cacheable(client, widget):
    r = client.get(f"/widgets/{widget['id']}/config")
    assert r.status_code == 200
    cc = r.headers["cache-control"]
    assert "public" in cc and re.search(r"max-age=\d+", cc)
    assert r.headers["etag"]
    assert len(r.content) < 2048
    cfg = r.json()
    assert cfg["id"] == widget["id"] and "owner_id" not in cfg
    # conditional request -> 304 with no body
    r2 = client.get(f"/widgets/{widget['id']}/config", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304 and r2.content == b""


def test_config_etag_changes_when_widget_changes(client, auth, widget):
    e1 = client.get(f"/widgets/{widget['id']}/config").headers["etag"]
    client.patch(f"/api/widgets/{widget['id']}", headers=auth, json={"title": "New title"})
    r = client.get(f"/widgets/{widget['id']}/config", headers={"If-None-Match": e1})
    assert r.status_code == 200 and r.headers["etag"] != e1 and r.json()["title"] == "New title"


def test_unknown_or_inactive_widget_config_404(client, auth, widget):
    assert client.get("/widgets/does-not-exist/config").status_code == 404
    client.patch(f"/api/widgets/{widget['id']}", headers=auth, json={"is_active": False})
    assert client.get(f"/widgets/{widget['id']}/config").status_code == 404


def test_loader_is_short_cached_and_points_at_versioned_immutable_bundle(client, ctx):
    loader = client.get("/widget.js?id=abc")
    assert loader.status_code == 200 and "javascript" in loader.headers["content-type"]
    assert "max-age=300" in loader.headers["cache-control"]
    m = re.search(r"/assets/(widget\.[0-9a-f]{10}\.js)", loader.text)
    assert m, loader.text
    bundle = client.get(f"/assets/{m.group(1)}")
    assert bundle.status_code == 200
    assert bundle.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "FlyRankWidget" in bundle.text
    assert client.get("/assets/widget.0000000000.js").status_code == 404  # only the current hash exists


def test_bundle_url_changes_when_content_changes(tmp_path, monkeypatch):
    from app.api import public
    (tmp_path / "widget.js").write_text("console.log(1)")
    (tmp_path / "loader.js").write_text("load('__BUNDLE__')")
    monkeypatch.setattr(public, "STATIC", tmp_path)
    a = public.load_bundle().name
    (tmp_path / "widget.js").write_text("console.log(2)")
    assert public.load_bundle().name != a


def test_widget_js_never_parses_server_data_as_markup():
    from pathlib import Path
    src = (Path(__file__).parent.parent / "static" / "widget.js").read_text()
    assert "innerHTML" not in src and "eval(" not in src
