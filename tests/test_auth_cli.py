"""Real native plugin CLI discovery in disposable Hermes homes (no network)."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_provider import PLUGIN
from test_session import session_module


@pytest.fixture
def installed(tmp_path):
    profile = tmp_path / 'profile'
    plugin = profile / 'plugins/web/perplexity-pro'
    plugin.parent.mkdir(parents=True)
    shutil.copytree(PLUGIN, plugin, ignore=shutil.ignore_patterns('__pycache__'))
    (profile / 'config.yaml').write_text(json.dumps({'plugins': {'enabled': ['web/perplexity-pro']}}))
    runtime = profile / 'plugin-runtimes/perplexity-pro/bin/python'
    runtime.parent.mkdir(parents=True)
    runtime.symlink_to(sys.executable)
    home = tmp_path / 'os-home'
    home.mkdir()
    bundled = tmp_path / 'empty-bundled'
    bundled.mkdir()
    env = os.environ.copy()
    env.update(HERMES_HOME=str(profile), HOME=str(home),
               HERMES_BUNDLED_PLUGINS=str(bundled), HERMES_ENABLE_PROJECT_PLUGINS='0',
               PERPLEXITY_SESSION_TOKEN='SECRET_FOREIGN_ENV', PYTHONDONTWRITEBYTECODE='1')
    return profile, env


def cli(env, *args):
    return subprocess.run([sys.executable, '-m', 'hermes_cli.main', 'perplexity-pro', *args],
                          env=env, text=True, capture_output=True, timeout=30)


def test_native_plugin_cli_help_and_local_commands(installed):
    profile, env = installed
    result = cli(env, '--help')
    assert result.returncode == 0, result.stderr
    assert all(word in result.stdout for word in ['login', 'status', 'logout'])
    result = cli(env, 'status')
    assert result.returncode == 1 and 'missing' in result.stdout
    store = session_module().SessionStore(profile)
    store.save('SECRET_PROFILE_FIXTURE')
    result = cli(env, 'status')
    assert result.returncode == 0 and 'present-unchecked' in result.stdout
    assert 'SECRET' not in result.stdout + result.stderr
    # Removing the runtime must not prevent local logout.
    (profile / 'plugin-runtimes/perplexity-pro/bin/python').unlink()
    result = cli(env, 'status', '--online')
    assert result.returncode == 2 and 'dependency' in result.stdout
    result = cli(env, 'logout')
    assert result.returncode == 0 and 'local' in result.stdout
    assert store.read() is None
    assert 'SECRET' not in result.stdout + result.stderr


def test_code_update_preserves_profile_session(installed, tmp_path):
    profile, env = installed
    store = session_module().SessionStore(profile)
    store.save('SECRET_RETAINED_FIXTURE')
    plugin = profile / 'plugins/web/perplexity-pro'
    backup = tmp_path / 'backup-outside-discovery'
    plugin.rename(backup)
    shutil.copytree(PLUGIN, plugin, ignore=shutil.ignore_patterns('__pycache__'))
    result = cli(env, 'status')
    assert result.returncode == 0 and 'present-unchecked' in result.stdout
    assert store.read() == 'SECRET_RETAINED_FIXTURE'
    # A code rollback also does not touch the separate auth store.
    shutil.rmtree(plugin)
    backup.rename(plugin)
    assert store.read() == 'SECRET_RETAINED_FIXTURE'
    assert 'SECRET' not in result.stdout + result.stderr


def test_real_profile_flags_do_not_cross_sessions(installed):
    root, env = installed
    named = root / 'profiles/research'
    shutil.copytree(root / 'plugins', named / 'plugins')
    (named / 'config.yaml').write_text((root / 'config.yaml').read_text())
    store = session_module()
    default_store, named_store = store.SessionStore(root), store.SessionStore(named)
    default_store.save('SECRET_DEFAULT_FIXTURE')
    named_store.save('SECRET_NAMED_FIXTURE')
    # A sticky active profile must not override explicit -p default.
    (root / 'active_profile').write_text('research')
    def selected(name, action):
        return subprocess.run([sys.executable, '-m', 'hermes_cli.main', '-p', name,
                               'perplexity-pro', action], env=env, text=True,
                              capture_output=True, timeout=30)
    result = selected('default', 'status')
    assert result.returncode == 0 and 'present-unchecked' in result.stdout, result.stderr
    result = selected('research', 'logout')
    assert result.returncode == 0, result.stderr
    assert named_store.read() is None
    assert default_store.read() == 'SECRET_DEFAULT_FIXTURE'
    assert 'SECRET' not in result.stdout + result.stderr


def test_logout_ignores_global_sdk_file_and_foreign_env(installed):
    profile, env = installed
    global_file = Path(env['HOME']) / '.config/perplexity-web-mcp/token'
    global_file.parent.mkdir(parents=True)
    global_file.write_text('SECRET_GLOBAL_FIXTURE')
    global_file.chmod(0o600)
    result = cli(env, 'status', '--online')
    assert result.returncode == 1 and 'missing' in result.stdout
    result = cli(env, 'logout')
    assert result.returncode == 0
    assert global_file.read_text() == 'SECRET_GLOBAL_FIXTURE'
    assert 'SECRET' not in result.stdout + result.stderr


def test_online_missing_session_does_not_require_sdk_runtime(installed):
    profile, env = installed
    (profile / 'plugin-runtimes/perplexity-pro/bin/python').unlink()
    result = cli(env, 'status', '--online')
    assert result.returncode == 1 and 'perplexity-pro/missing:' in result.stdout
    assert 'SECRET' not in result.stdout + result.stderr


def auth_cli_module():
    from test_provider import load_provider
    import importlib
    load_provider()
    return importlib.import_module('perplexity_pro_tests.auth_cli')


@pytest.mark.parametrize('kind,expected', [('noise', 'runtime-error'), ('crash', 'runtime-error'),
    ('timeout', 'unreachable'), ('missing', 'dependency'), ('os', 'storage-error'),
    ('interrupt', 'cancelled')])
def test_cli_subprocess_error_paths_never_echo_output(monkeypatch, tmp_path, capfd, kind, expected):
    m = auth_cli_module()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    session_module().SessionStore(tmp_path).save('SECRET_PROFILE_FIXTURE')
    def child(*args, **kwargs):
        if kind == 'timeout':
            raise subprocess.TimeoutExpired('SECRET', 45, output='SECRET', stderr='SECRET')
        if kind == 'missing':
            raise FileNotFoundError('SECRET')
        if kind == 'os':
            raise OSError('SECRET')
        if kind == 'interrupt':
            raise KeyboardInterrupt('SECRET')
        return subprocess.CompletedProcess([], 1 if kind == 'crash' else 0, 'SECRET')
    monkeypatch.setattr(m.subprocess, 'run', child)
    assert m.run_action('status', online=True) != 0
    output = ''.join(capfd.readouterr())
    assert expected in output
    assert 'SECRET' not in output


@pytest.mark.parametrize('state,label,expected', [
    ('valid', 'Авторизован: да', 0),
    ('rejected', 'Авторизован: нет', 1),
    ('unreachable', 'Авторизован: не удалось проверить', 2),
    ('present-unchecked', 'Авторизован: не проверено', 0),
    ('missing', 'Авторизован: нет локальной сессии', 1),
])
def test_status_explicitly_labels_authorization_without_changing_codes(monkeypatch, tmp_path, capfd, state, label, expected):
    m = auth_cli_module()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    if state != 'missing':
        session_module().SessionStore(tmp_path).save('SECRET_PROFILE_FIXTURE')
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 0, state))
    online = state in ('valid', 'rejected', 'unreachable')
    assert m.run_action('status', online=online) == expected
    output = ''.join(capfd.readouterr())
    assert f'perplexity-pro/{state}:' in output and label in output
    assert 'SECRET' not in output


def test_auth_cli_changes_only_child_environment(monkeypatch, tmp_path):
    m = auth_cli_module()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    monkeypatch.setenv('PERPLEXITY_SESSION_TOKEN', 'SECRET_FOREIGN_ENV')
    previous = os.environ.copy()
    env = m.child_environment(tmp_path)
    assert 'PERPLEXITY_SESSION_TOKEN' not in env
    assert env['HERMES_HOME'] == str(tmp_path)
    assert os.environ == previous


@pytest.mark.parametrize('outcome', ['timeout', 'interrupt', 'exit'])
@pytest.mark.parametrize('controlling_tty', [True, False])
def test_login_restores_terminal_after_child_termination(monkeypatch, tmp_path, outcome, controlling_tty):
    """A synthetic child, not auth_worker/login: real PTY and subprocess kill."""
    import errno
    import pty
    import termios
    m = auth_cli_module()
    master, slave = pty.openpty()
    child = tmp_path / 'synthetic_terminal_child.py'
    child.write_text(
        'import sys, termios, time\n'
        'attrs = termios.tcgetattr(0)\n'
        'attrs[3] &= ~termios.ECHO\n'
        'termios.tcsetattr(0, termios.TCSANOW, attrs)\n'
        + ('time.sleep(30)\n' if outcome != 'exit' else 'print("failed")\n'))
    original_run, original_open = subprocess.run, os.open
    def open_tty(path, flags, *args, **kwargs):
        if path == '/dev/tty':
            if not controlling_tty:
                raise OSError(errno.ENXIO, 'synthetic no controlling terminal')
            return os.dup(slave)
        return original_open(path, flags, *args, **kwargs)
    def run(*args, **kwargs):
        try:
            return original_run([sys.executable, str(child)], stdin=slave,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=0.5)
        except subprocess.TimeoutExpired:
            if outcome == 'interrupt':
                raise KeyboardInterrupt()
            raise
    try:
        before = termios.tcgetattr(slave)
        with os.fdopen(os.dup(slave), 'r') as terminal:
            monkeypatch.setattr(m.sys, 'stdin', terminal)
            monkeypatch.setattr(m.os, 'open', open_tty)
            monkeypatch.setattr(m.subprocess, 'run', run)
            monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
            assert m.run_action('login') == (130 if outcome == 'interrupt' else 2)
        assert termios.tcgetattr(slave) == before, 'child left the terminal with echo disabled'
    finally:
        # Keep the test runner healthy even on RED.
        termios.tcsetattr(slave, termios.TCSANOW, before)
        os.close(slave)
        os.close(master)


def test_show_codes_flag_is_documented_but_rejects_unattended_login(installed):
    _, env = installed
    help_result = cli(env, 'login', '--help')
    assert help_result.returncode == 0 and '--show-codes' in help_result.stdout
    result = cli(env, 'login', '--show-codes')
    assert result.returncode != 0 and 'terminal-required' in result.stdout


def test_login_show_codes_option_reaches_only_child_argv(monkeypatch, tmp_path, capfd):
    import contextlib
    from types import SimpleNamespace
    m = auth_cli_module()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    monkeypatch.setattr(m.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(m, 'preserve_terminal', contextlib.nullcontext)
    commands = []
    def child(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, 'saved')
    monkeypatch.setattr(m.subprocess, 'run', child)
    with pytest.raises(SystemExit) as exit_info:
        m.handle_args(SimpleNamespace(perplexity_action='login', online=False, show_codes=True))
    assert exit_info.value.code == 0
    assert commands[0][-2:] == ['login', '--show-codes']
    assert 'SECRET' not in ''.join(capfd.readouterr())


def test_login_refuses_unattended_input_without_network(installed):
    _, env = installed
    result = cli(env, 'login')
    assert result.returncode != 0
    assert 'terminal-required' in result.stdout
    assert 'SECRET' not in result.stdout + result.stderr
