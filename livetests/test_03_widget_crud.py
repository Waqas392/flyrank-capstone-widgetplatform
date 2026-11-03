"""Widget management API: create / read / update / delete + embed snippet."""
import re

import pytest

from conftest import bearer, expect, expect_json_error


def test_create_widget_defaults(make_widget, hA):
    """POST /api/widgets -> 201 with id, default fields, embed snippet"""
    w = make_widget(hA, type="signup_form", title="Newsletter")
    assert w["id"] and w["version"] == 1 and w["is_active"] is True
    assert [f["name"] for f in w["fields"]] == ["email"]
    assert "owner" not in " ".join(w.keys()).lower()


def test_embed_snippet_is_one_script_line(wA):
    """Created widget carries a one-line <script src=.../widget.js?id=...> snippet"""
    snip = wA["embed_snippet"]
    assert re.fullmatch(r'<script src="https?://[^"]+/widget\.js\?id=' + re.escape(wA["id"]) + r'" async></script>', snip), snip
    assert "\n" not in snip


def test_embed_endpoint_matches(http, hA, wA):
    """GET /api/widgets/{id}/embed -> same snippet"""
    r = expect(http.get(f"/api/widgets/{wA['id']}/embed", headers=hA), 200)
    assert r.json()["embed_snippet"] == wA["embed_snippet"]


def test_list_and_get(http, hA, wA):
    """GET /api/widgets lists it; GET /api/widgets/{id} returns it"""
    items = expect(http.get("/api/widgets", headers=hA), 200).json()["items"]
    assert wA["id"] in [w["id"] for w in items]
    got = expect(http.get(f"/api/widgets/{wA['id']}", headers=hA), 200).json()
    assert got["title"] == wA["title"]


def test_custom_fields_roundtrip(make_widget, hA):
    """Custom field definitions are stored and returned unchanged"""
    fields = [
        {"name": "full_name", "label": "Full name", "type": "text", "required": True, "max_length": 50},
        {"name": "phone", "label": "Phone", "type": "tel", "required": False},
    ]
    w = make_widget(hA, fields=fields, button_text="Go")
    assert [f["name"] for f in w["fields"]] == ["full_name", "phone"]
    assert w["button_text"] == "Go"


def test_patch_updates_and_bumps_version(http, hA, wA):
    """PATCH /api/widgets/{id} -> 200, change persisted, version incremented"""
    r = expect(http.patch(f"/api/widgets/{wA['id']}", json={"title": "Renamed", "button_text": "Send now"}, headers=hA), 200).json()
    assert r["title"] == "Renamed" and r["version"] == wA["version"] + 1
    again = http.get(f"/api/widgets/{wA['id']}", headers=hA).json()
    assert again["title"] == "Renamed" and again["button_text"] == "Send now"


def test_delete_then_gone(http, hA, make_widget):
    """DELETE /api/widgets/{id} -> 204, then GET -> 404 and public config -> 404"""
    w = make_widget(hA)
    expect(http.delete(f"/api/widgets/{w['id']}", headers=hA), 204)
    expect_json_error(http.get(f"/api/widgets/{w['id']}", headers=hA), 404, code="widget_not_found")
    expect(http.get(f"/widgets/{w['id']}/config"), 404)


@pytest.mark.parametrize(
    "label,body",
    [
        ("bad type", {"type": "carousel", "title": "x"}),
        ("empty title", {"type": "contact_form", "title": ""}),
        ("title too long", {"type": "contact_form", "title": "x" * 201}),
        ("missing title", {"type": "contact_form"}),
        ("unknown property", {"type": "contact_form", "title": "x", "is_admin": True}),
        ("duplicate field names", {"type": "contact_form", "title": "x", "fields": [
            {"name": "a", "label": "A"}, {"name": "a", "label": "A2"}]}),
        ("bad field name", {"type": "contact_form", "title": "x", "fields": [{"name": "Bad Name!", "label": "A"}]}),
        ("bad field type", {"type": "contact_form", "title": "x", "fields": [{"name": "a", "label": "A", "type": "file"}]}),
        ("zero fields", {"type": "contact_form", "title": "x", "fields": []}),
        ("21 fields", {"type": "contact_form", "title": "x", "fields": [{"name": f"f{i}", "label": "F"} for i in range(21)]}),
        ("field named like honeypot", {"type": "contact_form", "title": "x", "fields": [{"name": "website", "label": "W"}]}),
        ("popover delay too big", {"type": "cta_popover", "title": "x", "display": {"mode": "popover", "delay_seconds": 999}}),
    ],
)
def test_create_validation(http, hA, label, body):
    """POST /api/widgets invalid body -> 422 JSON error"""
    expect_json_error(http.post("/api/widgets", json=body, headers=hA), 422)


def test_update_validation(http, hA, wA):
    """PATCH /api/widgets/{id} invalid body -> 422 JSON error"""
    expect_json_error(http.patch(f"/api/widgets/{wA['id']}", json={"title": ""}, headers=hA), 422)
    expect_json_error(http.patch(f"/api/widgets/{wA['id']}", json={"nope": 1}, headers=hA), 422)


def test_malformed_json_body_not_500(http, hA):
    """POST /api/widgets with broken JSON -> 4xx, never 500"""
    r = http.post("/api/widgets", content=b"{broken", headers={**hA, "Content-Type": "application/json"})
    assert 400 <= r.status_code < 500, f"got {r.status_code}"


def test_unknown_widget_is_404(http, hA):
    """GET/PATCH/DELETE on a non-existent widget -> 404"""
    for m in ("GET", "DELETE"):
        expect_json_error(http.request(m, "/api/widgets/doesnotexist", headers=hA), 404, code="widget_not_found")
    expect_json_error(http.patch("/api/widgets/doesnotexist", json={"title": "x"}, headers=hA), 404)
