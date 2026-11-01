"""Real local SQLite/filesystem; no SDK or service calls."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def jobs_module():
    path = ROOT / 'plugin/research_jobs.py'
    assert path.is_file(), 'profile-scoped research jobs are not implemented'
    spec = importlib.util.spec_from_file_location('research_jobs_tests', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_job_is_persistent_idempotent_and_session_owned(tmp_path):
    m = jobs_module()
    store = m.JobStore(tmp_path)
    first, created = store.create('session-one', 'offline query', 900, 'request-1')
    assert created and first['status'] == 'queued'
    second, created = m.JobStore(tmp_path).create('session-one', 'offline query', 900, 'request-1')
    assert not created and second['id'] == first['id']
    assert m.JobStore(tmp_path).get(first['id'], 'session-one')['query'] == 'offline query'
    with pytest.raises(m.JobError, match='not_found'):
        store.get(first['id'], 'other-session')
    assert store.database.stat().st_mode & 0o077 == 0


def test_claim_once_and_completed_report_is_private_and_owned(tmp_path):
    m = jobs_module()
    store = m.JobStore(tmp_path)
    job, _ = store.create('owner', 'offline', 900, 'r1')
    assert store.claim(job['id'])['status'] == 'running'
    assert store.claim(job['id']) is None
    assert store.finish(job['id'], {'status': 'completed', 'full_report': True,
                                   'report': '# OFFLINE fixture report',
                                   'sources': [{'title': 'Source', 'url': 'https://example.org/'}]})
    result = store.result(job['id'], 'owner')
    assert result['report'] == '# OFFLINE fixture report'
    assert result['sources'] == [{'title': 'Source', 'url': 'https://example.org/'}]
    assert Path(result['report_path']).stat().st_mode & 0o077 == 0
    with pytest.raises(m.JobError, match='not_found'):
        store.result(job['id'], 'foreign')
    assert store.finish(job['id'], {'status': 'failed', 'code': 'runtime'}) is False


def test_dead_supervisor_is_interrupted_without_resubmission(tmp_path, monkeypatch):
    m = jobs_module()
    store = m.JobStore(tmp_path)
    job, _ = store.create('owner', 'offline', 900, 'r1')
    store.claim(job['id'])
    def missing(pid, sig):
        raise ProcessLookupError()
    monkeypatch.setattr(m.os, 'kill', missing)
    status = store.status(job['id'], 'owner')
    assert status == {'job_id': job['id'], 'status': 'interrupted', 'code': 'interrupted'}
    duplicate, created = store.create('owner', 'offline', 900, 'r1')
    assert not created and duplicate['status'] == 'interrupted'


@pytest.mark.parametrize('component', ['plugin-results', 'database', 'report'])
def test_symlinks_are_refused_without_touching_target(tmp_path, component):
    m = jobs_module()
    store = m.JobStore(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    target = outside / 'protected'
    target.write_text('ORIGINAL')
    if component == 'plugin-results':
        (tmp_path / 'plugin-results').symlink_to(outside, target_is_directory=True)
        with pytest.raises(m.JobError, match='storage'):
            store.create('owner', 'offline', 900, 'r')
    else:
        job, _ = store.create('owner', 'offline', 900, 'r')
        if component == 'database':
            store.database.unlink()
            store.database.symlink_to(target)
            with pytest.raises(m.JobError, match='storage'):
                store.get(job['id'], 'owner')
        else:
            store.claim(job['id'])
            (store.root / (job['id'] + '.md')).symlink_to(target)
            with pytest.raises(m.JobError, match='storage'):
                store.finish(job['id'], {'status': 'completed', 'full_report': True, 'report': 'fixture'})
            assert store.get(job['id'], 'owner')['status'] == 'running'
    assert target.read_text() == 'ORIGINAL'


def test_conflicting_idempotency_and_concurrent_job_refused(tmp_path):
    m = jobs_module()
    store = m.JobStore(tmp_path)
    store.create('owner', 'offline', 900, 'r')
    with pytest.raises(m.JobError, match='conflict'):
        store.create('owner', 'different', 900, 'r')
    with pytest.raises(m.JobError, match='busy'):
        store.create('owner', 'offline', 900, 'another-request')


def test_incomplete_is_not_completed_and_signed_sources_are_omitted(tmp_path):
    m = jobs_module()
    store = m.JobStore(tmp_path)
    job, _ = store.create('owner', 'offline', 900, 'r')
    store.claim(job['id'])
    with pytest.raises(m.JobError, match='incomplete'):
        store.finish(job['id'], {'status': 'completed', 'report': 'intro'})
    assert store.get(job['id'], 'owner')['status'] == 'running'
    store.finish(job['id'], {'status': 'completed', 'full_report': True, 'report': 'fixture',
                            'sources': [{'url': 'https://x.cloudfront.net/report?Signature=SECRET'},
                                        {'url': 'https://user:SECRET@example.org/'},
                                        {'url': 'https://example.org/', 'title': 'Good'}]})
    assert store.result(job['id'], 'owner')['sources'] == [{'url': 'https://example.org/', 'title': 'Good'}]


def test_missing_sqlite_serialization_fails_before_creating_storage(tmp_path, monkeypatch):
    m = jobs_module()
    monkeypatch.setattr(m.sqlite3, 'Connection', object)
    with pytest.raises(m.JobError, match='dependency'):
        m.JobStore(tmp_path).create('owner', 'offline', 900, 'r')
    assert not (tmp_path / 'plugin-results').exists()


def test_database_swap_after_validation_never_modifies_external_database(tmp_path, monkeypatch):
    import sqlite3
    m = jobs_module()
    store = m.JobStore(tmp_path)
    external = tmp_path / 'external.sqlite3'
    with sqlite3.connect(external) as db:
        db.execute('CREATE TABLE protected(value TEXT)')
        db.execute("INSERT INTO protected VALUES('ORIGINAL')")
    before = external.read_bytes()
    check = store._check_file
    swapped = []
    def replace_after_check(directory, name):
        result = check(directory, name)
        if name == 'jobs.sqlite3' and not swapped:
            swapped.append(True)
            store.database.unlink()
            store.database.symlink_to(external)
        return result
    monkeypatch.setattr(store, '_check_file', replace_after_check)
    with pytest.raises(m.JobError):
        store.create('owner', 'offline race', 900, 'r')
    assert external.read_bytes() == before, 'unsafe SQLite target was modified'


def test_live_supervisor_keeps_execution_slot_after_clock_jump(tmp_path, monkeypatch):
    m = jobs_module()
    store = m.JobStore(tmp_path)
    job, _ = store.create('owner', 'offline', 60, 'r')
    store.claim(job['id'])
    now = m.time.time()
    monkeypatch.setattr(m.time, 'time', lambda: now + 10000)
    assert store.status(job['id'], 'owner')['status'] == 'running'
    with pytest.raises(m.JobError, match='busy'):
        store.create('new-owner', 'another', 60, 'new')


def test_status_snapshot_cannot_interrupt_a_fresh_claim(tmp_path, monkeypatch):
    m = jobs_module()
    store = m.JobStore(tmp_path)
    job, _ = store.create('owner', 'offline race', 900, 'r')
    now = m.time.time()
    monkeypatch.setattr(m.time, 'time', lambda: now + 40)
    stale = store._stale
    claimed = []
    def race(row):
        old_verdict = stale(row)
        if not claimed:
            claimed.append(store.claim(job['id']))
        return old_verdict
    monkeypatch.setattr(store, '_stale', race)
    assert store.status(job['id'], 'owner')['status'] == 'running'
    assert claimed[0]['status'] == 'running'
    with pytest.raises(m.JobError, match='busy'):
        store.create('another-owner', 'second attempt', 900, 'r2')


def test_new_session_can_start_after_stale_job_without_access_to_old_result(tmp_path, monkeypatch):
    m = jobs_module()
    store = m.JobStore(tmp_path)
    old, _ = store.create('old-owner', 'offline old', 900, 'old-request')
    original_time = m.time.time
    now = original_time()
    monkeypatch.setattr(m.time, 'time', lambda: now + 40)
    new, created = store.create('new-owner', 'offline new', 900, 'new-request')
    assert created and new['status'] == 'queued'
    assert store.get(old['id'], 'old-owner')['status'] == 'interrupted'
    with pytest.raises(m.JobError, match='not_found'):
        store.get(old['id'], 'new-owner')
