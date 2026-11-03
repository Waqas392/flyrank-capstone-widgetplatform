from .conftest import register, submit


def test_widget_endpoints_reject_missing_or_bad_auth(client):
    assert client.get("/api/widgets").status_code == 401
    assert client.post("/api/widgets", json={"type": "signup_form", "title": "x"}).status_code == 401
    assert client.get("/api/widgets", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/dashboard/stats").status_code == 401


def test_widget_crud_and_embed_snippet(client, auth):
    r = client.post("/api/widgets", headers=auth, json={"type": "signup_form", "title": "Join", "button_text": "Sign me up"})
    assert r.status_code == 201
    w = r.json()
    assert w["embed_snippet"] == f'<script src="http://testserver/widget.js?id={w["id"]}" async></script>'
    assert w["fields"][0]["name"] == "email"

    assert client.get(f"/api/widgets/{w['id']}", headers=auth).json()["title"] == "Join"
    assert len(client.get("/api/widgets", headers=auth).json()["items"]) == 1
    assert client.get(f"/api/widgets/{w['id']}/embed", headers=auth).json()["embed_snippet"] == w["embed_snippet"]

    p = client.patch(f"/api/widgets/{w['id']}", headers=auth, json={"title": "Join now"})
    assert p.status_code == 200 and p.json()["title"] == "Join now" and p.json()["version"] == 2

    assert client.delete(f"/api/widgets/{w['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/widgets/{w['id']}", headers=auth).status_code == 404


def test_widget_validation_errors_are_422_json(client, auth):
    for body in [
        {"type": "nope", "title": "x"},
        {"type": "signup_form"},
        {"type": "signup_form", "title": "x", "unexpected": 1},
        {"type": "signup_form", "title": "x", "fields": [{"name": "Bad Name", "label": "l"}]},
        {"type": "signup_form", "title": "x", "fields": [{"name": "a", "label": "l"}, {"name": "a", "label": "m"}]},
        {"type": "signup_form", "title": "x", "fields": [{"name": "website", "label": "l"}]},
    ]:
        r = client.post("/api/widgets", headers=auth, json=body)
        assert r.status_code == 422, (body, r.text)
        assert r.json()["error"]["code"] == "validation_error"


def test_tenant_isolation_widgets_and_submissions(client):
    a, b = register(client, "a@example.com"), register(client, "b@example.com")
    wa = client.post("/api/widgets", headers=a, json={"type": "signup_form", "title": "A's"}).json()
    wb = client.post("/api/widgets", headers=b, json={"type": "signup_form", "title": "B's"}).json()
    assert submit(client, wb["id"], {"email": "lead@b.com"}).status_code == 201
    assert submit(client, wa["id"], {"email": "lead@a.com"}).status_code == 201

    # A cannot read/modify/delete B's widget - and gets 404, not 403, so existence isn't leaked
    assert client.get(f"/api/widgets/{wb['id']}", headers=a).status_code == 404
    assert client.patch(f"/api/widgets/{wb['id']}", headers=a, json={"title": "pwned"}).status_code == 404
    assert client.delete(f"/api/widgets/{wb['id']}", headers=a).status_code == 404
    assert client.get(f"/api/widgets/{wb['id']}/embed", headers=a).status_code == 404
    assert [w["id"] for w in client.get("/api/widgets", headers=a).json()["items"]] == [wa["id"]]
    assert client.get(f"/api/widgets/{wb['id']}", headers=b).json()["title"] == "B's"  # untouched

    # ...nor B's submissions, by list, by filter, by id, or in stats
    assert client.get(f"/api/dashboard/submissions?widget_id={wb['id']}", headers=a).status_code == 404
    items = client.get("/api/dashboard/submissions", headers=a).json()["items"]
    assert [i["data"]["email"] for i in items] == ["lead@a.com"]
    b_sub = client.get("/api/dashboard/submissions", headers=b).json()["items"][0]["id"]
    assert client.get(f"/api/dashboard/submissions/{b_sub}", headers=a).status_code == 404
    assert client.get(f"/api/dashboard/stats?widget_id={wb['id']}", headers=a).status_code == 404
    assert client.get("/api/dashboard/stats", headers=a).json()["totals"]["submissions"] == 1


def test_login_and_duplicate_registration(client):
    register(client, "x@example.com", "password-123")
    assert client.post("/api/auth/register", json={"email": "x@example.com", "password": "password-123"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "x@example.com", "password": "wrong-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "x@example.com", "password": "password-123"}).status_code == 200
    assert client.post("/api/auth/register", json={"email": "bad", "password": "short"}).status_code == 422


def test_password_is_hashed_and_tokens_stored_hashed(client, ctx):
    h = register(client, "h@example.com", "plaintext-pass-1")
    from sqlalchemy import text
    with ctx.engine.connect() as c:
        pw = c.execute(text("select password_hash from owners")).scalar()
        tok = c.execute(text("select token_hash from api_tokens")).scalar()
    assert "plaintext-pass-1" not in pw and pw.startswith("scrypt$")
    assert tok not in h["Authorization"] and len(tok) == 64
