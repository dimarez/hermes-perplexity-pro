# Scope / acceptance 0.2.0 (historical baseline)

For the 0.3.0 async research extension, use `ASYNC_RESEARCH.md`, `REVIEW.md`,
current `EVIDENCE.md` and the exact final archive verification. The table below
records the earlier auth/search baseline, not new research acceptance.

Task t_ea31e28c extends released t_34e7552c, not a backend rewrite. Single product
writer; read-only helper review only. Local-only; working Hermes/profiles/config,
real sessions/2FA, gateway, PR/publication are out of scope and unchanged.

| Requirement | Implementation | Evidence |
|---|---|---|
| Native local login/status/logout | Supported register_cli_command hook, terminal-only `hermes [-p PROFILE] perplexity-pro` | Real reference CLI in test_auth_cli, portable_check; official excerpts auth-environment.json |
| Reuse existing SDK auth protocol | Direct six auth helpers; no copied endpoints/OAuth, no unsafe SDK CLI invocation | test_auth uses real SDK helpers with fake network session only |
| Hidden email/OTP/TOTP, cancel and fatal 404 | getpass with echo-fallback refusal, Ctrl-C/EOF, one attempt only | test_auth cancel stages, GetPassWarning and fatal TOTP404 fixtures |
| No token/PII/raw-error output | Fixed enums/messages, SDK fd and Python stream suppression | test_auth noisy network + probe, test_auth_cli child failures, existing provider tests |
| Per-profile session | Explicit HERMES_HOME/plugin-auth/perplexity-pro/token, private directory descriptors, atomic replacement | test_session, actual -p default/research test with sticky profile |
| No shared fallback/migration | SDK load_token unused; constructor receives explicit profile token; foreign env removed only in children | worker no-fallback fixture, native CLI synthetic shared file unchanged, env preservation tests |
| Honest status | Local presence explicitly unchecked; explicit SDK online probe distinguishes accepted/rejected/unreachable | Real SDK probe with network fixtures; actual no-session CLI online check makes no network request |
| Scoped logout | Local unlink only, no server revoke, no symlink/hardlink following | Two profile and symlink tests, logout without runtime, shared synthetic file unchanged |
| Clear search auth error, no interactive login | Fixed login command and same-profile guidance; worker fails before SDK/HTTP if no safe profile session | test_worker, provider/env tests, native dispatcher missing-session path |
| Preserve original search backend | Same model/config, source semantics, sanitization, extract unaffected, no new fallback | Original provider/worker/loader/dispatcher regressions retained |
| Safe commit/error semantics | Ancestor directories fsynced before token commit, including retries; post-commit directory fsync failure distinguished as changed-unconfirmed; cancel/timeout not promised rollback | Store fsync order/failure/retry and login post-commit regressions; read-only review finding fixed |
| Terminal after cancellation/timeout | Parent snapshots and restores getpass TTY even after SIGKILL; pending input discarded | Six real synthetic PTY subprocess tests: timeout/interrupt/exit, controlling TTY/fallback; no SDK/auth/network |
| Installation/update/rollback | Main/default explicit; named/custom homes; code backups outside discovery; auth outside code/runtime | README; code replacement/rollback test preserving synthetic profile session |
| Portable exact release | Deterministic allowlisted 0.2.0 ZIP, fresh SDK sidecar, real doctor/enable/help/native dispatcher, full suite outside source | dist/verification-final.json + MANIFEST.sha256 + SHA256SUMS |

## Boundaries

- Real login, real online session validity, live search, Pro entitlement: NOT RUN.
  HTTP/email/TOTP/probe responses in tests are named fixtures, not live evidence.
- Reference Hermes f0888d77bf606ea5c96738d4deecbc0503f96bb1 and SDK
  e34b5082d6c16283358d8a1e3cbd7fa61c35fc0d unchanged; worker locks unchanged.
- POSIX/Linux credential store. Windows unsupported by 0.2.0. Explicit home and
  OS-owned ancestors trusted; symlink home/store refused; no transaction lock
  between simultaneous operator login/logout commands in one profile.
- SDK subprocess is isolation from host logging/env side effects, not an OS sandbox.
- Host core keyless rescue is distinct from adapter fallback and is not silently disabled.
- Working host loader/transport not available from Docker. Compatibility and installation
  commands for it are operator instructions, not an execution claim.
