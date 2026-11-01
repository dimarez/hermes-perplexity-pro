# 0.3.1 packaging acceptance

Claim: ordinary `hermes plugins install dimarez/hermes-perplexity-pro` selects a
minimal native tree instead of the development repository. main remains the
source branch; the generated plugin branch becomes GitHub's default branch.

Requirements:
- Root manifest 0.3.1; complete unchanged runtime Python files and SDK lock.
- Explicit allowlist export: no tests, scripts, diagnostic trees, credentials,
  environments or private reports. License, SDK lock, readable README/security
  notes and deterministic SHA256SUMS accompany the runtime.
- No removed guards, obfuscation, scanner suppressions or global policy changes.
  Required capability warnings remain CAUTION and require deliberate consent.
- Builder regression tests cover completeness, byte identity, checksums,
  refusing overwrite/symlink input and excluding unexpected files.
- Full existing search/auth/research regressions still pass. Verify actual
  Doctor and native Git install in a disposable profile. User consent to accept
  CAUTION is separate and scoped; do not silently reuse an old exact-commit grant.
- Review diff from 0e02bf6deb11bcc0999e10b23a3cfbc8b0f6c9c1 before publication.
  Confirm source and package remote SHAs, complete trees and default branch.

Publication: construct package Git tree from generated files with a separate
index, parent it to the source commit, push main and plugin without force, then
read back exact remote refs before changing the default branch. Tag v0.3.1 on
the package commit so users can inspect the exact install tree. No working-profile
activation, login, live Perplexity requests or gateway restart belongs to this fix.

Review focus: installer root layout; default-branch/subdirectory compatibility;
source/runtime byte parity; exclusion of local data; truthful CAUTION handling.
The independent judge is tests + actual native installer/scanner + read-only
reviewer; GitHub API/Git reads prove publication, not comments or plans.
