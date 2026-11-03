"""Login brute-force protection. Runs LAST because it drains the auth rate-limit bucket."""
from conftest import DEMO, expect


def test_login_bruteforce_is_throttled(http):
    """10 wrong-password logins in a row -> 429 with Retry-After appears"""
    seen = []
    for i in range(10):
        r = http.post("/api/auth/login", json={"email": DEMO[0], "password": f"wrong-password-{i}"})
        seen.append(r.status_code)
        if r.status_code == 429:
            assert r.headers.get("retry-after"), "429 without Retry-After"
            assert "error" in r.json()
            break
    assert 429 in seen, f"no throttling after 10 bad logins: {seen}"
    assert set(seen) <= {401, 429}, seen
