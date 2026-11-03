# flyrank-capstone-widgetplatform

Embeddable widget & lead-capture platform (FlyRank Backend Track capstone). A customer defines a widget through an
authenticated API, pastes **one line** of `<script>` into any website, and visitors' submissions come back to a hardened public
endpoint: validated, rate-limited, spam-filtered, geo-enriched, stored, and shown on an owner dashboard.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · SQLite (default) / PostgreSQL (docker compose) · plain-JS widget · $0, no credit card.

```
 Widget owner ──(bearer)──► /api/widgets, /api/dashboard/* ─────────────┐
                                                                         ▼
 Customer site (any origin)                                    ┌──────────────────┐
   <script src="/widget.js?id=X"> ─► loader ─► /assets/widget.<hash>.js │  FastAPI app    │
        └─► GET /widgets/X/config  (public · ETag · max-age=60)         │  api → services │
 Visitor ─► POST /submissions (public · CORS)                           │  → repo → DB    │
              │ per-IP limit → size cap → JSON → widget → per-widget    └───────┬─────────┘
              │ limit → honeypot/timing/links → field validation               │
              │ → idempotency → geo: A ─fail→ B ─fail→ none                     ▼
              └→ ONE tx: INSERT submission + INSERT job(outbox) → 201     DB: owners, widgets,
                                                                          submissions, jobs, spam_events
 Background worker: jobs → confirmation email (retry+backoff → ALERT)
```

## Run it (one command)
```bash
docker compose up --build                              # API :8000 (Postgres), customer site :5500
docker compose exec api python -m scripts.seed         # demo owner + 3 widgets; prints a bearer token
# open http://localhost:5500  -> widgets rendered from another origin
# open http://localhost:5500/dashboard.html  -> owner dashboard (demo@example.com / demo-password-123)
```
Without Docker (SQLite), macOS/Linux:
```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env && set -a && . ./.env && set +a
uvicorn app.main:app_factory --factory --port 8000 &
python -m http.server 5500 --directory demo &
python -m scripts.seed
```

Without Docker (SQLite), Windows PowerShell (run each line in the project folder):
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///./data/app.db"
$env:SECRET_KEY = "replace-with-a-long-random-secret"
$env:DEBUG_ENDPOINTS = "1"
$env:GEO_MODE = "mock"
Start-Process -NoNewWindow python -ArgumentList "-m","uvicorn","app.main:app_factory","--factory","--port","8000"
Start-Process -NoNewWindow python -ArgumentList "-m","http.server","5500","--directory","demo"
python -m scripts.seed
```
Open `http://localhost:5500`. The API is at `http://localhost:8000`. Keep the two server processes running while testing.
Tests (no Docker/network; SQLite + mock geo): `python -m pytest -q` · Acceptance probes against a live server: `python -m scripts.run_probes` · Live end-to-end suite against the running Docker stack (Windows): `run_tests.bat`

## API
| | Endpoint | Notes |
|---|---|---|
| owner | `POST /api/auth/register`, `POST /api/auth/login` | -> `{token}`; send `Authorization: Bearer …` |
| owner | `POST/GET /api/widgets`, `GET/PATCH/DELETE /api/widgets/{id}`, `GET …/{id}/embed` | tenant-isolated; response includes `embed_snippet` |
| owner | `GET /api/dashboard/submissions?widget_id&limit&offset&days`, `GET …/submissions/{id}` | paginated |
| owner | `GET /api/dashboard/stats?widget_id&days` | totals, per-widget, per-day (zero-filled), country breakdown, spam blocked |
| public | `GET /widget.js?id=` | loader, `max-age=300` + ETag |
| public | `GET /assets/widget.<hash>.js` | `max-age=31536000, immutable`; hash changes with content |
| public | `GET /widgets/{id}/config` | ~600 B, `max-age=60, stale-while-revalidate=300`, ETag → 304 |
| public | `POST /submissions` | body `{"widget_id","data":{…}}`, optional `Idempotency-Key` header |
| ops | `GET /healthz` | status + job counts |
| dev | `GET/POST /_debug/faults`, `POST /_debug/drain-jobs` | only when `DEBUG_ENDPOINTS=1` |

Errors always look like `{"error":{"code","message","details?"}}`: `400 invalid_json` · `401` · `404` · `413` · `422 validation_error` · `429 rate_limited` (+`Retry-After`) · never a stack trace, never HTML.

## Why it is built this way
* **CORS is path-aware.** Public endpoints answer `*` (they use no cookies, so that exposes nothing extra); the owner API only answers origins in `ADMIN_CORS_ORIGINS`. Preflights are answered in middleware before routing; errors and 500s carry CORS headers too (otherwise the browser reports a misleading "CORS error").
* **Two-layer caching.** The loader is tiny and short-lived; the bundle URL contains a content hash so it is cached forever and busts itself on release. Config uses short max-age + ETag so edits propagate within a minute.
* **Rate limiting** is a token bucket per IP *and* per widget (a distributed flood can't drown one owner). The IP check is first so junk is rejected cheaply. Burst 10, refill 2/s - a flooding IP recovers on its own.
* **Spam:** per-widget honeypot (silently returns the same 201 so bots learn nothing), too-fast-to-be-human timing (`elapsed_ms`), link stuffing. Every drop is counted in `spam_events`.
* **Fallback chain:** ip-api.com → ipapi.co (live) or deterministic mocks (`GEO_MODE=mock`) with `/_debug/faults` toggles. Each row records which provider answered. Per-provider timeout; total failure returns `None`, never an exception.
* **Safe side effects = transactional outbox.** The submission and its email job commit together; a worker sends later with exponential backoff and logs `ALERT` after `JOB_MAX_ATTEMPTS`. SMTP down can't slow or fail a submission, and a crash can't lose an email.
* **Idempotency:** the widget sends one `Idempotency-Key` per form instance; a unique `(widget_id, key)` index makes a retried POST store once (returns `200 duplicate:true`).
* **Privacy:** raw visitor IPs are never stored (keyed hash only); passwords are scrypt-hashed; API tokens are stored as sha256; widget renders server data with `textContent` in a Shadow DOM (no XSS, no CSS bleed).

## Shared requirements checklist
Layered architecture ✔ · validation at the boundary ✔ · background job (retries + failure alert) ✔ · migrations + indexes + tenancy ✔ · idempotency ✔ · secrets in env only (`.env.example`, scrypt/sha256, nothing secret logged) ✔ · AI cost tracking: **N/A** (no AI calls at runtime).

## Limitations (honest)
* Rate-limit buckets and the job worker are in-process: fine for one instance; use Redis / a dedicated worker for several. `X-Forwarded-For` is only trusted with `TRUST_PROXY=1` behind exactly one proxy.
* No geo-result caching, deliberately - it would hide provider A/B behaviour during the fallback proofs. Live providers are rate-limited (ip-api 45/min); `GEO_MODE=live` skips private IPs, so localhost submissions get no geo.
* Config edits take up to ~60 s to reach browsers (max-age) - the price of caching.
* Webhooks are a non-goal (see `docs/DESIGN.md`). Deleting a widget cascades to its submissions.
* The unit tests (`pytest`) run on SQLite. The live end-to-end suite (`run_tests.bat`: 182 pass, 1 documented skip, see `docs/live-test-report.md`) runs against the real `docker compose` stack with PostgreSQL.
* **Dev defaults are not production settings.** `DEBUG_ENDPOINTS=1` is on in the demo compose file so probes can inject faults, and `SECRET_KEY` falls back to a placeholder (`dev-only-change-me`). In production: set `DEBUG_ENDPOINTS=0`, set a long random `SECRET_KEY` (it keys the visitor-IP hash), and remove the seeded demo account (`demo@example.com`).
