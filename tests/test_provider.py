"""Offline contract tests: subprocess responses are fixtures, not live searches."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugin'


def load_provider():
    path = PLUGIN / 'provider.py'
    assert path.is_file(), 'perplexity-pro provider is not implemented'
    import types
    package = types.ModuleType('perplexity_pro_tests')
    package.__path__ = [str(PLUGIN)]
    sys.modules[package.__name__] = package
    spec = importlib.util.spec_from_file_location('perplexity_pro_tests.provider', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_search_contract(monkeypatch):
    module = load_provider()
    response = {'success': True, 'data': {'web': [
        {'title': 'Example fixture', 'url': 'https://example.org/',
         'description': 'Fixture snippet', 'position': 1}
    ]}}
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, json.dumps(response))

    monkeypatch.setattr(module.subprocess, 'run', run)
    provider = module.PerplexityProProvider()
    assert provider.name == 'perplexity-pro'
    assert provider.supports_search() is True
    assert provider.supports_extract() is False
    assert provider.search('public query', 5) == response
    args, kwargs = calls[0]
    assert args[0] == str(provider.worker_python())
    assert 'public query' not in args
    assert json.loads(kwargs['input']) == {'query': 'public query', 'limit': 5}
    assert kwargs['timeout'] == 90
    assert kwargs['stderr'] == subprocess.DEVNULL
    assert kwargs['env']['PWM_TRACE'] == '0'
    assert kwargs['env']['PWM_DEBUG'] == '0'
    assert kwargs['env']['PYTHONFAULTHANDLER'] == '0'


def test_provider_passes_explicit_profile_and_sanitizes_only_child_env(monkeypatch, tmp_path):
    import os
    m = load_provider()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    monkeypatch.setenv('HERMES_HOME', str(tmp_path / 'foreign-home'))
    monkeypatch.setenv('PERPLEXITY_SESSION_TOKEN', 'SECRET_FOREIGN_ENV')
    previous = os.environ.copy()
    def run(*args, **kwargs):
        assert kwargs['env']['HERMES_HOME'] == str(tmp_path)
        assert 'PERPLEXITY_SESSION_TOKEN' not in kwargs['env']
        return subprocess.CompletedProcess([], 0, '{"success":false,"error":"untrusted fixture"}')
    monkeypatch.setattr(m.subprocess, 'run', run)
    m.PerplexityProProvider().search('test')
    assert dict(os.environ) == previous


def test_parent_errors_are_sanitized(monkeypatch):
    module = load_provider()
    cases = [
        (subprocess.TimeoutExpired('SECRET', 90, output='SECRET'), 'timeout'),
        (OSError('SECRET'), 'runtime'),
        (subprocess.CompletedProcess([], 1, 'SECRET'), 'runtime'),
        (subprocess.CompletedProcess([], 0, 'SECRET'), 'protocol'),
        (subprocess.CompletedProcess([], 0, '{"success":true,"data":{}}'), 'protocol'),
        (subprocess.CompletedProcess([], 0, '{"success":false,"error":"SECRET"}'), 'protocol'),
    ]
    for outcome, code in cases:
        def run(*args, **kwargs):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        monkeypatch.setattr(module.subprocess, 'run', run)
        result = module.PerplexityProProvider().search('test')
        assert result['success'] is False
        assert code in result['error']
        assert 'SECRET' not in json.dumps(result)


def test_invalid_input_never_starts_worker(monkeypatch):
    module = load_provider()
    def unexpected(*args, **kwargs):
        raise AssertionError('invalid input reached worker')
    monkeypatch.setattr(module.subprocess, 'run', unexpected)
    for query, limit in [('', 5), ('  ', 5), (None, 5), ('x', 0), ('x', 101),
                         ('x', True), ('x', '5')]:
        assert module.PerplexityProProvider().search(query, limit)['success'] is False


def test_limit_100_is_supported(monkeypatch):
    module = load_provider()
    def run(args, **kwargs):
        assert json.loads(kwargs['input'])['limit'] == 100
        return subprocess.CompletedProcess(args, 0, '{"success":true,"data":{"web":[]}}')
    monkeypatch.setattr(module.subprocess, 'run', run)
    assert module.PerplexityProProvider().search('query', 100)['success'] is True


import pytest


@pytest.mark.parametrize('row', [None, {}, {'title': 123, 'url': 'https://example.org/', 'description': '', 'position': 1},
    {'title': 'x', 'url': 'javascript:alert(1)', 'description': '', 'position': 1},
    {'title': 'x', 'url': 'https://user:password@example.org/', 'description': '', 'position': 1},
    {'title': 'x', 'url': 'https://example.org/', 'description': '', 'position': True}])
def test_invalid_worker_rows_are_rejected(monkeypatch, row):
    m = load_provider()
    response = {'success': True, 'data': {'web': [row]}}
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess([], 0, json.dumps(response)))
    assert '/protocol:' in m.PerplexityProProvider().search('query')['error']


def test_unexpected_fields_never_cross_worker_boundary(monkeypatch):
    m = load_provider()
    row = {'title': 'x', 'url': 'https://example.org/', 'description': '', 'position': 1, 'auth': 'SECRET'}
    response = {'success': True, 'debug': 'SECRET', 'data': {'web': [row], 'raw_data': 'SECRET'}}
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess([], 0, json.dumps(response)))
    result = m.PerplexityProProvider().search('query')
    assert result['success'] is True
    assert 'SECRET' not in json.dumps(result)
