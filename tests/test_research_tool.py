"""Public tool actions with session-injected ownership; all child fixtures offline."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

import pytest
from test_provider import PLUGIN, load_provider


def tool_module():
    path = PLUGIN / 'research_tool.py'
    assert path.is_file(), 'deep_research tool actions are not implemented'
    load_provider()
    spec = importlib.util.spec_from_file_location('perplexity_pro_tests.research_tool', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_start_is_fast_idempotent_and_does_not_import_sdk(tmp_path, monkeypatch):
    m = tool_module()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    runtime = tmp_path / 'plugin-runtimes/perplexity-pro/bin/python'
    runtime.parent.mkdir(parents=True)
    runtime.symlink_to(sys.executable)
    launches = []
    monkeypatch.setattr(m, 'launch', lambda *args: launches.append(args))
    args = {'action': 'start', 'query': 'offline fixture', 'request_id': 'req-one'}
    started = time.monotonic()
    response = json.loads(m.handle(args, session_id='session-one'))
    assert time.monotonic() - started < 2
    assert response['success'] is True and response['data']['status'] == 'queued'
    job_id = response['data']['job_id']
    duplicate = json.loads(m.handle(args, session_id='session-one'))
    assert duplicate['data']['job_id'] == job_id and len(launches) == 1
    foreign = json.loads(m.handle({'action': 'status', 'job_id': job_id}, session_id='foreign'))
    assert foreign['success'] is False and foreign['code'] == 'not_found'


@pytest.mark.parametrize('args', [None, [], {}, {'action': 'unknown'},
    {'action': 'start', 'query': ''}, {'action': 'start', 'query': 'x', 'timeout_seconds': True},
    {'action': 'start', 'query': 'x', 'timeout_seconds': 1801},
    {'action': 'start', 'query': 'x', 'request_id': '../escape'},
    {'action': 'start', 'query': 'x', 'session_id': 'spoofed'},
    {'action': 'result', 'job_id': '../escape'}, {'action': 'status', 'job_id': 'a' * 32, 'query': 'extra'}])
def test_invalid_input_never_starts_process(tmp_path, monkeypatch, args):
    m = tool_module()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    def forbidden(*args):
        raise AssertionError('invalid input started a process')
    monkeypatch.setattr(m, 'launch', forbidden)
    assert json.loads(m.handle(args, session_id='owner'))['code'] == 'input'
    assert not (tmp_path / 'plugin-results').exists()


def test_missing_trusted_context_fails_without_storage(tmp_path, monkeypatch):
    m = tool_module()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    assert json.loads(m.handle({'action': 'start', 'query': 'offline'}))['code'] == 'context'
    assert not (tmp_path / 'plugin-results').exists()


def test_reaper_start_failure_returns_json_job_id_before_any_process(tmp_path, monkeypatch):
    m = tool_module()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    runtime = tmp_path / 'plugin-runtimes/perplexity-pro/bin/python'
    runtime.parent.mkdir(parents=True)
    runtime.symlink_to(sys.executable)
    launched = []
    popen = m.subprocess.Popen
    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        launched.append(process)
        return process
    monkeypatch.setattr(m.subprocess, 'Popen', capture)
    def no_thread(*args, **kwargs):
        raise RuntimeError('SECRET_THREAD_FAILURE')
    monkeypatch.setattr(m.threading.Thread, 'start', no_thread)
    try:
        response = json.loads(m.handle({'action': 'start', 'query': 'offline', 'request_id': 'thread-r'}, session_id='owner'))
        assert response['code'] == 'runtime' and response['job_id']
        assert 'SECRET' not in str(response)
        assert launched == []
        status = json.loads(m.handle({'action': 'status', 'job_id': response['job_id']}, session_id='owner'))
        assert status['data']['status'] == 'failed'
    finally:
        for process in launched:
            process.wait(timeout=10)


def test_actual_detached_worker_without_session_reaches_auth_failure(tmp_path, monkeypatch):
    m = tool_module()
    monkeypatch.setattr(m, 'get_hermes_home', lambda: tmp_path)
    runtime = tmp_path / 'plugin-runtimes/perplexity-pro/bin/python'
    runtime.parent.mkdir(parents=True)
    runtime.symlink_to(sys.executable)
    monkeypatch.setenv('PERPLEXITY_SESSION_TOKEN', 'FOREIGN_SECRET')
    monkeypatch.setenv('PYTHONPATH', '/nonexistent/foreign-python')
    original_environment = os.environ.copy()
    started = json.loads(m.handle({'action': 'start', 'query': 'offline missing auth'}, session_id='owner'))
    assert started['success'] is True
    job_id = started['data']['job_id']
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = json.loads(m.handle({'action': 'status', 'job_id': job_id}, session_id='owner'))
        if status['data']['status'] == 'failed':
            break
        time.sleep(0.05)
    assert status['data']['code'] == 'auth'
    assert os.environ == original_environment
