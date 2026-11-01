# Async deep_research contract (0.3.0)

Accepted by the user on 2026-11-01. This supersedes the synchronous proposal in DEEP_RESEARCH_PLAN.md. Research is a new model-facing tool; ordinary web_search, web_extract routing and profile login/status/logout keep their existing behavior.

## Interface

One tool, exact name `deep_research`, toolset `perplexity-pro-research`:

- `action=start`, `query` (nonblank UTF-8, at most 16000 characters), optional `timeout_seconds` (integer 60..1800, default 900), optional `request_id` (1..128 ASCII letters/digits or `_.:-`). It returns a `job_id` quickly; it does not wait for Perplexity.
- `action=status`, `job_id`: a short read of the existing job. No SDK interpreter or valid online session is needed for status/result.
- `action=result`, `job_id`: status, sources, up to 4000 characters of preview, `truncated`, `full_report=true`, and the full private Markdown file path for a completed report. The full report is not replaced by the preview.

All actions return JSON text. Success envelope: `{"success":true,"data":{...}}`. Local operation errors: `{"success":false,"code":"...","error":"static message"}`. A successfully read failed job still has success=true with data.status=failed and a static data.code; this does not mean research succeeded.

Owner identity comes only from the native dispatcher's injected `session_id`. It is not accepted in tool arguments. Missing identity fails closed (`context`); jobs are private to both the current profile and originating session. A foreign/missing ID has the same `not_found` response. Starting a new Hermes session does not grant access to the previous session's jobs; local OS access is a separate trust boundary.

Use a stable request_id when reconciling a repeated start. The same session/key/query/timeout returns the existing job and never submits again, including after failure/interruption. Reusing the key for different input returns `conflict`. Without a key, a new start is a new explicit attempt. At most one queued/running research job is allowed per profile (`busy`).

## Execution and storage

The short handler starts a detached Python supervisor from the profile-owned external runtime. The supervisor atomically claims one SQLite job and launches one isolated SDK process with a hard process timeout. Queries are passed to the SDK child on stdin, not command-line arguments. No SDK is imported into Hermes. Child environments are allowlisted and do not inherit ambient session tokens or foreign PYTHONPATH/PYTHONHOME. Stdout/stderr of dependencies are suppressed; only a bounded structured worker payload is consumed.

The SDK uses Models.DEEP_RESEARCH explicitly, max_retries=0 and the existing profile SessionStore. No shared token loader, credential migration, interactive login, paid API fallback or automatic query retry.

Linux is required for this implementation; availability checks the descriptor APIs, safe open flags and locking primitive, not a process-filesystem mount. Private directories and files are opened through O_NOFOLLOW-pinned descriptors. SQLite never resolves the database filename itself: a cross-process flock protects descriptor-read bytes, an in-memory SQLite connection executes the transaction, and the committed SQLite image is published by private atomic replacement. This avoids the SQLite pathname-validation/open race. The metadata image is capped at 64 MiB; reports remain separate files. Python/SQLite serialization support is required (tested with Python 3.13); lock acquisition is bounded. Existing authentication restrictions still apply. No cross-platform research support is claimed.

Local data root: `$HERMES_HOME/plugin-results/perplexity-pro/research/`.

- `jobs.sqlite3`: private SQLite metadata, hashed session owner, user query, state, timing, safe error/source/question fields; no credential or signed download URL.
- `<job_id>.md`: generated filename, exclusive atomic publication, private permissions, no model-selected path or replacement of existing files.
- Directories 0700, files 0600; symlinks, hardlinks and unsafe ownership/permissions fail closed below trusted HERMES_HOME.

States: queued -> running -> completed / needs_clarification / failed. A dead local supervisor or abandoned queued startup is exposed as interrupted, never replayed automatically. Reconciliation compares the inspected row snapshot so it cannot overwrite a fresh claim. A live/ambiguous PID retains the execution slot even after a wall-clock deadline; PID reuse may require local operator investigation rather than an unsafe automatic restart or arbitrary kill. Startup has a short grace period. The SDK process deadline does not promise cancellation/refund of already accepted remote work.

## Full-report proof and trust

The pinned SDK's default full-report download can silently leave an intro. The research adapter overrides only that fetch hook and records successful retrieval explicitly. No verified separate download means incomplete, regardless of answer length.

Thread detail is retrieved through the SDK's authenticated Perplexity HTTP client. The report URL is restricted to HTTPS *.cloudfront.net, normal HTTPS port, a .md path, no credentials/fragment/control characters. Download uses a new unauthenticated session without Perplexity cookies/headers, redirects disabled, bounded streaming (5 MiB), UTF-8 and nonblank content. A new origin/format fails closed until explicitly supported. Sources are HTTP(S) allowlisted fields; credentials and signed service links are omitted.

Remote report text and clarification questions remain untrusted content, not instructions to execute commands, reveal credentials or change tools. Clarifications are returned to the user; no continuation or automatic resubmission is promised.

## Explicit exclusions

No automatic Telegram completion notification, gateway wakeup, job daemon/service installation, restart-survival guarantee, cancel API, bot/profile researcher, production activation, real login, or live research is included in this release. Completed SQLite records/reports persist on disk, but that is not proof an in-flight process survives restart. Ask for status/result after start; do not have the model busy-poll.

The SDK/client process is bounded; a supervisor crash can leave uncertain remote progress. Status detects a dead supervisor or expired unclaimed startup but never kills an arbitrary reused PID or resubmits the query. A live or reused PID may keep the profile busy until the OS owner investigates it. Additional durable supervision and notification integration need separately verified lifecycle contracts.

## Acceptance evidence

Use real loader/Doctor, model-facing definitions and native dispatcher in disposable profiles; test actual process paths with synthetic workers and absent sessions. Verify isolation, idempotency, one active job, collision refusal including same toolset, input/error boundaries, full/intro/clarification/timeout behavior, private atomic files and final archive portability. Synthetic reports and offline fixtures are not live service or model-selection evidence.

The original 0.2.0 ZIP must remain byte-identical. The final 0.3.0 archive is tested outside its source directory with a fresh SDK runtime. Working installation/config/approvals, real credentials and Perplexity quota remain untouched.
