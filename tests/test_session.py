"""Real filesystem fixtures only; never inspect a user's existing credentials."""
import importlib.util
import stat
from pathlib import Path

from test_provider import PLUGIN


def session_module():
    path = PLUGIN / 'session.py'
    assert path.exists(), 'profile-owned session store is missing'
    spec = importlib.util.spec_from_file_location('session_store_tests', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_private_atomic_store_is_profile_scoped(tmp_path):
    m = session_module()
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir()
    b.mkdir()
    first, second = m.SessionStore(a), m.SessionStore(b)
    assert first.read() is None
    first.save('FIXTURE_ONE')
    second.save('FIXTURE_TWO')
    assert first.read() == 'FIXTURE_ONE'
    assert second.read() == 'FIXTURE_TWO'
    first.save('FIXTURE_REPLACEMENT')
    assert first.read() == 'FIXTURE_REPLACEMENT'
    assert stat.S_IMODE(first.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(first.path.parent.stat().st_mode) == 0o700
    assert sorted(p.name for p in first.path.parent.iterdir()) == ['token']
    assert first.logout() is True
    assert first.logout() is False
    assert first.read() is None
    assert second.read() == 'FIXTURE_TWO'


import pytest


@pytest.mark.parametrize('part', ['home', 'plugin-auth', 'perplexity-pro', 'token'])
def test_symlink_read_write_logout_fail_closed(tmp_path, part):
    m = session_module()
    home = tmp_path / 'profile'
    home.mkdir()
    store = m.SessionStore(home)
    store.save('ORIGINAL_FIXTURE')
    target = tmp_path / 'unrelated'
    if part == 'token':
        target.write_text('UNRELATED_FIXTURE')
        target.chmod(0o600)
        store.path.unlink()
        store.path.symlink_to(target)
    else:
        source = {'home': home, 'plugin-auth': home / 'plugin-auth',
                  'perplexity-pro': store.path.parent}[part]
        source.rename(target)
        source.symlink_to(target, target_is_directory=True)
    for action in (store.read, lambda: store.save('NEW_FIXTURE'), store.logout):
        with pytest.raises(m.StoreError):
            action()
    if part == 'token':
        assert target.read_text() == 'UNRELATED_FIXTURE'
    else:
        assert list(target.rglob('token'))[0].read_text() == 'ORIGINAL_FIXTURE'


def test_store_file_disappearing_during_read_has_opaque_error(monkeypatch, tmp_path):
    m = session_module()
    store = m.SessionStore(tmp_path)
    store.save('FIXTURE')
    real_open = m.os.open
    def vanished(path, *args, **kwargs):
        if path == 'token':
            raise FileNotFoundError('SECRET_OS_DETAILS')
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(m.os, 'open', vanished)
    with pytest.raises(m.StoreError):
        store.read()


def test_post_commit_fsync_failure_is_not_reported_as_old_session_retained(monkeypatch, tmp_path):
    m = session_module()
    import os
    store = m.SessionStore(tmp_path)
    store.save('OLD_FIXTURE')
    real_fsync = os.fsync
    def fail_directory(descriptor):
        if os.fstat(descriptor).st_ino == store.path.parent.stat().st_ino:
            raise OSError('SECRET_FS_DETAILS')
        return real_fsync(descriptor)
    monkeypatch.setattr(os, 'fsync', fail_directory)
    with pytest.raises(m.ChangeUncertain):
        store.save('NEW_FIXTURE')
    assert store.read() == 'NEW_FIXTURE'
    with pytest.raises(m.ChangeUncertain):
        store.logout()
    assert store.read() is None


def test_first_save_syncs_new_directory_entries_before_token(monkeypatch, tmp_path):
    import os
    m = session_module()
    store = m.SessionStore(tmp_path)
    calls = []
    real_fsync = os.fsync
    def sync(descriptor):
        calls.append(os.fstat(descriptor).st_ino)
        return real_fsync(descriptor)
    monkeypatch.setattr(os, 'fsync', sync)
    store.save('FIXTURE')
    assert calls == [tmp_path.stat().st_ino, (tmp_path / 'plugin-auth').stat().st_ino,
                     store.path.stat().st_ino, store.path.parent.stat().st_ino]


@pytest.mark.parametrize('fail_on', [1, 2])
def test_first_save_directory_sync_failure_cannot_claim_saved(monkeypatch, tmp_path, fail_on):
    import os
    m = session_module()
    store = m.SessionStore(tmp_path)
    calls = []
    real_fsync = os.fsync
    def sync(descriptor):
        calls.append(descriptor)
        if len(calls) == fail_on:
            raise OSError('SECRET_FS_FIXTURE')
        return real_fsync(descriptor)
    monkeypatch.setattr(os, 'fsync', sync)
    with pytest.raises(m.StoreError):
        store.save('FIXTURE')
    assert not store.path.exists()


def test_retry_after_directory_sync_failure_confirms_existing_ancestors(monkeypatch, tmp_path):
    import os
    m = session_module()
    store = m.SessionStore(tmp_path)
    def fail(descriptor):
        raise OSError('SECRET_FS_FIXTURE')
    with monkeypatch.context() as patch:
        patch.setattr(os, 'fsync', fail)
        with pytest.raises(m.StoreError):
            store.save('NOT_SAVED_FIXTURE')
    calls = []
    real_fsync = os.fsync
    def sync(descriptor):
        calls.append(os.fstat(descriptor).st_ino)
        return real_fsync(descriptor)
    monkeypatch.setattr(os, 'fsync', sync)
    store.save('RETRY_FIXTURE')
    assert calls == [tmp_path.stat().st_ino, (tmp_path / 'plugin-auth').stat().st_ino,
                     store.path.stat().st_ino, store.path.parent.stat().st_ino]


def test_failed_atomic_replace_preserves_old_session(monkeypatch, tmp_path):
    m = session_module()
    store = m.SessionStore(tmp_path)
    store.save('OLD_FIXTURE')
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(m.os, 'replace', interrupted)
    with pytest.raises(KeyboardInterrupt):
        store.save('NEW_FIXTURE')
    assert store.read() == 'OLD_FIXTURE'
    assert sorted(p.name for p in store.path.parent.iterdir()) == ['token']


@pytest.mark.parametrize('mode', [0o644, 0o666])
def test_unsafe_file_permissions_fail_closed(tmp_path, mode):
    m = session_module()
    store = m.SessionStore(tmp_path)
    store.save('FIXTURE')
    store.path.chmod(mode)
    for action in (store.read, store.logout, lambda: store.save('NEW_FIXTURE')):
        with pytest.raises(m.StoreError):
            action()
