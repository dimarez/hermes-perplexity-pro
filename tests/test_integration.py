"""Real Hermes loader + dispatcher; successful search data is explicitly mocked."""
import json
import os
import subprocess
from pathlib import Path

from test_provider import PLUGIN


def test_real_plugin_doctor():
    from hermes_cli.plugin_dev import doctor_plugin
    report = doctor_plugin(PLUGIN)
    assert report.ok, report.format_text()
    assert report.manifest.name == 'web-perplexity-pro'
    assert report.registered_tools == ('deep_research',)
    assert 'web_search' not in report.registered_tools  # Preserve the native search tool.


def test_real_loader_and_native_dispatch(monkeypatch, tmp_path):
    from hermes_cli.plugin_dev import _doctor_runtime
    from agent.web_search_registry import get_provider
    from hermes_cli import config
    from tools import web_tools

    settings = {'web': {'search_backend': 'perplexity-pro', 'extract_backend': 'firecrawl',
                        'keyless_rescue': False, 'keyless_enabled': False}}
    monkeypatch.setattr(config, 'load_config', lambda *a, **kw: settings)
    monkeypatch.setattr(web_tools, '_ensure_web_plugins_loaded', lambda: None)
    with _doctor_runtime(PLUGIN):
        provider = get_provider('perplexity-pro')
        assert provider is not None
        assert provider.supports_extract() is False
        # Test-side SDK interpreter injection only; shipped runtime is plugin-owned.
        monkeypatch.setattr(provider, 'worker_python', lambda: Path(__import__('sys').executable))
        assert provider.is_available() is True
        assert web_tools._get_search_backend() == 'perplexity-pro'
        assert web_tools._get_extract_backend() == 'firecrawl'
        fixture = {'success': True, 'data': {'web': [
            {'title': 'Fixture, not live', 'url': 'https://example.org/', 'description': '', 'position': 1}
        ]}}
        module = __import__(provider.__class__.__module__, fromlist=['subprocess'])
        def run(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, json.dumps(fixture))
        with monkeypatch.context() as patch:
            patch.setattr(module.subprocess, 'run', run)
            result = json.loads(web_tools.web_search_tool('offline dispatcher fixture', 3))
            assert result == fixture

        # A real SDK subprocess with an empty temporary HOME: no credentials read, no HTTP.
        monkeypatch.setenv('HOME', str(tmp_path))
        monkeypatch.delenv('PERPLEXITY_SESSION_TOKEN', raising=False)
        result = json.loads(web_tools.web_search_tool('missing-session-check', 5))
        assert result['success'] is False
        assert '/auth:' in result['error']
