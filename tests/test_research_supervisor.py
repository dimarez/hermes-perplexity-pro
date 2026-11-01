"""Actual child-process paths and timeouts; network is never requested."""
import importlib.util
import os
from pathlib import Path
import time

import pytest
from test_provider import PLUGIN, load_provider
from test_research_jobs import jobs_module


def supervisor_module():
    path = PLUGIN / 'research_supervisor.py'
    assert path.is_file(), 'bounded research supervisor is not implemented'
    load_provider()
    spec = importlib.util.spec_from_file_location('perplexity_pro_tests.research_supervisor', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_worker_without_session_finishes_auth_failure(tmp_path, monkeypatch):
    m = supervisor_module()
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('PERPLEXITY_SESSION_TOKEN', 'FOREIGN_SECRET')
    store = jobs_module().JobStore(tmp_path)
    job, _ = store.create('owner', 'offline missing profile only', 60, 'r')
    assert m.supervise(job['id']) == 0
    assert store.status(job['id'], 'owner') == {'job_id': job['id'], 'status': 'failed', 'code': 'auth'}
    assert m.supervise(job['id']) == 0  # no rerun of a terminal job


def test_actual_timeout_kills_and_reaps_sdk_child(tmp_path, monkeypatch):
    m = supervisor_module()
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    pid_file = tmp_path / 'pid'
    child = tmp_path / 'sleeping_sdk.py'
    child.write_text('import os,time\nfrom pathlib import Path\nPath(' + repr(str(pid_file)) + ').write_text(str(os.getpid()))\ntime.sleep(30)\n')
    monkeypatch.setattr(m, 'WORKER', child)
    store = jobs_module().JobStore(tmp_path)
    # Internal short budget for a fast cleanup test; public schema still requires >=60.
    job, _ = store.create('owner', 'offline timeout fixture', 1, 'timeout-r')
    assert m.supervise(job['id']) == 0
    assert store.status(job['id'], 'owner')['code'] == 'timeout'
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_non_bmp_query_at_public_limit_survives_real_stdin(tmp_path, monkeypatch):
    m = supervisor_module()
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = jobs_module().JobStore(tmp_path)
    job, _ = store.create('owner', '\U0001f600' * 16000, 60, 'unicode-request')
    assert m.supervise(job['id']) == 0
    # Reaching auth (not protocol) proves the entire accepted query reached the
    # real worker's request validator, without any session or network.
    assert store.status(job['id'], 'owner')['code'] == 'auth'


@pytest.mark.parametrize('output,expected', [('noise', 'protocol'), ('{"status":"completed","report":"intro"}', 'incomplete')])
def test_malformed_worker_is_terminal_failure(tmp_path, monkeypatch, output, expected):
    m = supervisor_module()
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    child = tmp_path / 'fixture_sdk.py'
    child.write_text('print(' + repr(output) + ')\n')
    monkeypatch.setattr(m, 'WORKER', child)
    store = jobs_module().JobStore(tmp_path)
    job, _ = store.create('owner', 'offline fixture', 60, 'r')
    assert m.supervise(job['id']) == 0
    assert store.status(job['id'], 'owner')['code'] == expected
