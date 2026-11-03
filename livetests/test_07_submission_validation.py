"""Public submission endpoint: every bad payload gets a clean 4xx JSON error, never a 500."""
import json

import pytest

from conftest import GOOD, dash_items, expect, expect_json_error, raw_submit, submit


def test_valid_submission_stored_and_visible(http, hA, wA):
    """POST /submissions valid -> 201 {ok,id}; visible via dashboard API linked to the right widget"""
    r = expect(submit(http, wA["id"]), 201)
    body = r.json()
    assert body["ok"] is True and body["id"] and body["duplicate"] is False
    row = next((i for i in dash_items(http, hA, wA["id"]) if i["id"] == body["id"]), None)
    assert row, "submission not visible through the dashboard API"
    assert row["widget_id"] == wA["id"] and row["data"]["email"] == GOOD["email"] and row["data"]["name"] == GOOD["name"]


def test_malformed_json_400(http):
    """POST /submissions broken JSON -> 400 invalid_json"""
    expect_json_error(raw_submit(http, content=b"{oops", headers={"Content-Type": "application/json"}), 400, code="invalid_json")


def test_invalid_utf8_400(http):
    """POST /submissions invalid UTF-8 bytes -> 400 JSON"""
    expect_json_error(raw_submit(http, content=b"\xff\xfe\x00{", headers={"Content-Type": "application/json"}), 400)


@pytest.mark.parametrize("raw", [b"[]", b"null", b"123", b'"text"', b"true"])
def test_non_object_json_400(http, raw):
    """POST /submissions JSON that is not an object -> 400"""
    expect_json_error(raw_submit(http, content=raw, headers={"Content-Type": "application/json"}), 400, code="invalid_json")


def test_oversized_declared_body_413(http, wA):
    """POST /submissions 60 KB body (Content-Length) -> 413 payload_too_large JSON"""
    big = json.dumps({"widget_id": wA["id"], "data": {"message": "x" * 60000}}).encode()
    expect_json_error(raw_submit(http, content=big, headers={"Content-Type": "application/json"}), 413, code="payload_too_large")


def test_oversized_chunked_body_413(http, wA):
    """POST /submissions 60 KB streamed WITHOUT Content-Length -> 413 (limit enforced while reading)"""
    def gen():
        yield b'{"widget_id":"' + wA["id"].encode() + b'","data":{"message":"'
        for _ in range(60):
            yield b"x" * 1000
        yield b'"}}'
    expect_json_error(raw_submit(http, content=gen(), headers={"Content-Type": "application/json"}), 413)


def test_missing_widget_id_422(http):
    """POST /submissions without widget_id -> 422"""
    expect_json_error(raw_submit(http, json={"data": GOOD}), 422, code="validation_error")


@pytest.mark.parametrize("wid", [123, None, ["a"], "has spaces", "../../etc", "x" * 17])
def test_malformed_widget_id_422(http, wid):
    """POST /submissions with malformed widget_id -> 422"""
    expect_json_error(raw_submit(http, json={"widget_id": wid, "data": GOOD}), 422)


def test_unknown_widget_404(http):
    """POST /submissions for a widget that doesn't exist -> 404 widget_not_found"""
    expect_json_error(submit(http, "nope-nope"), 404, code="widget_not_found")


def test_inactive_widget_404(http, hA, wA):
    """POST /submissions to a deactivated widget -> 404"""
    http.patch(f"/api/widgets/{wA['id']}", json={"is_active": False}, headers=hA)
    expect_json_error(submit(http, wA["id"]), 404)


@pytest.mark.parametrize("data", [None, [], "string", 5, [{"a": 1}]])
def test_data_must_be_object(http, wA, data):
    """POST /submissions with data not an object -> 422"""
    expect_json_error(raw_submit(http, json={"widget_id": wA["id"], "data": data}), 422)


def test_missing_required_fields_422_lists_them(http, wA):
    """POST /submissions with required fields missing -> 422 with per-field details"""
    body = expect_json_error(submit(http, wA["id"], {"name": "Only name"}), 422, code="validation_error")
    fields = {d["field"] for d in body["error"]["details"]}
    assert {"email", "message"} <= fields, f"details only mention {fields}"


def test_whitespace_only_counts_as_missing(http, wA):
    """POST /submissions whitespace-only required value -> 422"""
    expect_json_error(submit(http, wA["id"], {**GOOD, "message": "    "}), 422)


@pytest.mark.parametrize("email", ["not-an-email", "a@", "@b.com", "a b@c.com", "a@b", "x" * 300 + "@example.com"])
def test_invalid_email_422(http, wA, email):
    """POST /submissions invalid email -> 422"""
    expect_json_error(submit(http, wA["id"], {**GOOD, "email": email}), 422)


def test_unknown_field_422(http, wA):
    """POST /submissions with a field the widget doesn't define -> 422"""
    body = expect_json_error(submit(http, wA["id"], {**GOOD, "is_admin": True}), 422)
    assert any(d["field"] == "is_admin" for d in body["error"]["details"])


def test_too_long_value_422(http, wA):
    """POST /submissions value over the field's max_length -> 422"""
    expect_json_error(submit(http, wA["id"], {**GOOD, "message": "m" * 2001}), 422)


@pytest.mark.parametrize("bad", [12345, True, ["a"], {"x": 1}])
def test_wrong_value_type_422(http, wA, bad):
    """POST /submissions string field given non-string -> 422"""
    expect_json_error(submit(http, wA["id"], {**GOOD, "name": bad}), 422)


def test_too_many_keys_422(http, wA):
    """POST /submissions with >40 data keys -> 422"""
    expect_json_error(submit(http, wA["id"], {f"k{i}": "v" for i in range(41)}), 422)


def test_tel_and_checkbox_validation(http, hA, make_widget):
    """Widget with tel + required checkbox: bad phone / unticked / string-bool -> 422; good -> 201"""
    w = make_widget(hA, fields=[
        {"name": "email", "label": "Email", "type": "email"},
        {"name": "phone", "label": "Phone", "type": "tel", "required": True},
        {"name": "agree", "label": "I agree", "type": "checkbox", "required": True},
    ])
    ok = {"email": "a@example.com", "phone": "+1 (555) 123-4567", "agree": True}
    expect_json_error(submit(http, w["id"], {**ok, "phone": "abc"}), 422)
    expect_json_error(submit(http, w["id"], {**ok, "agree": False}), 422)
    expect_json_error(submit(http, w["id"], {**ok, "agree": "yes"}), 422)
    expect(submit(http, w["id"], ok), 201)


def test_optional_field_may_be_omitted(http, hA, make_widget):
    """Optional fields can be left out -> 201"""
    w = make_widget(hA, fields=[{"name": "email", "label": "Email", "type": "email"},
                                {"name": "note", "label": "Note", "type": "text", "required": False}])
    expect(submit(http, w["id"], {"email": "a@example.com"}), 201)


def test_bad_idempotency_key_422(http, wA):
    """POST /submissions with a 129-char Idempotency-Key -> 422"""
    expect_json_error(submit(http, wA["id"], headers={"Idempotency-Key": "k" * 129}), 422)


def test_hostile_strings_stored_as_inert_text(http, hA, wA):
    """XSS / SQL-injection strings are stored verbatim as data (no 500, no execution)"""
    xss = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    sqli = "'); DROP TABLE submissions;--"
    r = expect(submit(http, wA["id"], {"name": xss, "email": "a@example.com", "message": sqli}), 201)
    row = next(i for i in dash_items(http, hA, wA["id"]) if i["id"] == r.json()["id"])
    assert row["data"]["name"] == xss and row["data"]["message"] == sqli
    again = http.get("/api/dashboard/submissions", params={"widget_id": wA["id"]}, headers=hA)
    assert again.status_code == 200 and "json" in again.headers["content-type"], "dashboard no longer JSON-safe after injection attempt"


def test_control_characters_stripped(http, hA, wA):
    """NUL / control characters in values don't crash storage (-> 201, cleaned)"""
    r = expect(submit(http, wA["id"], {**GOOD, "message": "hello\x00\x07world"}), 201)
    row = next(i for i in dash_items(http, hA, wA["id"]) if i["id"] == r.json()["id"])
    assert "\x00" not in row["data"]["message"]


FUZZ = [
    b"", b"{}", b'{"widget_id":"nope"}', b'{"widget_id":null,"data":null}', b"[" * 5000 + b"]" * 5000,
    b'{"widget_id":"' + b"a" * 5000 + b'","data":{}}', b'{"widget_id":"x","data":{"a":' + b"[" * 400 + b"]" * 400 + b"}}",
    b"\x00\x01\x02", b'{"widget_id":"\\u0000","data":{}}', b"{'single':'quotes'}",
]


@pytest.mark.parametrize("raw", FUZZ, ids=[f"fuzz{i}" for i in range(len(FUZZ))])
def test_fuzz_bodies_never_500(http, raw):
    """POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx"""
    r = raw_submit(http, content=raw, headers={"Content-Type": "application/json"})
    assert 400 <= r.status_code < 500, f"server answered {r.status_code}: {r.text[:200]}"
    assert "error" in r.json()
