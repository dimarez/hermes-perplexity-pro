"""Foreign Hermes Python paths must not break the separate SDK interpreter."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_auth_cli import auth_cli_module
from test_provider import PLUGIN, load_provider


@pytest.mark.parametrize('variable', ['PYTHONPATH', 'PYTHONHOME'])
@pytest.mark.parametrize('operation', ['login', 'search'])
def test_foreign_python_environment_does_not_break_sidecar(monkeypatch, tmp_path, variable, operation):
    foreign = tmp_path / 'foreign-python'
    foreign.mkdir()
    (foreign / 'json.py').write_text('raise ImportError("foreign Python dependency")\n')
    monkeypatch.setenv(variable, str(foreign))
    profile = tmp_path / 'profile'
    profile.mkdir()
    previous = os.environ.copy()
    if operation == 'login':
        module = auth_cli_module()
        # Empty email stops the real login after SDK import, before any HTTP.
        program = (
            f'import sys; sys.path.insert(0, {str(PLUGIN)!r}); '
            'from auth_worker import login; from session import SessionStore; '
            'from pathlib import Path; '
            f'print(login(SessionStore(Path({str(profile)!r})), prompt=lambda _: ""))'
        )
        result = subprocess.run([sys.executable, '-c', program],
            env=module.child_environment(profile), text=True, capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == 'failed'  # Not a dependency failure.
    else:
        module = load_provider()
        monkeypatch.setattr(module, 'get_hermes_home', lambda: profile)
        runtime = profile / 'plugin-runtimes/perplexity-pro/bin/python'
        runtime.parent.mkdir(parents=True)
        runtime.symlink_to(sys.executable)
        result = module.PerplexityProProvider().search('offline isolation regression')
        # The real worker reaches the missing-session guard, without SDK HTTP.
        assert result['success'] is False
        assert '/auth:' in result['error']
    assert os.environ == previous
