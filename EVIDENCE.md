# EVIDENCE.md - one proof per Requirements box (Section 6)

All outputs below were produced by running this repo: `python -m pytest -v` (SQLite, mock geo) and
`python -m scripts.run_probes` against a live `uvicorn` + `python -m http.server 5500` (the second origin), plus a headless
Chromium run for the render proof. Re-run them yourself - they are deterministic.

**Full test run: see "Test names" at the bottom - all green.**

## Widget management
1. **Authenticated CRUD; requests without valid auth rejected.**
   Tests: `test_widgets_and_tenancy.py::test_widget_endpoints_reject_missing_or_bad_auth` (401 for missing / bogus bearer),
   `::test_widget_crud_and_embed_snippet` (201 create, 200 get/list/patch, 204 delete, 404 after delete),
   `::test_widget_validation_errors_are_422_json`. Live: `curl -s localhost:8000/api/widgets` ->
   `HTTP/1.1 401 {"error":{"code":"unauthorized","message":"Missing or invalid credentials"}}` (curl block below).
2. **Multi-tenant isolation.** `test_widgets_and_tenancy.py::test_tenant_isolation_widgets_and_submissions` - tenant A gets **404** on
   B's widget for GET/PATCH/DELETE/embed, B's widget is unchanged afterwards, A's widget list and dashboard list/by-id/by-filter/stats
   contain none of B's data (A sees 1 submission, its own).

## Widget delivery
3. **Embed snippet generated per widget.** `test_widget_crud_and_embed_snippet` asserts
   `<script src="http://testserver/widget.js?id=<id>" async></script>`; live: `GET /api/widgets/demo-contact/embed` ->
   `{"widget_id":"demo-contact","embed_snippet":"<script src=\"http://localhost:8000/widget.js?id=demo-contact\" async></script>"}`.
4. **Public config, small payload, correct cache headers.** `test_delivery.py::test_config_is_public_small_and_cacheable` (<2 KB, `public`, `max-age`, ETag,
   `If-None-Match` -> 304 empty body) and `::test_config_etag_changes_when_widget_changes`. Live: `cache-control: public, max-age=60, stale-while-revalidate=300`, `content-length: 588`.
5. **Versioned bundle.** `test_loader_is_short_cached_and_points_at_versioned_immutable_bundle`
   (`/assets/widget.<10-hex>.js` -> `public, max-age=31536000, immutable`; a wrong hash -> 404) and
   `test_bundle_url_changes_when_content_changes` (edit file -> new URL). Live: loader `max-age=300` -> `/assets/widget.339bb676e9.js` immutable.
6. **Widget renders on a page from a different origin.** Headless Chromium loaded `http://localhost:5500/` (script from `:8000`): 2 widgets attached
   (the 3rd is the 3-second popover), no console errors; the contact form was filled and submitted through the Shadow DOM, the widget showed
   "Thanks! We got your details.", and the row appeared in the dashboard API:
   `{"widget_id": "demo-contact", "data": {"name": "Browser Test", "email": "browser@example.com", ...}, "geo_provider": "mock-a"}`.
   Screenshot: `docs/widget-second-origin.png`. (**Take your own screenshot with Docker running for your submission.**)

## Public submission API
7. **Cross-origin submissions; CORS + preflight.** `test_cors.py::test_preflight_for_submissions_is_answered` (204, `*`, allows `Content-Type, Idempotency-Key`, max-age 86400),
   `::test_actual_responses_carry_cors_headers_even_on_errors`, `::test_admin_api_is_not_open_to_arbitrary_origins`. Probe 1 below shows `OPTIONS /submissions -> 204 ACAO=*`.
8. **Malformed and oversized payloads -> 4xx JSON.** `test_submissions.py::test_malformed_json_is_400`, `::test_oversized_payload_is_413` (Content-Length *and* chunked),
   `::test_oversized_field_is_422_not_500`, `::test_invalid_field_values_are_422` (9 cases), `::test_junk_envelopes_never_500` (10 cases incl. SQL-injection-looking ids). Probe 2 below.
9. **Valid submissions stored, linked to widget and tenant.** `::test_valid_submission_is_stored_enriched_and_visible_in_dashboard`, `::test_raw_ip_is_never_stored`,
   tenancy test above; `::test_idempotency_key_stores_once_and_enqueues_one_email` (retried POST stored once).

## Abuse protection
10. **Rate limiting returns 429 under a burst; API keeps serving.** `::test_burst_gets_429s_service_stays_up_and_client_recovers`, `::test_per_widget_limit_protects_owner_from_distributed_flood`.
    Probe 3 below: `40 rapid POSTs -> 10x 201, 30x 429`, config/healthz still 200 during the flood, normal POST 1.5 s later -> 201.
11. **Spam control demonstrably blocks.** `::test_honeypot_blocks_bot_silently` (201 to the bot, 0 rows stored, `spam_blocked` = 1), `::test_other_spam_heuristics`. Probe 6 below.

## Enrichment & safe side effects
12. **Fallback chain A -> B.** `::test_geo_fallback_chain` (all up -> `mock-a`; A down -> `mock-b`, city "Beta City"), `::test_live_geo_chain_survives_real_provider_errors` (exception + timeout + success). Probe 4.
13. **All providers down -> stored without geo.** same test (`geo_provider is None`) - Probe 4 line `A+B down -> HTTP 201, stored geo_provider=None`.
14. **Failing email/webhook does not block storing.** `::test_failing_email_does_not_block_submission` (201, stored, job ends `failed` after 3 attempts),
    `::test_job_retries_then_succeeds_when_email_recovers`, `::test_job_alert_is_logged_on_permanent_failure`. Probe 5.

## Documentation
15. **README with architecture diagram, setup, API docs; required files present.** `README.md`, `capstone.yaml`, `EVIDENCE.md`, `BUILDLOG.md`, `.env.example`, `LICENSE`, `docs/DESIGN.md`; `.env` is git-ignored.

---
## Probe transcript (`python -m scripts.run_probes`, live server)
```
PROBE 1 - cross-origin submission -> stored, 2xx, visible via dashboard API
  OPTIONS /submissions -> 204 ACAO=* ACAH=Content-Type, Idempotency-Key
  POST /submissions -> 201 {"ok":true,"id":"b9f0ffcec1da164dd68f66b6","duplicate":false}
  GET dashboard -> newest: b9f0ffcec1da164dd68f66b6 geo=mock-a
  [PASS] preflight answered
  [PASS] submission 2xx with CORS header
  [PASS] visible in dashboard

PROBE 2 - malformed and oversized payloads -> clean 4xx JSON, never 500
  malformed JSON -> 400 {"error":{"code":"invalid_json","message":"Request body must be valid JSON"}}
  oversized body -> 413 {"error":{"code":"payload_too_large","message":"Request body exceeds 16384 bytes"}}
  invalid field -> 422 {"error":{"code":"validation_error","message":"Submission failed validation","details":[{"field":"name","problem":"required"},{"field":"emai
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
  POST with email forced to fail -> 201 {"ok":true,"id":"5f4f47fca78e7edf44d3f126","duplicate":false}
  worker drain -> {'processed': 2}; /healthz jobs={'done': 14, 'pending': 2}
  [PASS] submission returned 201
  [PASS] submission stored despite email failure

PROBE 6 - honeypot filled like a bot
  POST with website=... -> 201 {"ok":true,"id":"4584870627614ca37339ffb8","duplicate":false}
  spam_blocked 0 -> 1; 'BOT' stored? False
  [PASS] bot row not stored
  [PASS] spam counted

16/16 checks passed
```

## curl transcript (live server)
```
$ curl -si localhost:8000/widgets/demo-contact/config -H "Origin: http://localhost:5500"
HTTP/1.1 200 OK
cache-control: public, max-age=60, stale-while-revalidate=300
etag: W/"demo-contact-v1"
content-length: 588
content-type: application/json
access-control-allow-origin: *
access-control-expose-headers: Retry-After, ETag
{"id": "demo-contact", "type": "contact_form", "title": "Contact us", "description": "We reply within a day.", "button_text": "Send message", "fields": [{"name": "name", "label": "Name", "type": "text

$ curl -si localhost:8000/widget.js?id=demo-contact  (loader)
HTTP/1.1 200 OK
cache-control: public, max-age=300
etag: "b8e9be00bc"
content-type: application/javascript; charset=utf-8
/* Tiny loader served at /widget.js (short cache). It pulls in the content-hashed bundle (cached forever). */
  b.src = u.origin + "/assets/widget.339bb676e9.js";

$ curl -si localhost:8000/assets/widget.339bb676e9.js  (versioned bundle)
HTTP/1.1 200 OK
cache-control: public, max-age=31536000, immutable
etag: "339bb676e9"
content-length: 6292
content-type: application/javascript; charset=utf-8

$ curl -si localhost:5500/ | grep script   (customer site, second origin)
HTTP/1.0 200 OK
  <script src="http://localhost:8000/widget.js?id=demo-signup" async></script>
  <script src="http://localhost:8000/widget.js?id=demo-contact" async></script>
  <script src="http://localhost:8000/widget.js?id=demo-popover" async></script>

$ curl -s localhost:8000/api/widgets  (no auth)
HTTP/1.1 401 Unauthorized
{"error":{"code":"unauthorized","message":"Missing or invalid credentials"}}

$ curl -s localhost:8000/api/widgets/demo-contact/embed -H "Authorization: Bearer <token>"
{"widget_id":"demo-contact","embed_snippet":"<script src=\"http://localhost:8000/widget.js?id=demo-contact\" async></script>"}

(dashboard stats output: see Probe 6 and the tests above)
```

## Test names (`python -m pytest -v`)
```
test_cors.py::test_preflight_for_submissions_is_answered PASSED
test_cors.py::test_actual_responses_carry_cors_headers_even_on_errors PASSED
test_cors.py::test_admin_api_is_not_open_to_arbitrary_origins PASSED
test_dashboard_and_infra.py::test_dashboard_stats_shape PASSED
test_dashboard_and_infra.py::test_dashboard_pagination_and_filters PASSED
test_dashboard_and_infra.py::test_migrations_are_idempotent PASSED
test_dashboard_and_infra.py::test_deleting_widget_removes_its_submissions PASSED
test_dashboard_and_infra.py::test_errors_are_json_never_html PASSED
test_dashboard_and_infra.py::test_debug_endpoints_absent_when_disabled PASSED
test_delivery.py::test_config_is_public_small_and_cacheable PASSED
test_delivery.py::test_config_etag_changes_when_widget_changes PASSED
test_delivery.py::test_unknown_or_inactive_widget_config_404 PASSED
test_delivery.py::test_loader_is_short_cached_and_points_at_versioned_immutable_bundle PASSED
test_delivery.py::test_bundle_url_changes_when_content_changes PASSED
test_delivery.py::test_widget_js_never_parses_server_data_as_markup PASSED
test_submissions.py::test_valid_submission_is_stored_enriched_and_visible_in_dashboard PASSED
test_submissions.py::test_raw_ip_is_never_stored PASSED
test_submissions.py::test_malformed_json_is_400 PASSED
test_submissions.py::test_oversized_payload_is_413 PASSED
test_submissions.py::test_oversized_field_is_422_not_500 PASSED
test_submissions.py::test_invalid_field_values_are_422[data0] PASSED
test_submissions.py::test_invalid_field_values_are_422[data1] PASSED
test_submissions.py::test_invalid_field_values_are_422[data2] PASSED
test_submissions.py::test_invalid_field_values_are_422[data3] PASSED
test_submissions.py::test_invalid_field_values_are_422[data4] PASSED
test_submissions.py::test_invalid_field_values_are_422[data5] PASSED
test_submissions.py::test_invalid_field_values_are_422[data6] PASSED
test_submissions.py::test_invalid_field_values_are_422[data7] PASSED
test_submissions.py::test_invalid_field_values_are_422[data8] PASSED
test_submissions.py::test_junk_envelopes_never_500[payload0] PASSED
test_submissions.py::test_junk_envelopes_never_500[payload1] PASSED
test_submissions.py::test_junk_envelopes_never_500[payload2] PASSED
test_submissions.py::test_junk_envelopes_never_500[payload3] PASSED
test_submissions.py::test_junk_envelopes_never_500[payload4] PASSED
test_submissions.py::test_junk_envelopes_never_500[payload5] PASSED
test_submissions.py::test_junk_envelopes_never_500[payload6] PASSED
test_submissions.py::test_junk_envelopes_never_500[payload7] PASSED
test_submissions.py::test_junk_envelopes_never_500[payload8] PASSED
test_submissions.py::test_junk_envelopes_never_500[payload9] PASSED
test_submissions.py::test_unknown_widget_is_404_and_bad_idempotency_key_422 PASSED
test_submissions.py::test_control_characters_are_stripped PASSED
test_submissions.py::test_idempotency_key_stores_once_and_enqueues_one_email PASSED
test_submissions.py::test_burst_gets_429s_service_stays_up_and_client_recovers PASSED
test_submissions.py::test_per_widget_limit_protects_owner_from_distributed_flood PASSED
test_submissions.py::test_honeypot_blocks_bot_silently PASSED
test_submissions.py::test_other_spam_heuristics PASSED
test_submissions.py::test_geo_fallback_chain PASSED
test_submissions.py::test_live_geo_chain_survives_real_provider_errors PASSED
test_submissions.py::test_failing_email_does_not_block_submission PASSED
test_submissions.py::test_job_retries_then_succeeds_when_email_recovers PASSED
test_submissions.py::test_job_alert_is_logged_on_permanent_failure PASSED
test_widgets_and_tenancy.py::test_widget_endpoints_reject_missing_or_bad_auth PASSED
test_widgets_and_tenancy.py::test_widget_crud_and_embed_snippet PASSED
test_widgets_and_tenancy.py::test_widget_validation_errors_are_422_json PASSED
test_widgets_and_tenancy.py::test_tenant_isolation_widgets_and_submissions PASSED
test_widgets_and_tenancy.py::test_login_and_duplicate_registration PASSED
test_widgets_and_tenancy.py::test_password_is_hashed_and_tokens_stored_hashed PASSED
============================== 57 passed in 7.57s ==============================
```
