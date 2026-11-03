"""Safe side effects: a failing confirmation email must never break or lose the submission."""
import time

import pytest

from conftest import dash_items, expect, submit


def _jobs(http) -> dict:
    return http.get("/healthz").json()["jobs"]


@pytest.fixture()
def email_fault(http, debug_ok):
    if not debug_ok:
        pytest.skip("/_debug/faults not available (DEBUG_ENDPOINTS=0)")
    yield lambda on: http.post("/_debug/faults", json={"email_fail": on})
    http.post("/_debug/faults", json={"email_fail": False})


def test_email_failure_does_not_block_submission(http, hA, wA, email_fault):
    """Email forced to fail -> submission still 201 and stored"""
    email_fault(True)
    before = sum(_jobs(http).values())
    r = expect(submit(http, wA["id"]), 201)
    assert r.json()["ok"] is True
    assert r.json()["id"] in [i["id"] for i in dash_items(http, hA, wA["id"])], "submission lost when email failed"
    assert sum(_jobs(http).values()) == before + 1, "confirmation job was not queued"


def test_email_job_runs_off_the_request_path(http, wA, email_fault):
    """A healthy submission returns quickly (email is queued, not sent inline)"""
    email_fault(False)
    t = time.perf_counter()
    expect(submit(http, wA["id"]), 201)
    assert time.perf_counter() - t < 3.0, "submission took >3s - side effect may be running inline"


def test_failed_email_is_retried_and_recovers(http, wA, email_fault):
    """Failing job is retried with backoff and completes once email works again"""
    email_fault(True)
    expect(submit(http, wA["id"]), 201)
    time.sleep(1.5)                      # let the worker hit the failure at least once
    email_fault(False)
    deadline = time.time() + 45
    while time.time() < deadline:
        j = _jobs(http)
        if j.get("pending", 0) == 0 and j.get("running", 0) == 0:
            return
        time.sleep(1.5)
    pytest.fail(f"jobs still not finished after 45s: {_jobs(http)}")
