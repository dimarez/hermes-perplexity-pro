"""One query, one SDK process, fixed web-only Sonar model, no account discovery."""
from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
from urllib.parse import urlsplit
from pathlib import Path

if __package__:
    from .protocol import failure, valid_input
    from .session import SessionStore, StoreError
    from .quiet import quiet_sdk
else:
    from protocol import failure, valid_input
    from session import SessionStore, StoreError
    from quiet import quiet_sdk


def execute(request: dict) -> dict:
    try:
        return _execute(request)
    except Exception as exc:
        # Classify by structured status/type only. Never stringify remote failures.
        try:
            from curl_cffi.requests.exceptions import Timeout
        except ImportError:
            Timeout = TimeoutError
        # The SDK wraps curl failures with `raise PerplexityError(...) from error`.
        # Inspect a bounded explicit-cause chain, never remote text or traceback.
        current = exc
        seen = set()
        for _ in range(8):
            if current is None or id(current) in seen:
                break
            seen.add(id(current))
            status = getattr(current, 'status_code', None)
            if status in (401, 403, 429):
                return failure({401: 'auth', 403: 'forbidden', 429: 'quota'}[status])
            if isinstance(current, (TimeoutError, Timeout)):
                return failure('timeout')
            current = current.__cause__
        return failure('provider')


def _execute(request: dict) -> dict:
    if not isinstance(request, dict) or not valid_input(request.get('query'), request.get('limit')):
        return failure('input')
    # A missing/unsafe profile session fails before SDK import or HTTP. Never
    # call SDK load_token(): it has a shared file and ambient-env fallback.
    home = os.environ.get('HERMES_HOME', '')
    if not home or not Path(home).is_absolute():
        return failure('auth')
    try:
        token = SessionStore(Path(home)).read()
    except (StoreError, OSError, UnicodeError):
        return failure('auth')
    if not token:
        return failure('auth')
    try:
        from perplexity_web_mcp.config import ClientConfig, ConversationConfig
        from perplexity_web_mcp.core import Perplexity
        from perplexity_web_mcp.enums import CitationMode, LogLevel, SearchFocus
        from perplexity_web_mcp.models import Models
    except ImportError:
        return failure('dependency')
    with Perplexity(token, config=ClientConfig(
        timeout=60, max_retries=0, requests_per_second=0,
        rotate_fingerprint=False, logging_level=LogLevel.DISABLED,
    )) as client:
        conversation = client.create_conversation(ConversationConfig(
            model=Models.SONAR, citation_mode=CitationMode.DEFAULT,
            search_focus=SearchFocus.WEB, source_focus=['web'], save_to_library=False,
        ))
        conversation.ask(request['query'])
        rows, seen = [], set()
        for position, source in enumerate(conversation.search_results or [], 1):
            url = source.url
            if not isinstance(url, str) or url in seen:
                continue
            try:
                parsed = urlsplit(url)
                if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                    continue
            except ValueError:
                continue
            seen.add(url)
            rows.append({'title': source.title or '', 'url': url,
                         'description': source.snippet or '', 'position': position})
            if len(rows) >= request['limit']:
                break
        return {'success': True, 'data': {'web': rows}}


def main() -> None:
    # Must be set before importing the SDK; do not inherit its debug/trace switches.
    os.environ.update(PWM_TRACE='0', PWM_DEBUG='0', LOG_LEVEL='DISABLED', PYTHONFAULTHANDLER='0')
    logging.disable(logging.CRITICAL)
    try:
        request = json.loads(sys.stdin.read())
        # Protect the protocol from optional dependency banners and tracebacks.
        with quiet_sdk():
            response = execute(request)
    except Exception:
        response = failure('provider')
    print(json.dumps(response, ensure_ascii=False))


if __name__ == '__main__':
    main()
