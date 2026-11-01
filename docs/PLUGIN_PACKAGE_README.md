# hermes-perplexity-pro 0.3.2 — install package

This branch contains only the native Hermes plugin, its fixed external SDK
requirements, license, checksums and security notes. Development sources and
tests are on the **main** branch of this same repository. This branch is generated
by main/scripts/build_install_tree.py; do not edit the two copies independently.

## Install into an explicitly selected existing profile

```bash
hermes -p default plugins install dimarez/hermes-perplexity-pro --no-enable
```

Use your target profile instead of default where appropriate. The installed name
is **web-perplexity-pro**. Do not install a second copy alongside a previous
manual web/perplexity-pro installation; preserve its profile auth/results and
plan the code transition first.

**CAUTION is expected.** This plugin needs local subprocesses and Linux descriptor
checks. Read SECURITY.md and the source before deciding to trust it. If Hermes
refuses, stop. Only after your explicit review may you repeat installation with
`--force` for that specific revision; this confirms trust and is not a fix for a
vulnerability. Never turn off scanning globally. `--ref` accepts an exact
40-character commit SHA, not a version label. Nothing logs in automatically.

## Separate SDK runtime

For the standard default profile only, after the code download succeeded:

```bash
set -e
PROFILE_HOME="$HOME/.hermes"
PLUGIN="$PROFILE_HOME/plugins/web-perplexity-pro"
RUNTIME="$PROFILE_HOME/plugin-runtimes/perplexity-pro"
test -f "$PLUGIN/plugin.yaml"
test ! -e "$RUNTIME" && test ! -L "$RUNTIME"
mkdir -p "$PROFILE_HOME/plugin-runtimes"
uv venv --python 3.13 "$RUNTIME"
uv pip install --python "$RUNTIME/bin/python" -r "$PLUGIN/requirements-worker.lock.txt"
uv pip check --python "$RUNTIME/bin/python"
hermes -p default plugins doctor "$PLUGIN" --ci
hermes -p default plugins enable web-perplexity-pro
hermes -p default perplexity-pro --help
```

For another existing profile or custom home, use that same explicit profile/home
throughout. If a runtime already exists, inspect/update it rather than deleting
it. Do not install SDK requirements into Hermes' managed Python environment.

Choose search_backend=perplexity-pro intentionally after saving the old setting.
Enable toolset **perplexity-pro-research** in the desired tools selection.
Login is performed only by the user in a local interactive terminal:
`hermes -p default perplexity-pro login`. Email input is visible. OTP/TOTP stay
hidden by default; `login --show-codes` explicitly enables terminal-only echo.
Temporary codes are sensitive until expiry and can be captured by terminal/screen
recording. No values are added to argv, SDK logs or command-result stdout.
Never send tokens or OTP through chat. The online status now explicitly says
whether authorization was accepted, rejected or could not be checked; local-only
status does not pretend to validate the service session.

The new tool is **deep_research**, with start/status/result. It does not replace
web_search/web_extract. No automatic completion notifications, automatic retries,
remote cancellation, or restart-survival guarantee. SDK requests and reports are
untrusted content; private profile results must not be published.

Offline tests and installation checks do not establish real Perplexity account,
quota, anti-bot compatibility or report quality. Live service acceptance and
working-profile activation require separate authorization.
