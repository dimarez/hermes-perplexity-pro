"""Synthetic session + network-boundary fixtures, never live research."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_provider import PLUGIN, load_provider
from test_session import session_module


def worker_module():
    path = PLUGIN / 'research_worker.py'
    assert path.is_file(), 'research SDK worker is not implemented'
    load_provider()
    spec = importlib.util.spec_from_file_location('perplexity_pro_tests.research_worker', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def profile(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    session_module().SessionStore(tmp_path).save('FIXTURE_RESEARCH_TOKEN')
    return tmp_path


def test_deep_model_and_verified_full_download_not_intro(monkeypatch, profile):
    m = worker_module()
    from perplexity_web_mcp import core
    from perplexity_web_mcp.models import Models
    calls = []
    conversation = SimpleNamespace(_backend_uuid='fixture-thread',
        _http=SimpleNamespace(get=lambda endpoint: SimpleNamespace(json=lambda: {
            'entries': [{'text': '{"download_info": [{"url":"https://fixture.cloudfront.net/report.md?Signature=FIXTURE"}]}'}]})),
        search_results=[SimpleNamespace(title='Source', url='https://example.org/')])
    def ask(query):
        calls.append(query)
        core.Conversation._fetch_research_report(conversation)
    conversation.ask = ask
    class Client:
        def __init__(self, token, config):
            assert token == 'FIXTURE_RESEARCH_TOKEN'
            assert config.timeout == 900 and config.max_retries == 0
            assert config.rotate_fingerprint is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def create_conversation(self, config):
            assert config.model is Models.DEEP_RESEARCH
            return conversation
    class Session:
        def __init__(self, **kwargs):
            assert 'cookies' not in kwargs and 'headers' not in kwargs
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, **kwargs):
            assert kwargs['allow_redirects'] is False
            assert kwargs['stream'] is True
            return SimpleNamespace(status_code=200, iter_content=lambda **kw: iter([b'# FULL FIXTURE REPORT']), close=lambda: None)
    monkeypatch.setattr(core, 'Perplexity', Client)
    monkeypatch.setattr(core, 'Session', Session)
    result = m.execute({'query': 'offline topic', 'timeout_seconds': 900})
    assert result == {'status': 'completed', 'full_report': True, 'report': '# FULL FIXTURE REPORT',
                      'sources': [{'title': 'Source', 'url': 'https://example.org/'}]}
    assert calls == ['offline topic']


def test_missing_profile_never_uses_ambient_credentials(monkeypatch, profile):
    m = worker_module()
    session_module().SessionStore(profile).logout()
    monkeypatch.setenv('PERPLEXITY_SESSION_TOKEN', 'FOREIGN_SECRET')
    from perplexity_web_mcp import core, token_store
    def forbidden(*args, **kwargs):
        raise AssertionError('must not load shared session or create HTTP client')
    monkeypatch.setattr(core, 'Perplexity', forbidden)
    monkeypatch.setattr(token_store, 'load_token', forbidden)
    assert m.execute({'query': 'offline', 'timeout_seconds': 900}) == {'status': 'failed', 'code': 'auth'}


@pytest.mark.parametrize('kind,expected', [('questions', 'needs_clarification'), ('quota', 'quota'),
                                         ('auth', 'forbidden'), ('timeout', 'timeout'), ('wrapped', 'timeout'), ('other', 'provider')])
def test_errors_and_clarifications_are_one_attempt_and_sanitized(monkeypatch, profile, kind, expected):
    m = worker_module()
    from perplexity_web_mcp import core, exceptions
    from curl_cffi.requests.exceptions import Timeout
    wrapped = exceptions.PerplexityError('SECRET_PAYLOAD')
    wrapped.__cause__ = Timeout('SECRET_TRANSPORT')
    errors = {'questions': exceptions.ResearchClarifyingQuestionsError(['Which scope?']),
              'quota': exceptions.RateLimitError('SECRET_PAYLOAD'),
              'auth': exceptions.AuthenticationError('SECRET_PAYLOAD'),
              'timeout': TimeoutError('SECRET_PAYLOAD'), 'wrapped': wrapped,
              'other': ValueError('SECRET_PAYLOAD')}
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise errors[kind]
    monkeypatch.setattr(core, 'Perplexity', fail)
    result = m.execute({'query': 'offline', 'timeout_seconds': 900})
    assert len(calls) == 1 and 'SECRET' not in str(result)
    if kind == 'questions':
        assert result == {'status': expected, 'questions': ['Which scope?']}
    else:
        assert result == {'status': 'failed', 'code': expected}


@pytest.mark.parametrize('url', ['http://fixture.cloudfront.net/report.md', 'https://127.0.0.1/report.md',
    'https://fixture.cloudfront.net.evil.org/report.md', 'https://user:SECRET@fixture.cloudfront.net/report.md',
    'https://fixture.cloudfront.net:8443/report.md', 'https://example.org/report.md',
    'https://fixture.cloudfront.net/report.html'])
def test_report_download_refuses_unsafe_origins_before_connect(url):
    m = worker_module()
    from perplexity_web_mcp import core
    conversation = SimpleNamespace(_backend_uuid='fixture', _http=SimpleNamespace(get=lambda endpoint:
        SimpleNamespace(json=lambda: {'download_info': [{'url': url}]})))
    with pytest.raises(m.JobError, match='incomplete'):
        m.fetch_full_report(conversation, core)


def test_intro_only_never_becomes_completed(monkeypatch, profile):
    m = worker_module()
    from perplexity_web_mcp import core
    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def create_conversation(self, config):
            return SimpleNamespace(ask=lambda query: None, answer='A long intro is not a full report', search_results=[])
    monkeypatch.setattr(core, 'Perplexity', Client)
    assert m.execute({'query': 'offline', 'timeout_seconds': 900}) == {'status': 'failed', 'code': 'incomplete'}


@pytest.mark.parametrize('status,chunks', [(302, [b'fixture']), (500, [b'fixture']), (200, [b'']), (200, [b'x' * 17])])
def test_bad_or_oversized_download_is_explicit_failure(monkeypatch, status, chunks):
    m = worker_module()
    from perplexity_web_mcp import core
    monkeypatch.setattr(m, 'MAX_REPORT_BYTES', 16)
    conversation = SimpleNamespace(_backend_uuid='fixture', _http=SimpleNamespace(get=lambda endpoint:
        SimpleNamespace(json=lambda: {'download_info': [{'url': 'https://fixture.cloudfront.net/report.md'}]})))
    closed = []
    class Session:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=status, iter_content=lambda **kw: iter(chunks), close=lambda: closed.append(True))
    monkeypatch.setattr(core, 'Session', Session)
    with pytest.raises(m.JobError, match='incomplete'):
        m.fetch_full_report(conversation, core)
    assert closed == [True]


@pytest.mark.parametrize('has_download', [True, False])
def test_real_slotted_sdk_conversation_reaches_ask_and_restores_hook(monkeypatch, profile, has_download):
    import json
    m = worker_module()
    from perplexity_web_mcp import core
    from perplexity_web_mcp.models import Models
    original_hook = core.Conversation._fetch_research_report
    calls = []
    class HTTP:
        def __init__(self, token, **kwargs):
            assert token == 'FIXTURE_RESEARCH_TOKEN'
            assert kwargs['timeout'] == 900 and kwargs['max_retries'] == 0
        def init_search(self, query):
            calls.append(('init', query))
        def stream_ask(self, payload):
            calls.append(('ask', payload))
            assert payload['params']['model_preference'] == Models.DEEP_RESEARCH.identifier
            yield 'data: ' + json.dumps({'backend_uuid': 'fixture', 'final': True, 'text': json.dumps({
                'answer': 'INTRO ONLY', 'web_results': [{'name': 'Source', 'url': 'https://example.org/'}]})})
        def get(self, endpoint):
            payload = {'download_info': [{'url': 'https://fixture.cloudfront.net/report.md'}]} if has_download else {}
            return SimpleNamespace(json=lambda: payload)
        def close(self):
            calls.append(('closed',))
    class Session:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=200, iter_content=lambda **kw: iter([b'# REAL SDK FIXTURE REPORT']), close=lambda: None)
    monkeypatch.setattr(core, 'HTTPClient', HTTP)
    monkeypatch.setattr(core, 'configure_logging', lambda **kw: None)
    monkeypatch.setattr(core, 'Session', Session)
    result = m.execute({'query': 'offline real class', 'timeout_seconds': 900})
    if has_download:
        assert result['status'] == 'completed', result
        assert result['report'] == '# REAL SDK FIXTURE REPORT'
        assert result['sources'] == [{'title': 'Source', 'url': 'https://example.org/'}]
    else:
        assert result == {'status': 'failed', 'code': 'incomplete'}
    assert len([call for call in calls if call[0] == 'ask']) == 1
    assert calls[-1] == ('closed',)
    assert core.Conversation._fetch_research_report is original_hook
