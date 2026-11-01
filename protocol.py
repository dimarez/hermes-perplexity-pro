"""Shared, static error vocabulary. Never render upstream exception text."""
ERRORS = {
    'input': 'Expected a non-empty query and an integer limit from 1 to 100.',
    'auth': 'No usable profile Perplexity session. Run hermes perplexity-pro login in a local terminal with the same HERMES_HOME/profile; for a named profile use hermes -p NAME perplexity-pro login.',
    'forbidden': 'Perplexity refused access (403): expired session or network/account policy.',
    'quota': 'Perplexity quota or rate limit reached. No fallback was attempted.',
    'timeout': 'Perplexity request timed out. No retry or fallback was attempted.',
    'dependency': 'Prepare HERMES_HOME/plugin-runtimes/perplexity-pro with the pinned perplexity-web-mcp-cli dependency; do not modify the Hermes Python environment.',
    'provider': 'Perplexity request failed. No retry or fallback was attempted.',
    'runtime': 'The isolated Perplexity worker could not run successfully.',
    'protocol': 'The isolated Perplexity worker returned an invalid response.',
}


def failure(code: str) -> dict:
    code = code if code in ERRORS else 'protocol'
    return {'success': False, 'error': f'perplexity-pro/{code}: {ERRORS[code]}'}


def valid_input(query, limit) -> bool:
    return isinstance(query, str) and bool(query.strip()) and type(limit) is int and 1 <= limit <= 100
