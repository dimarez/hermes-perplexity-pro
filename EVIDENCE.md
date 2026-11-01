# Historical evidence and limits — hermes-perplexity-pro 0.3.0

The record below describes the original 0.3.0 implementation. Current 0.3.2 changes
and acceptance criteria are in `docs/PACKAGING_0.3.2.md`; fresh local command output
is in the generated `docs/verification.json`, and publication evidence is recorded
separately. In 0.3.2 auth UI/status text and the storage availability gate change;
do not apply the historical unchanged-auth claim below to this newer diff.

Date: 2026-11-01. Local development and isolated offline acceptance only.

## Scope and provenance

The user accepted a separate tool with exact name **deep_research**, then the minimal asynchronous start/status/result contract in `docs/ASYNC_RESEARCH.md`. This is implemented as short native tool actions, a separate bounded SDK supervisor/worker, profile/session-owned SQLite jobs and private Markdown artifacts. It does not replace web_search or web_extract.

The actual working host installation is not accessible from the Docker backend. Reference compatibility is established against Hermes commit `f0888d77bf606ea5c96738d4deecbc0503f96bb1`, not inferred for an unknown production version. Installed SDK commit is `e34b5082d6c16283358d8a1e3cbd7fa61c35fc0d` (0.16.1), external to managed Hermes Python. Research was exercised with Python 3.13.16 on Linux.

Original ZIP 0.2.0 is preserved byte-identically:
`7a9799812366fb478f5d0b197e028ace06d7d12c2623e4f3c37bc2e616f88e27`.
`docs/regression-baseline.json` compares ordinary provider/worker/auth/store and worker requirements with the DR-01 pre-implementation source inventory: unchanged. Some child-Python-environment fixes already existed before DR-01 and differ from the older ZIP; do not interpret the unchanged-source claim as universal byte parity with that archive.

## Implemented behavior

- Exact native tool registration with no override. Both same-toolset and foreign-toolset name collisions refuse loading instead of replacing a tool. Definitions, availability and real native dispatcher are tested.
- start returns a job ID without waiting for research; status/result are local reads. Trusted native session_id, not model arguments, defines ownership together with active HERMES_HOME. Foreign and unknown IDs return the same refusal.
- Stable request_id reconciles the same attempt without replay, including terminal failures. Changed input under the same key refuses. One active local job per profile; status uses snapshot comparison and never releases a live/ambiguous PID merely due wall-clock expiry.
- A supervisor claims once, launches one SDK child, enforces its timeout, kills and waits for that child on timeout. Cleanup-thread capacity is reserved before detached launch, so thread exhaustion is a correlated no-start failure. No automatic retry or remote-cancellation/refund promise.
- Pinned SDK real Perplexity and slotted Conversation are used. A temporary class-level download hook inside the isolated worker proves separate full-report retrieval and is restored on all paths. Intro-only remains incomplete. Clarifications return to the user without automatic continuation.
- CDN downloads use a separate unauthenticated session, HTTPS CloudFront .md allowlist, no redirects, bounded streaming, UTF-8/nonblank checks. Source fields are allowlisted; signed service links and URL credentials are omitted.
- Private descriptor-pinned storage, cross-process flock, SQLite image serialization and atomic publication prevent SQLite's filename resolver from following a swapped database path. Metadata capped at 64 MiB; report capped at 5 MiB. Preview is at most 4000 characters with explicit truncation and a full private .md path.
- Host process does not import the SDK; queries use child stdin, not argv. Child environments are allowlisted; SDK shared/env credential fallback is not used. Ordinary search/auth implementations and SDK runtime lock are not rewritten by this change.

## Observed tests and what they prove

The source tree contains tests for actual SQLite/files/permissions, owner checks, keyed reuse/conflict, symlink/DB-target race, stale status versus claim, clock jumps, actual detached process paths, real SDK-child timeout kill/reap, malformed output, non-BMP input at the public limit, reaper startup failure, and real pinned SDK object compatibility.

An actual loader/model-tools/native-dispatch pipeline test starts a detached supervisor, substitutes ONLY a synthetic SDK-output program for the remote job, atomically saves a long fixture report, verifies preview versus full file, rejects a foreign session and proves keyed start did not launch twice. Captured local processes are waited for and temporary profiles/executables are cleaned up. The synthetic executable uses the standalone test venv filesystem rather than noexec /tmp.

The real-SDK regression keeps Perplexity/Conversation/config/model/SSE processing real while substituting HTTP and CDN session boundaries with named fixtures; it now covers the slotted-class hook installation that the original permissive fixture missed. Normal CLI auth/search regressions remain in the suite.

Focused research suite after all first-review corrections and capability checks: **58 passed**. Full-suite results, raw stdout, exact command arrays, exit statuses, timestamps and source hashes are authoritative in `docs/verification.json`. This prose does not override a failed or stale verification record.

Initial full verification exposed test-harness issues (outer timeout shorter than two nested CLI suites, and a synthetic executable relocated onto noexec /tmp). The bounded verification budgets and executable fixture location were corrected; no product guard or failing assertion was removed.

## Independent review

First independent read-only reviewer returned **no_ship** with two P1 and three P2 findings. Each was reproduced as a failing regression and corrected separately. `docs/REVIEW.md` records findings, changes and local checks; `docs/review-target-v2.json` fingerprints the corrected target. The latest independent follow-up verdict belongs in REVIEW.md and is separate from test or packaging success. A review does not validate live service behavior or the operational host.

## Reproduction and exact artifact acceptance

In the standalone project test environment with the pinned reference on PYTHONPATH:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/workspace/develop/hermes-agent-reference \
  .venv/bin/python scripts/verify.py
.venv/bin/python scripts/build_release.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/workspace/develop/hermes-agent-reference \
  .venv/bin/python scripts/portable_check.py \
  --archive dist/hermes-perplexity-pro-0.3.0.zip --report dist/verification-final.json
.venv/bin/python scripts/attest_release.py
```

`verify.py` gives child commands an empty disposable HOME/HERMES_HOME, runs the entire suite including an unpacked-suite regression, real Plugin Doctor, compatibility/help checks, dependency consistency and AST parsing. Source and evidence hashes are recorded. The expected Doctor registration is now **one tool (deep_research)**, not the baseline's zero tools.

`portable_check.py` checks exact archive bytes outside the source directory; installs the fixed SDK into a fresh disposable external runtime; runs Doctor, native enable with exact profile readback, CLI help/missing-session auth checks, actual search/research native dispatch with no session, and the complete suite. Its raw records and archive SHA-256 are kept outside the archive in `dist/verification-final.json`. A missing-session auth refusal is expected evidence of isolation, not service success.

`attest_release.py` checks every ZIP member against source, verifies the embedded source hashes, and emits MANIFEST.sha256 and SHA256SUMS only after exact-archive checks agree. Release traversal excludes diagnostic trees, extra-deps, actual reports, credentials, venvs/caches and reference checkouts. Worker/test locks are included; test-only requests does not enter the SDK runtime lock.

## Explicit unverified and excluded work

- **No live login, real online session probe, live web search or live Deep Research.** No true report, entitlement, quota or anti-bot compatibility is asserted. Network SDK responses, credentials and reports in acceptance are synthetic.
- No production install/enable, working config/env/approvals change, gateway restart, separate bot/profile, permanent service or publication/PR/CI. Only disposable profiles are activated for tests.
- No automatic completion notification, durable restart guarantee or cancel API. A new Hermes session does not acquire old-session job access. A reused/live PID may keep the execution slot busy until the OS owner investigates; it is never killed or replayed automatically.
- Linux and SQLite serialization support required for research. File ownership/private directories protect against other users and path mistakes, not arbitrary malicious code already running as the same OS account.
- Report text and clarification questions are untrusted source content, not commands to execute. Full output-quality parity with a real Perplexity research report remains unassessed until a separately authorized live comparison.
