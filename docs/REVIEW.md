# Async research review record

## Round 1 — independent review, 2026-11-01

Native reviewer batch `deleg_8896d4aa`, model gpt-6.1-sol, read-only, baseline ZIP SHA-256 `7a9799812366fb478f5d0b197e028ace06d7d12c2623e4f3c37bc2e616f88e27`. Initial verdict: **no_ship / high confidence**. This is not a release approval.

Findings reproduced by the parent and corrected one at a time:

1. **P1 SDK slots:** the actual SDK Conversation rejects assignment to an instance method. New test uses real Perplexity/Conversation with only HTTP/session/logging boundaries substituted; observed RED: 2 failed. The download hook is now temporarily replaced on the SDK class only inside the dedicated one-attempt child, and restored on both success and failure. Worker suite after correction: 22 passed.
2. **P1 status/claim race:** a stale queued snapshot could overwrite a fresh running claim. New deterministic interleaving test failed (interrupted instead of running). The update now compares status, updated timestamp and PID of the inspected snapshot. Job suite after correction: 10 passed.
3. **P2 SQLite pathname race:** replacing the database after validation redirected writes outside the store. New synthetic external-database regression failed because protected bytes changed. SQLite now operates on a descriptor-read serialized image in memory under a cross-process private file lock; it never opens a filesystem DB path. Atomic publishing rechecks pinned file identity. Combined jobs/supervisor/tool/integration tests after correction: 32 passed.
4. **P2 Unicode envelope:** default JSON ASCII escaping rejected valid non-BMP queries before auth. Actual supervisor/worker test at the 16000-character public limit failed with protocol instead of auth. The supervisor now uses ensure_ascii=False; supervisor suite after correction: 5 passed.
5. **P2 cleanup reservation:** Thread.start failure after Popen escaped as RuntimeError without a job envelope. Actual-process regression reproduced it. Cleanup thread capacity is now reserved before Popen; startup failure returns a static runtime error and committed job_id with no process launched. Tool/integration tests after correction: 18 passed.

Additional conservative liveness regression: a clock jump must not free the slot of a live/ambiguous supervisor PID. Observed RED: interrupted instead of running. Status now retains the slot for a live PID rather than inferring execution ended from wall-clock age; an abandoned queued job without a PID may expire. It never kills or resubmits using an ambiguous PID.

Combined five-module research regression suite after these corrections: **57 passed**. Command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/workspace/develop/hermes-agent-reference \
  .venv/bin/python -m pytest -q tests/test_research_jobs.py tests/test_research_supervisor.py \
  tests/test_research_worker.py tests/test_research_tool.py tests/test_research_integration.py \
  -p no:cacheprovider --tb=short
```

The independent reviewer also noted pre-existing source drift from the immutable 0.2.0 archive in provider/auth child-environment sanitization. Do not describe all current bytes as identical to that old archive; compare unchanged modules against the DR-01 pre-implementation inventory instead. The archived 0.2.0 ZIP itself remains unchanged.

## Round 2

Focused independent re-review `deleg_5e22a2a2` (gpt-6.1-sol) returned **ship / high confidence**, no findings. The reviewer verified all 12 corrected-target fingerprints, reran the five research test modules (**58 passed**), and inspected/reproduced the five fixes plus changed storage/locking paths. The parent read back the same fingerprint manifest and observed no target drift; full local verification independently recorded **153 passed** with Doctor and dependency/help/AST checks exit 0.

The reviewer additionally reported disposable cross-process contention and storage failure-injection probes; those remain reviewer-reported observations, not separate parent attestations. The remaining coverage gap is crash/power loss specifically between DB replacement and directory fsync. No restart-survival guarantee is made. Live Perplexity, real auth, production host and exact final archive remain outside the review verdict; archive acceptance is recorded separately in dist/verification-final.json and the checksum attestation.
