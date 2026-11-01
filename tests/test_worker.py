"""The SDK is replaced only at its network boundary; all results are fixtures."""
import importlib.util
import pytest
from pathlib import Path
from types import SimpleNamespace

from test_provider import PLUGIN


@pytest.fixture(autouse=True)
def profile_store(monkeypatch, tmp_path):
    from test_session import session_module
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = session_module().SessionStore(tmp_path)
    store.save('FIXTURE_NOT_A_REAL_TOKEN')
    return store


def load_worker():
    path = PLUGIN / 'worker.py'
    assert path.is_file(), 'isolated SDK worker is not implemented'
    from test_provider import load_provider
    load_provider()  # Give the script a package context without importing the SDK into Hermes.
    spec = importlib.util.spec_from_file_location('perplexity_pro_tests.worker', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_preserves_sources_and_uses_fixed_safe_configuration(monkeypatch):
    m = load_worker()
    from perplexity_web_mcp import core, token_store
    conversation = SimpleNamespace(
        search_results=[
            SimpleNamespace(title='One', url='https://example.org/a', snippet='Real fixture snippet'),
            SimpleNamespace(title='duplicate', url='https://example.org/a', snippet='skip'),
            SimpleNamespace(title=None, url='https://example.org/b', snippet=None),
            SimpleNamespace(title='unsafe', url='javascript:alert(1)', snippet='skip'),
            SimpleNamespace(title='Three', url='https://example.org/c', snippet='third'),
        ]
    )
    queries, configs, closed = [], [], []
    conversation.ask = lambda query: queries.append(query)
    class Client:
        def __init__(self, token, config):
            assert token == 'FIXTURE_NOT_A_REAL_TOKEN'
            assert config.timeout == 60
            assert config.max_retries == 0
            assert config.rotate_fingerprint is False
            assert config.logging_level.value == 'DISABLED'
        def __enter__(self):
            return self
        def __exit__(self, *args):
            closed.append(True)
        def create_conversation(self, config):
            configs.append(config)
            return conversation
    monkeypatch.setattr(core, 'Perplexity', Client)
    result = m.execute({'query': 'test query', 'limit': 2})
    assert result == {'success': True, 'data': {'web': [
        {'title': 'One', 'url': 'https://example.org/a', 'description': 'Real fixture snippet', 'position': 1},
        {'title': '', 'url': 'https://example.org/b', 'description': '', 'position': 3},
    ]}}
    assert queries == ['test query']
    assert closed == [True]
    assert configs[0].model.identifier == 'experimental'
    assert configs[0].source_focus == ['web']
    assert configs[0].save_to_library is False


def test_no_session_never_constructs_http_client(monkeypatch, profile_store):
    m = load_worker()
    from perplexity_web_mcp import core
    profile_store.logout()
    def unexpected(*args, **kwargs):
        raise AssertionError('network client created without session')
    monkeypatch.setattr(core, 'Perplexity', unexpected)
    assert '/auth:' in m.execute({'query': 'test', 'limit': 5})['error']


import pytest


@pytest.mark.parametrize('kind,status,code', [
    ('auth', None, 'forbidden'), ('quota', None, 'quota'),
    ('http', 401, 'auth'), ('http', 403, 'forbidden'),
    ('http', 429, 'quota'), ('http', 500, 'provider'),
    ('timeout', None, 'timeout'), ('curl_timeout', None, 'timeout'),
    ('other', None, 'provider'),
])
def test_sdk_errors_do_not_leak_payloads(monkeypatch, kind, status, code):
    m = load_worker()
    from perplexity_web_mcp import core, exceptions, token_store
    from curl_cffi.requests.exceptions import Timeout
    error = {
        'auth': exceptions.AuthenticationError('SECRET', response_body='SECRET'),
        'quota': exceptions.RateLimitError('SECRET', response_body='SECRET'),
        'http': exceptions.HTTPError('SECRET', status_code=status, response_body='SECRET'),
        'timeout': TimeoutError('SECRET'),
        'curl_timeout': Timeout('SECRET'),
        'other': RuntimeError('SECRET'),
    }[kind]
    def broken(*args, **kwargs):
        raise error
    monkeypatch.setattr(core, 'Perplexity', broken)
    result = m.execute({'query': 'test', 'limit': 5})
    assert result['success'] is False
    assert f'/{code}:' in result['error']
    assert 'SECRET' not in str(result)


def test_worker_never_uses_shared_sdk_token_loader(monkeypatch, tmp_path, profile_store):
    profile_store.logout()
    m = load_worker()
    from perplexity_web_mcp import token_store, core
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('PERPLEXITY_SESSION_TOKEN', 'SECRET_FOREIGN_ENV')
    calls = []
    def shared():
        calls.append('shared-token-loader')
        return 'SECRET_SHARED_SESSION'
    def network(*args, **kwargs):
        raise AssertionError('must not create network client without profile session')
    monkeypatch.setattr(token_store, 'load_token', shared)
    monkeypatch.setattr(core, 'Perplexity', network)
    response = m.execute({'query': 'profile missing fixture', 'limit': 5})
    assert '/auth:' in response['error']
    assert 'hermes perplexity-pro login' in response['error']
    assert calls == []


def test_worker_bad_input_is_rejected():
    m = load_worker()
    for request in [None, [], {}, {'query': 'x', 'limit': True}]:
        assert '/input:' in m.execute(request)['error']


def test_real_sdk_wrapped_http_timeout(monkeypatch):
    """Exercise the real client/wrapping path, not just a constructor exception."""
    m = load_worker()
    from perplexity_web_mcp import http, token_store
    from curl_cffi.requests.exceptions import Timeout
    calls = []
    class Session:
        def get(self, *args, **kwargs):
            calls.append('get')
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None)
        def post(self, *args, **kwargs):
            calls.append('post')
            raise Timeout('SECRET_FIXTURE')
        def close(self):
            calls.append('close')
    monkeypatch.setattr(http.HTTPClient, '_create_session', lambda *a: Session())
    result = m.execute({'query': 'offline wrapped timeout fixture', 'limit': 5})
    assert '/timeout:' in result['error']
    assert 'SECRET' not in str(result)
    assert calls == ['get', 'post', 'close']
