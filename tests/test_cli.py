"""Compatibility CLI uses real Hermes imports; live dispatch is explicitly mocked."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import json

from test_provider import ROOT


def module():
    spec = importlib.util.spec_from_file_location('compatibility_check', ROOT / 'scripts/check_compatibility.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert hasattr(m, 'check'), 'compatibility and routing checker is not implemented'
    return m


def test_compatibility_without_network_or_discovery(monkeypatch):
    from hermes_cli import plugins, config
    def unexpected(*args, **kw):
        raise AssertionError('default check must not load config, discover plugins or search')
    monkeypatch.setattr(plugins, 'discover_plugins', unexpected)
    monkeypatch.setattr(config, 'load_config_readonly', unexpected)
    code, result = module().check()
    assert code == 0
    assert result['status'] == 'provider_api_available'
    assert result['live_queries_sent'] == 0


def test_live_requires_exact_route_before_dispatch(monkeypatch):
    from hermes_cli import plugins
    from agent import web_search_registry
    monkeypatch.setattr(plugins, 'discover_plugins', lambda: None)
    monkeypatch.setattr(web_search_registry, 'get_active_search_provider', lambda: None)
    code, result = module().check(live=True)
    assert code == 1 and result['status'] == 'wrong_route'


def test_live_requires_runtime_and_disabled_rescue(monkeypatch):
    from hermes_cli import plugins, config
    from agent import web_search_registry
    from tools import web_tools
    monkeypatch.setattr(plugins, 'discover_plugins', lambda: None)
    provider = SimpleNamespace(name='perplexity-pro', is_available=lambda: False)
    monkeypatch.setattr(web_search_registry, 'get_active_search_provider', lambda: provider)
    monkeypatch.setattr(web_tools, '_get_search_backend', lambda: 'perplexity-pro')
    code, result = module().check(live=True)
    assert code == 1 and result['status'] == 'runtime_missing'
    provider.is_available = lambda: True
    monkeypatch.setattr(config, 'load_config_readonly', lambda: {'web': {'keyless_rescue': True}})
    code, result = module().check(live=True)
    assert code == 1 and result['status'] == 'rescue_enabled'


def test_live_invokes_native_dispatcher_once_with_fixture(monkeypatch):
    from hermes_cli import plugins, config
    from agent import web_search_registry
    from tools import web_tools
    monkeypatch.setattr(plugins, 'discover_plugins', lambda: None)
    provider = SimpleNamespace(name='perplexity-pro', is_available=lambda: True)
    monkeypatch.setattr(web_search_registry, 'get_active_search_provider', lambda: provider)
    monkeypatch.setattr(web_tools, '_get_search_backend', lambda: 'perplexity-pro')
    monkeypatch.setattr(config, 'load_config_readonly', lambda: {'web': {'keyless_rescue': False}})
    calls = []
    def native(query, limit):
        calls.append((query, limit))
        return json.dumps({'success': True, 'data': {'web': []}})
    monkeypatch.setattr(web_tools, 'web_search_tool', native)
    code, result = module().check(live=True)
    assert code == 0 and result['status'] == 'live_ok'
    assert len(calls) == 1 and calls[0][1] == 2
