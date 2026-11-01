# Security and required capabilities

## What the install scan means

CAUTION is a request to review real capabilities, not proof that a vulnerability
was found and not a safety certificate. This package intentionally keeps its
worker launch and file-access code readable. No scanner suppression, encoded
commands, policy disablement or removed permission guard is used.

The runtime uses subprocess.run and subprocess.Popen to launch fixed Python
worker paths in a separate, profile-owned SDK environment. Queries travel through
stdin, not shell commands. The worker is trusted local code, not an OS sandbox;
authorizing installation grants it the user's filesystem/network authority.

The runtime checks Linux, descriptor-relative filesystem APIs, safe open flags
and file locking directly. No process-filesystem mount is required. File storage
keeps O_NOFOLLOW, owner/private-mode checks, bounded locks and atomic persistence.
Unavailable required primitives fail closed before creating storage. The redundant
mount-presence gate was removed, not encoded or hidden from the scanner.

The SDK dependency lock is supplied for a separate runtime. Installation fetches
Python/Git dependencies. The SDK is pinned, but its upstream code and dependency
supply chain remain part of the trust boundary. An unofficial web-session API can
change independently of this release.

## Data and network boundaries

Only the selected profile session store is used; credentials are not bundled in
Git. Login is terminal-only and explicit. Reports, queries and profile metadata
may contain sensitive information; do not publish auth/results directories.
The report downloader is separately bounded and does not send session auth to
the report CDN. Reports and source material are untrusted data, never commands.

No automatic retry after ambiguous execution; no remote refund/cancellation
promise. Process timeout cleanup does not establish gateway-restart durability.
File protections do not defend against arbitrary code already running as the
same OS account. Live account/service correctness is outside offline tests.

## Distribution boundary

The plugin branch is a generated runtime-only tree. main holds tests, diagnostics,
source documentation and the generator. The native installer should scan this
runtime tree, not the full development checkout. Check SHA256SUMS against package
files and pin an exact commit when reproducibility is required. Scanner findings
on required capabilities stay visible and require a deliberate trust decision.
