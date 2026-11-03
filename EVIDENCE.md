# EVIDENCE.md
## FlyRank Widget Platform — Verification and Requirements Evidence

**Verification date:** November 3, 2026  
**Project:** FlyRank Widget Platform  
**Backend:** FastAPI  
**Database:** PostgreSQL 16  
**Frontend:** Customer widget site and owner dashboard

---

## 1. Verification Summary

The project was verified using three complementary testing methods.

| Verification layer | Result | Environment |
|---|---:|---|
| Unit tests | 57 passed | API container |
| Live end-to-end suite | 182 passed, 0 failed, 1 skipped | Docker Compose and PostgreSQL |
| Acceptance probes | 17/17 passed | Docker Compose and PostgreSQL |

**Overall result:** All executed tests passed, with one known low-severity caching check skipped.

### Live test suite

The live test suite was executed using:

```cmd
run_tests.bat
```

The complete verification command was:

```cmd
run_tests.bat all
```

The live suite tested the API and customer website through the Docker Compose network. It covered authentication, widget management, tenant isolation, delivery, CORS, validation, spam protection, idempotency, geo fallback, side effects, dashboard functionality, robustness and rate limiting.

Final live result:

```text
182 passed, 0 failed, 1 skipped
```

The HTML and Markdown reports are stored at:

- `docs/live-test-report.html`
- `docs/live-test-report.md`

### Unit tests

The existing unit test suite was executed inside the API container.

```text
57 passed, 55 warnings
```

The warnings are dependency deprecation warnings, not test failures.

### Acceptance probes

The acceptance probe script was executed against the running Docker API:

```cmd
docker compose exec api python -m scripts.run_probes --base http://localhost:8000
```

Final result:

```text
17/17 checks passed
```

The complete probe transcript is included in Section 7.

---

## 2. Known Limitation

One live test is intentionally skipped:

**Conditional caching for `/assets/<bundle>`**

The versioned JavaScript bundle is served with:

```text
Cache-Control: public, max-age=31536000, immutable
```

However, the asset endpoint currently ignores `If-None-Match` and returns `200` rather than `304` for conditional requests.

This is a low-severity improvement rather than a blocker for the current requirements. Because the asset URL is versioned and the response is immutable for one year, browsers can reuse the cached bundle without revalidation.

The loader endpoint and public widget configuration endpoint do support conditional requests and return `304 Not Modified` when appropriate.

---

# 3. Evidence Against Project Requirements

## Widget Management

### 1. Authenticated CRUD and access protection

**Evidence:**

- `test_02_auth.py::test_protected_endpoints_require_auth`
- `test_02_auth.py::test_garbage_credentials_rejected`
- `test_03_widget_crud.py`
- `test_widgets_and_tenancy.py`

Verified behavior:

- Widget creation returns `201 Created`.
- Widget retrieval and listing work for authenticated owners.
- Widget updates persist correctly.
- Widget deletion returns `204 No Content`.
- Deleted widgets subsequently return `404 Not Found`.
- Requests without valid authentication are rejected with `401 Unauthorized`.
- Invalid widget request bodies return structured `422` responses.

### 2. Multi-tenant isolation

**Evidence:**

- `test_04_tenant_isolation.py`
- `test_tenant_isolation_widgets_and_submissions`

Two independent owners were used to verify tenant separation.

Verified behavior:

- Owner B cannot retrieve Owner A's widget.
- Owner B cannot update or delete Owner A's widget.
- Owner B cannot retrieve Owner A's embed endpoint.
- Owner B's widget list does not contain Owner A's widgets.
- Dashboard submission lists, detail endpoints and statistics do not expose another owner's data.
- Deleting a widget also removes its associated submissions.

Cross-owner access returns `404` rather than exposing another owner's resource.

---

## Widget Delivery

### 3. Embed snippet generation

**Evidence:**

- `test_03_widget_crud.py::test_embed_snippet_is_one_script_line`
- `test_03_widget_crud.py::test_embed_endpoint_matches`

Verified behavior:

- Each widget receives an embed snippet.
- The snippet contains the correct widget ID.
- The generated snippet uses a single script element.
- The dedicated embed endpoint returns the same snippet.

Example format:

```html
<script src="https://api.example.com/widget.js?id=demo-contact" async></script>
```

### 4. Public configuration and caching

**Evidence:**

- `test_05_delivery_and_caching.py::test_config_cache_headers_and_small_payload`
- `test_05_delivery_and_caching.py::test_config_conditional_get_304`
- `test_05_delivery_and_caching.py::test_config_changes_after_update`
- `test_05_delivery_and_caching.py::test_config_hides_internals`
- `test_05_delivery_and_caching.py::test_inactive_widget_not_public`

Verified behavior:

- Public configuration returns JSON.
- Cache headers and ETags are included.
- Configuration payload remains below 5 KB.
- Conditional requests return `304 Not Modified`.
- Editing a widget changes its configuration ETag.
- Inactive widgets are not publicly accessible.
- Public configuration does not expose owner information, authentication tokens or internal hashes.

### 5. Versioned JavaScript bundle

**Evidence:**

- `test_05_delivery_and_caching.py::test_bundle_is_versioned_and_immutable`
- `test_05_delivery_and_caching.py::test_loader_conditional_get_304`
- `test_05_delivery_and_caching.py::test_unknown_asset_404_and_no_path_traversal`

Verified behavior:

- The loader references a versioned JavaScript asset.
- The bundle URL contains a content hash.
- The bundle is served with immutable caching headers.
- The loader supports conditional requests.
- Unknown asset paths return `404`.
- Path traversal attempts do not expose files from disk.

**Known limitation:** Conditional ETag handling for the bundle itself remains the one skipped live check described in Section 2.

### 6. Widget rendering on a different origin

**Manual verification:**

The customer website was opened at:

```text
http://localhost:5500
```

The API was running separately at:

```text
http://localhost:8000
```

The customer website successfully displayed the three seeded demo widgets:

- Newsletter signup
- Contact form
- Early-access popover

All three forms were submitted using test data.

The dashboard subsequently displayed:

```text
3 Submissions
3 Geo-enriched
0 Spam blocked
```

Each demo widget had one submission.

The live suite also verifies that the customer website is served from a different origin and contains the expected embed scripts.

---

## Public Submission API

### 7. Cross-origin submissions and CORS

**Evidence:**

- `test_06_cors.py`
- `test_cors.py`

Verified behavior:

- Cross-origin submission preflight requests return `204`.
- Required methods and headers are allowed.
- Public widget submissions work from third-party origins.
- Successful submission responses contain the appropriate CORS headers.
- Validation and error responses also contain CORS headers.
- Authenticated dashboard routes allow only the configured dashboard origin.
- Unlisted origins are not granted access to authenticated API routes.

### 8. Malformed and oversized payload handling

**Evidence:**

- `test_07_submission_validation.py`
- `test_13_robustness.py`

Verified behavior:

- Invalid JSON returns `400`.
- Invalid UTF-8 returns a clean JSON error.
- JSON values that are not objects are rejected.
- Oversized requests return `413`.
- The request-size limit is enforced even when `Content-Length` is absent.
- Missing required fields return `422`.
- Invalid email values are rejected.
- Invalid field types are rejected.
- Unknown fields are rejected.
- Excessive numbers of fields are rejected.
- Fuzzed payloads produce client errors rather than server errors.
- Hostile URLs and malformed identifiers do not cause unhandled `500` responses.

### 9. Submission persistence and dashboard visibility

**Evidence:**

- `test_07_submission_validation.py::test_valid_submission_stored_and_visible`
- `test_09_idempotency.py`
- `test_12_dashboard.py`
- `test_raw_ip_is_never_stored`

Verified behavior:

- Valid submissions return `201 Created`.
- Submissions are associated with their corresponding widgets.
- Stored submissions are visible through the dashboard API.
- Repeated requests with the same idempotency key do not create duplicate records.
- Different idempotency keys create separate submissions.
- Pagination and total counts remain consistent.
- Dashboard results are ordered newest first.
- Raw IP information is not exposed through dashboard detail responses.

---

## Abuse Protection

### 10. Rate limiting

**Evidence:**

- `test_90_rate_limiting.py::test_burst_gets_429_and_service_stays_up`
- `test_90_rate_limiting.py::test_junk_requests_also_count_against_the_limit`
- `test_99_auth_bruteforce.py`

Verified behavior:

- Rapid requests trigger `429 Too Many Requests`.
- Rate-limited responses include `Retry-After`.
- Error responses remain valid JSON.
- Health and widget configuration endpoints remain available.
- Normal requests succeed after the rate-limit bucket refills.
- Invalid requests also count toward rate limiting.
- Repeated failed login attempts trigger authentication throttling.

### 11. Spam protection

**Evidence:**

- `test_08_spam_protection.py`

Verified behavior:

- Filled honeypot fields are detected.
- Custom honeypot field names are supported.
- Honeypot values supplied outside the expected data object are also detected.
- Suspiciously fast submissions are blocked.
- Messages containing excessive URLs are blocked.
- Spam submissions are not stored as normal submissions.
- Spam counters are updated.
- Responses do not reveal the honeypot or internal spam-detection mechanism.
- Legitimate submissions continue to work.

---

## Enrichment and Safe Side Effects

### 12. Geo-provider fallback

**Evidence:**

- `test_10_geo_fallback.py::test_provider_b_answers_when_a_down`
- `test_geo_fallback_chain`
- `test_live_geo_chain_survives_real_provider_errors`

Verified behavior:

- When provider A is available, it supplies the geo-enrichment result.
- When provider A fails, provider B is used.
- When provider B fails but A is available, A still works.
- Enrichment resumes after provider recovery.

### 13. Submission storage when all geo providers fail

**Evidence:**

- `test_10_geo_fallback.py::test_both_down_still_stores_without_geo`
- `test_10_geo_fallback.py::test_geo_outage_is_reflected_in_stats`

Verified behavior:

- When both geo providers are unavailable, a valid submission still returns `201`.
- The submission is stored successfully.
- Geo fields remain empty when enrichment is unavailable.
- Dashboard statistics count only submissions that were successfully enriched.

### 14. Safe email side effects and retry handling

**Evidence:**

- `test_11_side_effects.py`
- `test_failing_email_does_not_block_submission`
- `test_job_retries_then_succeeds_when_email_recovers`
- `test_job_alert_is_logged_on_permanent_failure`

Verified behavior:

- An email failure does not prevent submission storage.
- The API returns a successful submission response.
- A background outbox job is created.
- Email processing does not block the submission request.
- Failed jobs can be retried with backoff.
- A job can complete after the email service recovers.
- Permanent failures are logged.

---

## Documentation and Project Structure

### 15. Required documentation and configuration

The project includes the following important files:

```text
README.md
BUILDLOG.md
EVIDENCE.md
capstone.yaml
.env.example
.gitignore
LICENSE
docs/
    DESIGN.md
    live-test-report.html
    live-test-report.md
```

The README documents the project setup, architecture and API usage.

The design document describes the system architecture.

The environment example file provides the expected configuration structure without containing real credentials.

The `.env` file is excluded through Git ignore rules.

---

# 4. Bug Discovered During Live PostgreSQL Testing

The live suite identified a bug that was not detected by the original SQLite-based unit tests.

### Problem

A widget identifier containing a URL-encoded NUL byte could reach a PostgreSQL lookup.

Example:

```text
/widgets/%00/config
```

PostgreSQL rejects NUL bytes in text values. This caused the API to return an internal server error rather than a normal not-found response.

### Root cause

The repository lookup methods did not reject NUL-containing identifiers before executing database queries.

SQLite did not expose the same behavior during the original unit tests.

### Fix

A shared `_unsafe()` validation guard was added in:

```text
app/repo.py
```

The guard detects NUL bytes before the affected repository lookups reach PostgreSQL.

The affected lookup paths now return not found for unsafe identifiers rather than triggering a database exception.

### Verification after the fix

The live PostgreSQL suite was executed again.

The NUL-byte URL robustness checks passed, including checks against authenticated routes.

Final live result:

```text
182 passed, 0 failed, 1 skipped
```

This demonstrates why testing against the actual database engine is important: behavior that passes with SQLite may differ under PostgreSQL.

---

# 5. Manual Dashboard Verification

The project was started using Docker Compose.

The database was seeded with the demo account and three demo widgets.

The customer site was opened at:

```text
http://localhost:5500
```

The dashboard was opened at:

```text
http://localhost:5500/dashboard.html
```

The API documentation was available at:

```text
http://localhost:8000/docs
```

The three demo forms were submitted with test data:

- Newsletter: `newsletter.test@example.com`
- Contact: `alex.morgan@example.com`
- Early access: `earlyaccess.test@example.com`

The dashboard displayed:

```text
3 Submissions
3 Geo-enriched
0 Spam blocked
```

The submission list showed one record for each demo widget.

The geo information used mock provider data, so the displayed country was `Mockland`.

This verified the complete flow:

```text
Customer Website
       |
       v
Embedded Widget
       |
       v
FastAPI Submission API
       |
       v
PostgreSQL
       |
       v
Dashboard API
       |
       v
Owner Dashboard
```

---

# 6. Automated Test Reports

The complete live test reports are included in the repository:

```text
docs/live-test-report.html
docs/live-test-report.md
```

To reproduce the complete verification:

```cmd
run_tests.bat all
```

This runs:

1. The existing unit test suite.
2. The live end-to-end test suite.
3. The six acceptance probes.

The live suite uses the Docker Compose network and the running API/customer-site services.

The unit tests execute inside the API container.

---

# 7. Acceptance Probe Transcript

**Environment:** Docker Compose, PostgreSQL 16, mock geo providers  
**Date:** November 3, 2026

Command:

```cmd
docker compose exec api python -m scripts.run_probes --base http://localhost:8000
```

Transcript:

```text
PROBE 1 - cross-origin submission -> stored, 2xx, visible via dashboard API
  OPTIONS /submissions -> 204 ACAO=* ACAH=Content-Type, Idempotency-Key
  POST /submissions -> 201
  GET dashboard -> newest submission visible, geo=mock-a
  [PASS] preflight answered
  [PASS] submission 2xx with CORS header
  [PASS] visible in dashboard

PROBE 2 - malformed and oversized payloads -> clean 4xx JSON, never 500
  malformed JSON -> 400 invalid_json
  oversized body -> 413 payload_too_large
  invalid field -> 422 validation_error
  [PASS] malformed -> 400 JSON
  [PASS] oversized -> 413 JSON
  [PASS] invalid field -> 422 JSON

PROBE 3 - burst -> 429s appear, a normal request right after still succeeds
  40 rapid POSTs -> 10x 201, 30x 429
  GET config during/after flood -> 200; /healthz -> 200
  normal POST 1.5s later -> 201
  [PASS] 429s returned
  [PASS] service stays up (config + health 200)
  [PASS] normal request succeeds afterwards

PROBE 4 - geo provider fallback
  all up    -> HTTP 201, stored geo_provider=mock-a city=Alpha City
  A down    -> HTTP 201, stored geo_provider=mock-b city=Beta City
  A+B down  -> HTTP 201, stored geo_provider=None city=None
  [PASS] A up -> enriched by A
  [PASS] A down -> enriched by B
  [PASS] both down -> stored without geo

PROBE 5 - failing email side effect does not block the submission
  POST with email forced to fail -> 201
  Submission stored and outbox job created
  [PASS] submission returned 201
  [PASS] submission stored despite email failure
  [PASS] outbox job created without blocking request

PROBE 6 - honeypot filled like a bot
  POST with website field -> 201
  Bot submission not stored; spam counter increased
  [PASS] bot row not stored
  [PASS] spam counted

17/17 checks passed
```

---

# 8. Final Verification Status

| Area | Status |
|---|---|
| Authentication and authorization | Passed |
| Widget CRUD | Passed |
| Multi-tenant isolation | Passed |
| Embed snippet generation | Passed |
| Widget delivery and configuration | Passed |
| CORS and cross-origin submissions | Passed |
| Input validation and payload limits | Passed |
| Submission persistence | Passed |
| Rate limiting | Passed |
| Spam protection | Passed |
| Idempotency | Passed |
| Geo-provider fallback | Passed |
| Safe email side effects | Passed |
| Dashboard and statistics | Passed |
| PostgreSQL NUL-byte robustness | Passed |
| Unit tests | 57 passed |
| Live end-to-end tests | 182 passed, 0 failed, 1 skipped |
| Acceptance probes | 17/17 passed |

**Final assessment:** The project passed its unit tests, live Docker/PostgreSQL verification and acceptance probes. One low-severity conditional caching improvement remains documented. The verification results demonstrate that the core widget platform functionality, API behavior, persistence, tenant isolation and abuse protections work in the tested environment.