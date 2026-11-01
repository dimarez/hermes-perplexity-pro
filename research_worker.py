"""Single SDK attempt; verified separate report download, never intro-as-success."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

if __package__:
    from .research_jobs import JobError, MAX_REPORT_BYTES, safe_sources
    from .session import SessionStore, StoreError
    from .quiet import quiet_sdk
else:
    from research_jobs import JobError, MAX_REPORT_BYTES, safe_sources
    from session import SessionStore, StoreError
    from quiet import quiet_sdk


def valid_request(request):
    return (isinstance(request, dict) and isinstance(request.get('query'), str)
            and bool(request['query'].strip()) and len(request['query']) <= 16000
            and type(request.get('timeout_seconds')) is int and 60 <= request['timeout_seconds'] <= 1800)


def _report_url(payload):
    stack, urls, visited = [payload], [], 0
    while stack:
        visited += 1
        if visited > 10000:
            raise JobError('incomplete')
        value = stack.pop()
        if isinstance(value, dict):
            info = value.get('download_info')
            if isinstance(info, list):
                urls.extend(entry.get('url') for entry in info if isinstance(entry, dict))
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, str) and 'download_info' in value and value.lstrip()[:1] in ('{', '['):
            if len(value) > MAX_REPORT_BYTES:
                raise JobError('incomplete')
            try:
                stack.append(json.loads(value))
            except ValueError:
                raise JobError('incomplete') from None
    if not urls or not isinstance(urls[-1], str):
        raise JobError('incomplete')
    url = urls[-1]
    try:
        parsed = urlsplit(url)
        if (len(url) > 16000 or any(ord(c) <= 32 for c in url) or '\\' in url
                or parsed.scheme != 'https' or not parsed.hostname
                or not parsed.hostname.endswith('.cloudfront.net') or parsed.port not in (None, 443)
                or parsed.username or parsed.password or parsed.fragment or not parsed.path.endswith('.md')):
            raise JobError('incomplete')
    except ValueError:
        raise JobError('incomplete') from None
    return url


def fetch_full_report(conversation, core):
    if not conversation._backend_uuid:
        raise JobError('incomplete')
    endpoint = (f'{core.ENDPOINT_THREAD_DETAIL}/{conversation._backend_uuid}'
                f'?version={core.API_VERSION}&source=default&limit=100&from_first=true')
    url = _report_url(conversation._http.get(endpoint).json())
    settings = {'impersonate': 'chrome'}
    bundle = core.get_system_ca_bundle_path()
    if bundle:
        settings['verify'] = bundle
    # New unauthenticated session: no Perplexity cookies/headers on the CDN.
    with core.Session(**settings) as session:
        response = session.get(url, timeout=60, allow_redirects=False, stream=True)
        try:
            if response.status_code != 200:
                raise JobError('incomplete')
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                if not isinstance(chunk, bytes):
                    raise JobError('incomplete')
                size += len(chunk)
                if size > MAX_REPORT_BYTES:
                    raise JobError('incomplete')
                chunks.append(chunk)
        finally:
            response.close()
    try:
        report = b''.join(chunks).decode('utf-8')
    except UnicodeError:
        raise JobError('incomplete') from None
    if not report.strip():
        raise JobError('incomplete')
    return report


def _execute(request):
    if not valid_request(request):
        raise JobError('protocol')
    home = os.environ.get('HERMES_HOME', '')
    if not home or not Path(home).is_absolute():
        raise JobError('auth')
    try:
        token = SessionStore(Path(home)).read()
    except StoreError:
        raise JobError('auth') from None
    if not token:
        raise JobError('auth')
    from perplexity_web_mcp import core
    from perplexity_web_mcp.config import ClientConfig, ConversationConfig
    from perplexity_web_mcp.enums import CitationMode, LogLevel, SearchFocus
    from perplexity_web_mcp.models import Models
    verified = {}
    with core.Perplexity(token, config=ClientConfig(
            timeout=request['timeout_seconds'], max_retries=0, requests_per_second=0,
            rotate_fingerprint=False, logging_level=LogLevel.DISABLED)) as client:
        conversation = client.create_conversation(ConversationConfig(
            model=Models.DEEP_RESEARCH, citation_mode=CitationMode.DEFAULT,
            search_focus=SearchFocus.WEB, source_focus=['web'], save_to_library=False))
        # A real SDK Conversation is slotted: patch the class method for the
        # duration of this one isolated SDK operation, never assign an instance method.
        # The original method is restored even on timeout/clarification/error.
        from unittest.mock import patch
        def fetch(active_conversation):
            verified['report'] = fetch_full_report(active_conversation, core)
            return verified['report']
        with patch.object(core.Conversation, '_fetch_research_report', fetch):
            conversation.ask(request['query'])
        if 'report' not in verified:
            raise JobError('incomplete')
        sources = safe_sources([{'title': source.title or '', 'url': source.url}
                                for source in (conversation.search_results or [])[:200]])
        return {'status': 'completed', 'full_report': True, 'report': verified['report'], 'sources': sources}


def execute(request):
    try:
        return _execute(request)
    except JobError as exc:
        return {'status': 'failed', 'code': str(exc)}
    except ImportError:
        return {'status': 'failed', 'code': 'dependency'}
    except Exception as exc:
        # Only structured types/status and bounded cause chains cross the boundary.
        try:
            from perplexity_web_mcp.exceptions import ResearchClarifyingQuestionsError
            from curl_cffi.requests.exceptions import Timeout
        except ImportError:
            return {'status': 'failed', 'code': 'dependency'}
        if isinstance(exc, ResearchClarifyingQuestionsError):
            questions = exc.questions
            if (isinstance(questions, list) and 1 <= len(questions) <= 20
                    and all(isinstance(q, str) and q.strip() and len(q) <= 2000 for q in questions)):
                return {'status': 'needs_clarification', 'questions': questions}
            return {'status': 'failed', 'code': 'protocol'}
        seen = set()
        current = exc
        for _ in range(8):
            if current is None or id(current) in seen:
                break
            seen.add(id(current))
            status = getattr(current, 'status_code', None)
            if status in (401, 403, 429):
                return {'status': 'failed', 'code': {401: 'auth', 403: 'forbidden', 429: 'quota'}[status]}
            if isinstance(current, (TimeoutError, Timeout)):
                return {'status': 'failed', 'code': 'timeout'}
            current = current.__cause__
        return {'status': 'failed', 'code': 'provider'}


def main():
    with quiet_sdk():
        try:
            raw = sys.stdin.read(100001)
            result = execute(json.loads(raw)) if len(raw) <= 100000 else {'status': 'failed', 'code': 'protocol'}
        except (ValueError, UnicodeError):
            result = {'status': 'failed', 'code': 'protocol'}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
