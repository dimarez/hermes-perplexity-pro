# 0.3.2 acceptance and review scope

Base source: a799619312533aa7de3f90ae84a26801791b5b96 (0.3.1).
The user explicitly requested this patch version and authorization UX changes.
No working-profile installation, real credentials or live authentication is part
of the executor's scope.

## Requirements

1. Storage and native research availability must not depend on a process-filesystem
mount. Reproduce the prior refusal with Path.is_dir reporting that mount absent,
then prove the complete local storage lifecycle and native check_fn work without
probing it. Replace the obsolete mount check with actual Linux, descriptor-API,
safe-open-flag and locking capability checks. Missing capabilities/unsupported OS
must refuse before creating storage. Preserve symlink/hardlink/owner/mode checks,
locks, DB identity validation, atomic persistence and SQLite capability refusal.
2. Email input is visible in the user's local TTY. OTP/TOTP remain hidden by
secure default; explicit login --show-codes opts into TTY echo for temporary codes.
They remain sensitive until expiry and terminal recording can capture them.
No credential values go into argv, CLI captured stdout/stderr, SDK logs or chat.
Non-TTY login still refuses before network. Keep cancellation, previous-session
preservation, getpass-fallback refusal and terminal restoration behavior.
3. Online status explicitly labels authorization accepted/rejected/unknown, while
preserving machine state prefixes and exit codes. Local presence is not a service
validation. Do not claim Pro, quota or full-service success. The SDK probe itself
is not changed; the observed old valid output was a positive result, not evidence
of a broken protocol.
4. Minimal package manifest/README are 0.3.2. Keep allowlisted runtime packaging,
security notes and checksums; no scanner suppression, encoded paths or global
policy changes. Measure current package findings with the same pinned scanner.
5. Full search/auth/research regressions, real PTY echo isolation, native CLI flag
forwarding and immutable package installation are separate checks. Remote/source
publication requires matching exact trees and tags, not just successful push.

## Publication and limits

main remains development; plugin remains the default minimal native tree. The
next package commit must descend from the previous package commit AND record the
new source parent, allowing a normal fast-forward push without rewriting history.
Tag v0.3.2 on the package commit. Read back both refs, complete trees, default HEAD
and release after publishing. A new package's CAUTION acceptance still requires
its own scoped consent for a disposable profile, not a reused old commit grant.
No real login, live research or gateway restart. Any leftover capability warnings
remain visible and are not a security certificate.

Review focus: storage guard equivalence; terminal-only visible input under parent
stdout capture; OTP secure-default and explicit opt-in; truthful status semantics;
package/source identity and non-force branch ancestry.
