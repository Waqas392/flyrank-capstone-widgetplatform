"""Authentication: wrong credentials, missing/garbage tokens, registration rules."""
import pytest

from conftest import DEMO, TENANT_A, auth_call, bearer, expect, expect_json_error

PROTECTED = [
    ("GET", "/api/widgets"),
    ("POST", "/api/widgets"),
    ("GET", "/api/widgets/abc"),
    ("PATCH", "/api/widgets/abc"),
    ("DELETE", "/api/widgets/abc"),
    ("GET", "/api/widgets/abc/embed"),
    ("GET", "/api/dashboard/submissions"),
    ("GET", "/api/dashboard/submissions/abc"),
    ("GET", "/api/dashboard/stats"),
]


def test_login_unknown_user_rejected(http):
    """POST /api/auth/login unknown email -> 401 invalid_credentials"""
    r = auth_call(http, "/api/auth/login", ("wrong@example.com", "wrong-password-123"))
    expect_json_error(r, 401, code="invalid_credentials")


def test_login_wrong_password_rejected_and_not_distinguishable(http):
    """POST /api/auth/login right email + wrong password -> same 401 (no user enumeration)"""
    a = auth_call(http, "/api/auth/login", (DEMO[0], "definitely-wrong-pw"))
    expect_json_error(a, 401, code="invalid_credentials")
    assert a.json()["error"]["message"] == "Invalid email or password"


def test_login_valid_returns_working_token(http):
    """POST /api/auth/login valid demo credentials -> 200 + token that works"""
    r = expect(auth_call(http, "/api/auth/login", DEMO), 200)
    body = r.json()
    assert body.get("token"), "no token in login response"
    assert "password" not in r.text.lower(), "login response leaks password/hash fields"
    ok = http.get("/api/widgets", headers=bearer(body["token"]))
    expect(ok, 200)


def test_login_bad_input_is_422_not_500(http):
    """POST /api/auth/login invalid email / short password -> 422 JSON"""
    expect_json_error(http.post("/api/auth/login", json={"email": "not-an-email", "password": "longenough1"}), 422)
    expect_json_error(http.post("/api/auth/login", json={"email": "a@example.com", "password": "short"}), 422)
    expect_json_error(http.post("/api/auth/login", json={}), 422)
    expect(http.post("/api/auth/login", content=b"{not json", headers={"Content-Type": "application/json"}), 400, 422)


def test_duplicate_registration_rejected(http, hA):
    """POST /api/auth/register existing email -> 409 email_taken"""
    r = auth_call(http, "/api/auth/register", TENANT_A)
    expect_json_error(r, 409, code="email_taken")


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_endpoints_require_auth(http, method, path):
    """Owner/dashboard endpoints reject requests without a token (401)"""
    r = http.request(method, path, json={} if method in ("POST", "PATCH") else None)
    expect_json_error(r, 401, code="unauthorized")
    assert "bearer" in r.headers.get("www-authenticate", "").lower(), "401 lacks WWW-Authenticate: Bearer"


@pytest.mark.parametrize("header", ["Bearer not-a-real-token", "Basic dXNlcjpwYXNz", "Bearer", "fw_garbage"])
def test_garbage_credentials_rejected(http, header):
    """GET /api/widgets with invalid Authorization header -> 401"""
    expect(http.get("/api/widgets", headers={"Authorization": header}), 401)
