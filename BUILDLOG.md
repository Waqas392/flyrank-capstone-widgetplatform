# BUILDLOG.md — AI Usage and Development Log

Honesty is more important than claiming the project was built entirely by hand. This document records where AI tools were used, what problems were discovered, what was fixed, and what I verified myself.

## 1. How This Repository Was Developed

The first version of this project, including its architecture, application code, tests and documentation, was generated with Claude (Anthropic) in a single development session using the supplied FlyRank capstone brief.

The implementation was subsequently reviewed with ChatGPT. Additional development and verification work included a live end-to-end testing suite, PostgreSQL-specific bug investigation, repository-layer fixes and documentation updates.

The commit history represents development phases rather than a day-by-day record of manual coding.

AI assistance was used extensively, but I am responsible for understanding the implementation and being able to explain its important design decisions and code.

## 2. Where AI Helped

AI tools assisted with the following parts of the project:

- Selecting the application architecture, including the separation between API routes, services and repository operations.
- Designing the email outbox pattern, token-bucket rate limiter and path-aware CORS configuration.
- Generating database migrations and FastAPI application code.
- Implementing the embeddable JavaScript widget, loader and versioned asset delivery.
- Creating the customer demo pages and owner dashboard.
- Generating the original 57 unit tests and acceptance probe script.
- Preparing Docker configuration, environment examples and project documentation.
- Developing the additional `livetests/` suite and `run_tests.bat` to test the application against the actual Docker Compose environment, including PostgreSQL and the separate customer website.

AI-generated code was reviewed and tested during subsequent verification passes.

## 3. Problems Discovered and Corrections Made

### 3.1 ETag comparison bug

The original conditional request implementation did not correctly normalise weak ETags.

The server and client values were not being compared consistently because the `W/` prefix was removed from the client's value but not properly normalised on both sides.

**Correction:** Both values are now normalised in `app/api/public.py`, inside `_not_modified()`.

Conditional requests for the supported loader and widget configuration endpoints can return `304 Not Modified`.

### 3.2 Widget source inspection test failure

One test that searched the widget source code for `innerHTML` failed because the word appeared in a code comment rather than an actual unsafe implementation.

**Correction:** The comment was reworded so that the source-inspection test could distinguish the comment from actual code usage.

### 3.3 Development server process issue

An initial live-probe attempt failed because the API server was started in a way that caused it to terminate when its shell session ended.

**Correction:** The API was restarted in detached mode so that the probe script could communicate with the running service.

This was an environment and process-management issue, not an application bug.

### 3.4 PostgreSQL NUL-byte bug

The live test suite discovered an issue that the original SQLite-based unit tests did not detect.

The following request returned an internal server error:

```text
GET /widgets/%00/config
```

The `%00` URL-encoded value represents a NUL byte. PostgreSQL rejects NUL bytes in text values, and the database exception resulted in an HTTP 500 response.

SQLite did not expose the same behavior during the original unit tests.

**Correction:** A shared `_unsafe()` guard was added in `app/repo.py` to reject NUL-containing identifiers before the affected database lookups are executed.

The guard was applied to:

- `get_widget_public`
- `get_widget_for_owner`
- `get_submission_for_owner`

Unsafe identifiers now produce normal not-found responses rather than database errors.

Additional authenticated robustness checks were added for NUL-containing identifiers, including widget routes, embed routes, submission detail and dashboard filters.

The updated live suite was rebuilt and executed against PostgreSQL. The NUL-byte checks passed.

### 3.5 Incorrect expected live-test count

An earlier AI-generated instruction incorrectly predicted 183 passing live tests.

The final verified result is:

```text
182 passed, 0 failed, 1 skipped
```

This represents 183 live checks in total, including the skipped check.

The skipped check concerns conditional ETag handling for versioned assets, which is documented in the known limitations section.

An older copy of the test suite was also used briefly during development. The updated test files were subsequently extracted and the suite was executed again.

### 3.6 Tests executed from the wrong container address

Running the tests directly with:

```cmd
docker compose exec api pytest
```

caused three customer-site connectivity checks to fail.

Inside the API container, `localhost:5500` refers to the API container itself, not the separate customer-site container.

This was a test-environment addressing issue rather than a failure of the customer website.

**Correction:** The live testing script was adjusted to handle an unreachable default customer-site address appropriately. The `run_tests.bat` runner uses the correct container network addresses when executing the live suite.

The updated test suite also handles the distinction between an optional default site address and an explicitly configured site address.

## 4. Known Limitation

The versioned JavaScript asset endpoint does not currently return `304 Not Modified` when it receives an `If-None-Match` header.

The endpoint returns `200` instead.

However, the versioned bundle is served with:

```text
Cache-Control: public, max-age=31536000, immutable
```

Because the bundle URL contains a content hash and is immutable, browsers can reuse the cached resource without normal revalidation.

The live suite marks this check as skipped rather than claiming that the behavior is implemented.

This is a low-severity improvement that remains outside the current required functionality.

## 5. Technical Decisions to Understand

The following are important implementation decisions that I should be able to explain during project evaluation.

- **404 instead of 403 for other tenants' resources:** Hides whether another owner's resource exists.
- **Honeypot responses:** Bots receive the same successful-looking `201` response as normal submissions, but detected spam is not stored as a legitimate submission.
- **IP privacy:** Raw IP addresses are not stored. A keyed hash is used instead, so the dashboard cannot display raw IP addresses.
- **Geo-provider fallback:** Provider B is used when provider A fails. If both providers fail, the submission is still stored without geo-enrichment.
- **Email processing:** Email work is handled through a database outbox and worker so that email failures do not block submission storage.
- **Webhooks:** Webhook delivery is outside the implemented project scope.
- **Rate limiting:** The application uses rate limits at different levels. The per-widget limit is covered by a unit test because it cannot be isolated from the per-IP limit using a single client IP in the live suite.

## 6. Verification Status

### Verified on my machine

The application was tested using Docker Compose and PostgreSQL 16.

The following activities were completed:

- Started the Docker Compose application stack.
- Verified the API, customer website and database containers.
- Seeded the database with the demo account and widgets.
- Opened the customer website on a separate origin from the API.
- Verified that the newsletter, contact and early-access widgets rendered.
- Submitted test data through all three widgets.
- Confirmed that the dashboard displayed the resulting submissions.
- Rebuilt the application after the PostgreSQL NUL-byte fix.
- Executed the unit tests, live end-to-end suite and acceptance probes.

Final verification results on November 3, 2026:

| Test suite | Result |
|---|---|
| Unit tests | 57 passed |
| Live end-to-end tests | 182 passed, 0 failed, 1 skipped |
| Acceptance probes | 17/17 passed |

The live test reports are saved in:

```text
docs/live-test-report.html
docs/live-test-report.md
```

### Not verified

Live integration with the external geo-IP providers `ip-api.com` and `ipapi.co` was not established during this verification.

Mock geo providers were used for the fallback tests. This allowed the provider success, failure and recovery scenarios to be tested deterministically.

## 7. My Development Notes

### What I changed and why

I applied the NUL-byte validation fix in `app/repo.py` after the live PostgreSQL test revealed that unsafe identifiers could cause database errors. I rebuilt the Docker containers and reran the live suite to verify that the issue was resolved.

### A bug or problem I encountered while testing

The most important application bug was the PostgreSQL NUL-byte issue. It passed the original SQLite tests but failed against PostgreSQL.

I also encountered Docker Desktop not running during the initial setup and a container-address problem when I first ran customer-site checks from inside the API container.

These experiences helped me understand why testing against the actual deployment environment is important.

### Two lines of code I can explain in my own words

**1. NUL-byte validation — `app/repo.py`**

```python
return "\x00" in value
```

This checks whether an identifier contains a NUL byte. PostgreSQL rejects NUL bytes in text values, so checking before the database query prevents an internal server error and allows the API to return a normal not-found response.

**2. Token-bucket rate limiting — `app/services/ratelimit.py`**

```python
tokens = min(self.capacity, tokens + (now - last) * self.refill)
```

This calculates how many tokens a client has after accounting for the time since its previous request. Tokens refill over time, but the bucket cannot exceed its maximum capacity. Requests consume tokens, and requests are rate-limited when the bucket is empty.

## 8. Follow-up Audit and Completion Pass

A later review against the supplied FlyRank capstone brief was performed with ChatGPT.

The original application architecture was retained, while several supporting issues were corrected:

- The live acceptance probe for email side effects was adjusted to verify that the submission is stored and exactly one outbox job is created. Retry, backoff and permanent-failure behavior are covered separately by unit tests.
- Windows PowerShell setup instructions were added to the README.
- Missing worker settings were added to `.env.example`.
- Configurable application settings were mapped through Docker Compose so that values from the Compose environment file reach the API container.

The audit environment also verified:

```text
57 unit tests passed
17/17 acceptance probes passed
```

A separate worker-enabled runtime accepted a submission and successfully changed its outbox job status to `done`.

The Docker Compose and PostgreSQL verification was subsequently completed on my machine, with the final results documented in Section 6.

---

## Final Note

This log records the use of AI tools, the issues discovered during development, the corrections made and the verification performed.

The project was not developed entirely through manual coding. AI tools played a substantial role in generating the initial implementation and supporting later development. My responsibility is to understand the architecture, explain the important implementation decisions and demonstrate the behavior of the finished system.