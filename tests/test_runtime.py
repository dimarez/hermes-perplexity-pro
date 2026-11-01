"""External SDK runtime: do not inject a VCS requirement into Hermes PM."""
import os
from pathlib import Path

from test_provider import PLUGIN, load_provider


def test_vcs_dependency_is_external_to_hermes_pm():
    from pm.plugin_declarations import read_python_declaration
    declaration = read_python_declaration(PLUGIN)
    assert declaration.external is True
    assert declaration.install_requirements == ()


def test_worker_interpreter_is_plugin_owned(monkeypatch, tmp_path):
    m = load_provider()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    provider = m.PerplexityProProvider()
    expected = tmp_path / 'plugin-runtimes' / 'perplexity-pro' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    assert provider.worker_python() == expected
    assert provider.is_available() is False
    assert '/dependency:' in provider.search('missing-runtime offline check')['error']
    expected.parent.mkdir(parents=True)
    expected.touch()
    expected.chmod(0o700)
    assert provider.is_available() is True


def test_large_unicode_query_is_not_truncated_before_auth_check(tmp_path):
    import json
    import subprocess
    import sys
    environment = os.environ.copy()
    environment['HOME'] = str(tmp_path)
    environment['HERMES_HOME'] = str(tmp_path)
    environment.pop('PERPLEXITY_SESSION_TOKEN', None)
    completed = subprocess.run([sys.executable, str(PLUGIN / 'worker.py')],
        input=json.dumps({'query': 'я' * 12000, 'limit': 5}), text=True,
        capture_output=True, env=environment, timeout=15)
    response = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert '/auth:' in response['error']
    assert completed.stderr == ''
