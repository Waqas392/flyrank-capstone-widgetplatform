# Live test suite

One command, against the stack that is already running (`docker compose up --build`):

    run_tests.bat            (double-click works too)

Needs only Docker. It runs the tests inside a throw-away container on the compose network,
so no Python install is required on Windows. Results: console summary + `livetests/report/report.html`.

Other modes: `run_tests.bat all` (unit + live + probes), `unit`, `probes`, `local`.

## What it covers
| Area | Examples |
|---|---|
| Connectivity | health, Swagger, customer site on a second origin embeds all 3 widgets |
| Auth | wrong creds 401, no user enumeration, garbage tokens, every protected route rejects anonymous calls |
| Widget CRUD | create/list/get/patch/delete, embed snippet, 12 invalid-body cases -> 422 |
| Tenant isolation | owner B cannot read/patch/delete/embed A's widgets or read A's submissions/stats |
| Delivery & caching | versioned immutable bundle (hash == content), ETag/304, config max-age, inactive widgets hidden |
| CORS | preflight, wildcard on public routes, admin routes locked to the dashboard origin, errors carry CORS |
| Submission validation | malformed/oversized (declared + chunked)/non-object/fuzz bodies -> 4xx JSON, never 500 |
| Spam | honeypot, too-fast, link stuffing, custom honeypot name; blocked rows are not stored and are counted |
| Idempotency | same key stored once |
| Geo fallback | A -> B -> store without geo -> recovery (mock providers via /_debug/faults) |
| Safe side effects | email failure never blocks/loses a submission; job queued; retried and recovers |
| Dashboard | totals, pagination, per-widget, by-day, by-country, privacy (no raw IP) |
| Rate limiting | 40-request burst -> 429 + Retry-After + CORS; health/config stay up; recovery; login brute-force |

## Safety
* Uses two throw-away owners (`livetest-a@example.com`, `livetest-b@example.com`) - the demo owner's data is never touched.
* Every widget it creates is deleted at the end (submissions cascade).
* Fault switches are reset at start and end. No application code is changed.

## Known limits
* HTTP-level only: it proves the loader/bundle/config/CORS contract, not pixels. Eyeball http://localhost:5500 for rendering.
* The per-widget limiter (60 burst) can't be isolated from the per-IP limiter (10 burst) from a single client IP.
