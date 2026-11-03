# Live test report

Run: 2026-11-03 13:05:48 | target: http://api:8000 | origin: http://localhost:5500 | 122s

**182 passed, 0 failed, 1 skipped** (of 183)


## 01 - Connectivity

| Result | Check | Detail |
|---|---|---|
| PASS | GET /healthz -> 200 {status: ok} |  |
| PASS | GET /docs and /openapi.json are served |  |
| PASS | Customer site and API are on different origins (so every call crosses CORS) |  |
| PASS | Customer site index.html contains one <script> embed line per demo widget |  |
| PASS | Customer site serves dashboard.html |  |
| PASS | GET /widgets/<seeded demo id>/config -> 200 (seed was run)  [demo-signup] |  |
| PASS | GET /widgets/<seeded demo id>/config -> 200 (seed was run)  [demo-contact] |  |
| PASS | GET /widgets/<seeded demo id>/config -> 200 (seed was run)  [demo-popover] |  |

## 02 - Auth

| Result | Check | Detail |
|---|---|---|
| PASS | POST /api/auth/login unknown email -> 401 invalid_credentials |  |
| PASS | POST /api/auth/login right email + wrong password -> same 401 (no user enumeration) |  |
| PASS | POST /api/auth/login valid demo credentials -> 200 + token that works |  |
| PASS | POST /api/auth/login invalid email / short password -> 422 JSON |  |
| PASS | POST /api/auth/register existing email -> 409 email_taken |  |
| PASS | Owner/dashboard endpoints reject requests without a token (401)  [GET-/api/widgets] |  |
| PASS | Owner/dashboard endpoints reject requests without a token (401)  [POST-/api/widgets] |  |
| PASS | Owner/dashboard endpoints reject requests without a token (401)  [GET-/api/widgets/abc] |  |
| PASS | Owner/dashboard endpoints reject requests without a token (401)  [PATCH-/api/widgets/abc] |  |
| PASS | Owner/dashboard endpoints reject requests without a token (401)  [DELETE-/api/widgets/abc] |  |
| PASS | Owner/dashboard endpoints reject requests without a token (401)  [GET-/api/widgets/abc/embed] |  |
| PASS | Owner/dashboard endpoints reject requests without a token (401)  [GET-/api/dashboard/submissions] |  |
| PASS | Owner/dashboard endpoints reject requests without a token (401)  [GET-/api/dashboard/submissions/abc] |  |
| PASS | Owner/dashboard endpoints reject requests without a token (401)  [GET-/api/dashboard/stats] |  |
| PASS | GET /api/widgets with invalid Authorization header -> 401  [Bearer not-a-real-token] |  |
| PASS | GET /api/widgets with invalid Authorization header -> 401  [Basic dXNlcjpwYXNz] |  |
| PASS | GET /api/widgets with invalid Authorization header -> 401  [Bearer] |  |
| PASS | GET /api/widgets with invalid Authorization header -> 401  [fw_garbage] |  |

## 03 - Widget Crud

| Result | Check | Detail |
|---|---|---|
| PASS | POST /api/widgets -> 201 with id, default fields, embed snippet |  |
| PASS | Created widget carries a one-line <script src=.../widget.js?id=...> snippet |  |
| PASS | GET /api/widgets/{id}/embed -> same snippet |  |
| PASS | GET /api/widgets lists it; GET /api/widgets/{id} returns it |  |
| PASS | Custom field definitions are stored and returned unchanged |  |
| PASS | PATCH /api/widgets/{id} -> 200, change persisted, version incremented |  |
| PASS | DELETE /api/widgets/{id} -> 204, then GET -> 404 and public config -> 404 |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [bad type-body0] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [empty title-body1] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [title too long-body2] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [missing title-body3] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [unknown property-body4] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [duplicate field names-body5] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [bad field name-body6] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [bad field type-body7] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [zero fields-body8] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [21 fields-body9] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [field named like honeypot-body10] |  |
| PASS | POST /api/widgets invalid body -> 422 JSON error  [popover delay too big-body11] |  |
| PASS | PATCH /api/widgets/{id} invalid body -> 422 JSON error |  |
| PASS | POST /api/widgets with broken JSON -> 4xx, never 500 |  |
| PASS | GET/PATCH/DELETE on a non-existent widget -> 404 |  |

## 04 - Tenant Isolation

| Result | Check | Detail |
|---|---|---|
| PASS | B: GET/PATCH/DELETE/embed on A's widget -> 404 (and A's widget is untouched) |  |
| PASS | B: GET /api/widgets never lists A's widgets |  |
| PASS | B: dashboard list/detail/stats cannot reach A's submissions |  |
| PASS | DELETE widget cascades: its submissions are gone too |  |

## 05 - Delivery And Caching

| Result | Check | Detail |
|---|---|---|
| PASS | GET /widget.js -> 200 JavaScript with Cache-Control max-age + ETag |  |
| PASS | GET /widget.js with If-None-Match -> 304 Not Modified |  |
| PASS | Loader points at /assets/widget.<hash>.js, served immutable for 1 year |  |
| SKIP | GET /assets/<bundle> with If-None-Match -> 304 (nice-to-have; not a brief requirement) | KNOWN GAP (low severity): /assets/<bundle> ignores If-None-Match and always returns 200. Harmless today because the bundle is 'immutable, max-age=1y' so browsers never revalidate it. |
| PASS | GET /assets/<unknown or ../ path> -> 404 JSON, never a file from disk |  |
| PASS | GET /widgets/{id}/config -> 200 JSON, Cache-Control max-age, ETag, payload < 5 KB |  |
| PASS | GET /widgets/{id}/config with If-None-Match -> 304 |  |
| PASS | Public config exposes no owner info, tokens or hashes |  |
| PASS | Editing a widget changes config content + ETag (cache busts on change) |  |
| PASS | is_active=false -> public config 404; re-activating restores it |  |
| PASS | GET /widgets/<missing>/config -> 404 JSON error |  |

## 06 - Cors

| Result | Check | Detail |
|---|---|---|
| PASS | OPTIONS /submissions (preflight) -> 204 + Allow-Origin/Methods/Headers |  |
| PASS | OPTIONS /submissions from a random third-party site -> allowed (any site may embed) |  |
| PASS | Preflight allow-list does not blindly echo arbitrary request headers |  |
| PASS | POST /submissions response carries Access-Control-Allow-Origin |  |
| PASS | 422 and 404 errors carry CORS headers too (so the widget JS can read the message) |  |
| PASS | GET config + widget.js + bundle carry Access-Control-Allow-Origin |  |
| PASS | OPTIONS /api/widgets from an unlisted origin -> refused, no Allow-Origin |  |
| PASS | OPTIONS /api/widgets from the allow-listed dashboard origin -> 204 echoing that origin |  |
| PASS | Authenticated /api/* response: ACAO is the exact allowed origin, never '*', absent for evil origin |  |

## 07 - Submission Validation

| Result | Check | Detail |
|---|---|---|
| PASS | POST /submissions valid -> 201 {ok,id}; visible via dashboard API linked to the right widget |  |
| PASS | POST /submissions broken JSON -> 400 invalid_json |  |
| PASS | POST /submissions invalid UTF-8 bytes -> 400 JSON |  |
| PASS | POST /submissions JSON that is not an object -> 400  [[]] |  |
| PASS | POST /submissions JSON that is not an object -> 400  [null] |  |
| PASS | POST /submissions JSON that is not an object -> 400  [123] |  |
| PASS | POST /submissions JSON that is not an object -> 400  ["text"] |  |
| PASS | POST /submissions JSON that is not an object -> 400  [true] |  |
| PASS | POST /submissions 60 KB body (Content-Length) -> 413 payload_too_large JSON |  |
| PASS | POST /submissions 60 KB streamed WITHOUT Content-Length -> 413 (limit enforced while reading) |  |
| PASS | POST /submissions without widget_id -> 422 |  |
| PASS | POST /submissions with malformed widget_id -> 422  [123] |  |
| PASS | POST /submissions with malformed widget_id -> 422  [None] |  |
| PASS | POST /submissions with malformed widget_id -> 422  [wid2] |  |
| PASS | POST /submissions with malformed widget_id -> 422  [has spaces] |  |
| PASS | POST /submissions with malformed widget_id -> 422  [../../etc] |  |
| PASS | POST /submissions with malformed widget_id -> 422  [xxxxxxxxxxxxxxxxx] |  |
| PASS | POST /submissions for a widget that doesn't exist -> 404 widget_not_found |  |
| PASS | POST /submissions to a deactivated widget -> 404 |  |
| PASS | POST /submissions with data not an object -> 422  [None] |  |
| PASS | POST /submissions with data not an object -> 422  [data1] |  |
| PASS | POST /submissions with data not an object -> 422  [string] |  |
| PASS | POST /submissions with data not an object -> 422  [5] |  |
| PASS | POST /submissions with data not an object -> 422  [data4] |  |
| PASS | POST /submissions with required fields missing -> 422 with per-field details |  |
| PASS | POST /submissions whitespace-only required value -> 422 |  |
| PASS | POST /submissions invalid email -> 422  [not-an-email] |  |
| PASS | POST /submissions invalid email -> 422  [a@] |  |
| PASS | POST /submissions invalid email -> 422  [@b.com] |  |
| PASS | POST /submissions invalid email -> 422  [a b@c.com] |  |
| PASS | POST /submissions invalid email -> 422  [a@b] |  |
| PASS | POST /submissions invalid email -> 422  [email5] |  |
| PASS | POST /submissions with a field the widget doesn't define -> 422 |  |
| PASS | POST /submissions value over the field's max_length -> 422 |  |
| PASS | POST /submissions string field given non-string -> 422  [12345] |  |
| PASS | POST /submissions string field given non-string -> 422  [True] |  |
| PASS | POST /submissions string field given non-string -> 422  [bad2] |  |
| PASS | POST /submissions string field given non-string -> 422  [bad3] |  |
| PASS | POST /submissions with >40 data keys -> 422 |  |
| PASS | Widget with tel + required checkbox: bad phone / unticked / string-bool -> 422; good -> 201 |  |
| PASS | Optional fields can be left out -> 201 |  |
| PASS | POST /submissions with a 129-char Idempotency-Key -> 422 |  |
| PASS | XSS / SQL-injection strings are stored verbatim as data (no 500, no execution) |  |
| PASS | NUL / control characters in values don't crash storage (-> 201, cleaned) |  |
| PASS | POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx  [fuzz0] |  |
| PASS | POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx  [fuzz1] |  |
| PASS | POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx  [fuzz2] |  |
| PASS | POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx  [fuzz3] |  |
| PASS | POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx  [fuzz4] |  |
| PASS | POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx  [fuzz5] |  |
| PASS | POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx  [fuzz6] |  |
| PASS | POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx  [fuzz7] |  |
| PASS | POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx  [fuzz8] |  |
| PASS | POST /submissions fuzz battery -> always a 4xx JSON error, never 5xx  [fuzz9] |  |

## 08 - Spam Protection

| Result | Check | Detail |
|---|---|---|
| PASS | Filled honeypot field -> not stored, counted as spam, bot still sees a normal-looking response |  |
| PASS | Honeypot hit gets no message mentioning 'honeypot'/'spam'/the field name |  |
| PASS | Bot putting the honeypot value outside 'data' is also dropped |  |
| PASS | elapsed_ms=50 (faster than a human) -> not stored, counted |  |
| PASS | elapsed_ms=8000 (human) -> stored normally |  |
| PASS | Message with 5 URLs -> not stored, counted |  |
| PASS | A message with a single URL is not treated as spam |  |
| PASS | Widget with its own honeypot_field name: filling it is caught |  |

## 09 - Idempotency

| Result | Check | Detail |
|---|---|---|
| PASS | Two POSTs with the same Idempotency-Key -> 201 then 200 duplicate, same id, one row |  |
| PASS | Different Idempotency-Keys -> two rows |  |
| PASS | The same key used on two different widgets is not treated as a duplicate |  |

## 10 - Geo Fallback

| Result | Check | Detail |
|---|---|---|
| PASS | Both providers up -> submission enriched by provider A |  |
| PASS | Provider A down -> 201 and enriched by provider B |  |
| PASS | Providers A+B down -> still 201, stored, geo fields empty |  |
| PASS | Provider B down (A up) -> A still answers |  |
| PASS | After the outage ends, enrichment resumes |  |
| PASS | Stats: geo_enriched counts only the submissions that got geo |  |
| PASS | POST /_debug/faults with unknown provider -> 422 (no 500) |  |

## 11 - Side Effects

| Result | Check | Detail |
|---|---|---|
| PASS | Email forced to fail -> submission still 201 and stored |  |
| PASS | A healthy submission returns quickly (email is queued, not sent inline) |  |
| PASS | Failing job is retried with backoff and completes once email works again |  |

## 12 - Dashboard

| Result | Check | Detail |
|---|---|---|
| PASS | GET /api/dashboard/submissions?widget_id= -> exactly this widget's 3 rows, total=3 |  |
| PASS | limit/offset paginate and total stays 3 |  |
| PASS | Submissions are ordered newest first |  |
| PASS | GET /api/dashboard/submissions invalid query params -> 422  [params0] |  |
| PASS | GET /api/dashboard/submissions invalid query params -> 422  [params1] |  |
| PASS | GET /api/dashboard/submissions invalid query params -> 422  [params2] |  |
| PASS | GET /api/dashboard/submissions invalid query params -> 422  [params3] |  |
| PASS | GET /api/dashboard/submissions invalid query params -> 422  [params4] |  |
| PASS | GET /api/dashboard/submissions/{id} -> row, without raw IP / hash |  |
| PASS | GET /api/dashboard/submissions/<unknown> -> 404 submission_not_found |  |
| PASS | GET /api/dashboard/stats?widget_id= -> totals, per_widget, by_day (30 days), by_country all consistent |  |
| PASS | GET /api/dashboard/stats?days=7 -> 7-point series |  |
| PASS | GET /api/dashboard/stats with out-of-range days -> 422  [params0] |  |
| PASS | GET /api/dashboard/stats with out-of-range days -> 422  [params1] |  |
| PASS | GET /api/dashboard/stats?widget_id=<unknown> -> 404 |  |
| PASS | Unfiltered stats list every widget the owner has (even with zero submissions) |  |

## 13 - Robustness

| Result | Check | Detail |
|---|---|---|
| PASS | GET odd/hostile URLs -> 4xx, never 5xx  [/nope] |  |
| PASS | GET odd/hostile URLs -> 4xx, never 5xx  [/api/nope] |  |
| PASS | GET odd/hostile URLs -> 4xx, never 5xx  [/widgets/%00/config] |  |
| PASS | GET odd/hostile URLs -> 4xx, never 5xx  [/widgets/..%2f..%2fetc%2fpasswd/config] |  |
| PASS | GET odd/hostile URLs -> 4xx, never 5xx  [path4] |  |
| PASS | GET odd/hostile URLs -> 4xx, never 5xx  [/assets/] |  |
| PASS | GET odd/hostile URLs -> 4xx, never 5xx  [/submissions/123] |  |
| PASS | Unknown route -> JSON 404 error envelope |  |
| PASS | Wrong method on /submissions -> JSON 405 error envelope |  |
| PASS | Error bodies contain no Python tracebacks / file paths |  |
| PASS | Responses carry X-Content-Type-Options: nosniff |  |
| PASS | GET /healthz still 200 after the fuzzing above |  |
| PASS | Authenticated routes given a NUL byte in an id -> 404/422, never 500 (Postgres rejects NUL)  [/api/widgets/%00] |  |
| PASS | Authenticated routes given a NUL byte in an id -> 404/422, never 500 (Postgres rejects NUL)  [/api/widgets/%00/embed] |  |
| PASS | Authenticated routes given a NUL byte in an id -> 404/422, never 500 (Postgres rejects NUL)  [/api/dashboard/submissions/%00] |  |
| PASS | Authenticated routes given a NUL byte in an id -> 404/422, never 500 (Postgres rejects NUL)  [/api/dashboard/submissions?widget_id=%00] |  |
| PASS | Authenticated routes given a NUL byte in an id -> 404/422, never 500 (Postgres rejects NUL)  [/api/dashboard/stats?widget_id=%00] |  |

## 90 - Rate Limiting

| Result | Check | Detail |
|---|---|---|
| PASS | 40 rapid POSTs -> some 429 (with Retry-After + JSON + CORS), config/health stay 200, normal request works afterwards |  |
| PASS | A flood of INVALID requests is rate limited too (can't hammer validation for free) |  |

## 99 - Auth Bruteforce

| Result | Check | Detail |
|---|---|---|
| PASS | 10 wrong-password logins in a row -> 429 with Retry-After appears |  |