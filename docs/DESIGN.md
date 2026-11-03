# Design doc (Phase 1)

**Problem.** Customers want a lead-capture form on *their* website without running any backend. They
create a widget through our API, paste one `<script>` line, and visitors' submissions come back to us
over the open internet - so every byte is untrusted, traffic is uncontrolled, and the origin is unknown.

## Data model (see `migrations/001_init.sql`)
| Table | Purpose | Key indexes |
|---|---|---|
| `owners`, `api_tokens` | tenants + opaque bearer tokens (only the sha256 of a token is stored) | `owners.email` unique; `api_tokens(owner_id)` |
| `widgets` | type, copy, `fields_json`, `display_json`, per-widget `honeypot_field`, `version` (bumped on edit -> new ETag) | `(owner_id, created_at)` |
| `submissions` | cleaned `data_json`, keyed `ip_hash` (never raw IP), geo columns + which provider answered, `idempotency_key` | `(widget_id, created_at)`, `(owner_id, created_at)`, **unique** `(widget_id, idempotency_key)` |
| `spam_events` | one row per dropped submission (reason) -> dashboard "spam blocked" | `(widget_id, created_at)` |
| `jobs` | transactional outbox for side effects (status, attempts, backoff `run_at`, `last_error`) | `(status, run_at)` |

Tenancy: `owner_id` is on every tenant row and **every repository query takes it**; a foreign id is a 404 (not 403) so existence doesn't leak.

## The embed flow
`<script src=".../widget.js?id=X">` -> loader (5 min cache) injects `/assets/widget.<hash>.js` (immutable, 1 yr) ->
bundle `GET /widgets/X/config` (60 s + ETag/304, simple request = no preflight) -> renders in a Shadow DOM ->
`POST /submissions` with `Idempotency-Key` (JSON => preflight, handled by our CORS middleware).

## API surface - three request paths, kept separate
1. **Owner (bearer auth, CORS only for `ADMIN_CORS_ORIGINS`)** - `/api/auth/*`, `/api/widgets[/{id}[/embed]]`, `/api/dashboard/{submissions,stats}`
2. **Customer site (public, cached, CORS `*`)** - `GET /widget.js`, `GET /assets/{file}`, `GET /widgets/{id}/config`
3. **Visitor (public, CORS `*`, protected)** - `POST /submissions`

## Layers
`app/api/*` (HTTP only: parse, status codes, headers) -> `app/services/*` (rules: validation, spam, geo chain, jobs) -> `app/repo.py` (SQL) -> migrations. Routers never touch SQL; the repo never knows about HTTP.

## Submission pipeline (order is deliberate: cheapest rejection first)
per-IP bucket -> bounded body read (413) -> strict JSON (400) -> envelope check (422) -> widget lookup (404) ->
per-widget bucket (429) -> spam checks (silent drop) -> field validation (422) -> idempotency lookup ->
geo chain -> **one transaction**: insert submission + insert email job -> 201.

## Failure policy
Critical path = validate, store. Everything else degrades: geo failure => stored without geo; email failure => job retries with
backoff then logs `ALERT` - the 201 was already returned.

## Explicit non-goals
* **Webhooks to owners** (the brief says "email / webhook"; I implement the email side effect only, through the same outbox so a webhook is one more job kind).
* Real CDN/domain/hosting, a form-builder UI, Redis-backed shared rate limits, CAPTCHA, GDPR export/delete.
