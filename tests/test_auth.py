"""SDK protocol is real; network sessions and terminal input are explicit fixtures."""
import importlib.util
import os
import pytest
from types import SimpleNamespace

from test_provider import PLUGIN
from test_session import session_module


def auth_module():
    path = PLUGIN / 'auth_worker.py'
    assert path.exists(), 'safe local auth wrapper is missing'
    # Load like a script (without importing Hermes or the SDK as a side effect).
    import sys
    spec = importlib.util.spec_from_file_location('auth_worker_tests', path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(PLUGIN))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class Response:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code = status
        self.data = data or {}
        self.headers = headers or {}
        self.text = 'SECRET_REMOTE_BODY'
    def json(self):
        return self.data


class AuthNetwork:
    """Fake only HTTP; real SDK helpers exercise CSRF/OTP/callback/TOTP/cookies."""
    def __init__(self):
        self.cookies = {}
        self.calls = []
        self.closed = False
    def get(self, url, **kwargs):
        self.calls.append(('get', url))
        if url.endswith('/api/auth/csrf'):
            return Response(data={'csrfToken': 'SECRET_CSRF'})
        if url == 'https://www.perplexity.ai/callback-fixture':
            self.cookies['__Secure-next-auth.session-token'] = 'SECRET_SESSION_FIXTURE'
        return Response()
    def post(self, url, **kwargs):
        self.calls.append(('post', url))
        if '/otp-redirect-link' in url:
            return Response(data={'redirect': '/callback-fixture'})
        return Response()
    def close(self):
        self.closed = True


def test_hidden_prompt_refuses_getpass_echo_fallback(monkeypatch):
    import getpass
    import warnings
    m = auth_module()
    def fallback(label):
        warnings.warn('terminal echo unavailable', getpass.GetPassWarning)
        raise AssertionError('must stop before echoed input')
    monkeypatch.setattr(m, 'getpass', fallback)
    with pytest.raises(getpass.GetPassWarning):
        m.hidden_prompt('Code: ')


def test_login_reports_uncertain_durability_after_commit(monkeypatch, tmp_path):
    import stat
    m = auth_module()
    from perplexity_web_mcp import auth
    monkeypatch.setattr(auth, 'Session', lambda **kw: AuthNetwork())
    store = m.SessionStore(tmp_path)
    store.save('OLD_FIXTURE')
    real_fsync = os.fsync
    def fsync(descriptor):
        if os.fstat(descriptor).st_ino == store.path.parent.stat().st_ino:
            raise OSError('SECRET')
        return real_fsync(descriptor)
    monkeypatch.setattr(os, 'fsync', fsync)
    answers = iter(['fixture@example.invalid', '123456'])
    assert m.login(store, prompt=lambda label: next(answers)) == 'changed-unconfirmed'
    assert store.read() == 'SECRET_SESSION_FIXTURE'


def test_login_reuses_sdk_helpers_without_printing_secrets(monkeypatch, tmp_path, capfd):
    m = auth_module()
    from perplexity_web_mcp import auth
    network = AuthNetwork()
    monkeypatch.setattr(auth, 'Session', lambda **kw: network)
    answers = iter(['fixture@example.invalid', '123456'])
    store = m.SessionStore(tmp_path)
    result = m.login(store, prompt=lambda label: next(answers))
    assert result == 'saved'
    assert store.read() == 'SECRET_SESSION_FIXTURE'
    assert network.closed
    assert any('/signin/email' in url for _, url in network.calls)
    output = capfd.readouterr()
    assert 'SECRET' not in output.out + output.err
    assert 'fixture@example.invalid' not in output.out + output.err


@pytest.mark.parametrize('http,expected', [(200, 'valid'), (401, 'rejected'), (403, 'rejected'),
                                         (500, 'unreachable'), (429, 'unreachable'), (None, 'unreachable')])
def test_online_status_uses_real_sdk_probe_and_discards_pii(monkeypatch, tmp_path, capfd, http, expected):
    m = auth_module()
    from perplexity_web_mcp.cli import auth
    calls = []
    class ProbeNetwork:
        def __init__(self, **kwargs):
            assert list(kwargs['cookies'].values()) == ['SECRET_SESSION_FIXTURE']
        def __enter__(self):
            return self
        def __exit__(self, *args):
            calls.append('closed')
        def get(self, *args, **kwargs):
            calls.append('probe')
            print('SECRET_STDOUT')
            os.write(2, b'SECRET_STDERR')
            if http is None:
                raise OSError('SECRET_REMOTE_ERROR')
            return Response(http, {'email': 'SECRET_PII@example.invalid', 'subscription_tier': 'pro'})
    monkeypatch.setattr(auth, 'Session', ProbeNetwork)
    store = m.SessionStore(tmp_path)
    assert m.status(store, online=True) == 'missing'
    assert not calls
    store.save('SECRET_SESSION_FIXTURE')
    assert m.status(store, online=False) == 'present-unchecked'
    assert not calls
    assert m.status(store, online=True) == expected
    assert calls == ['probe', 'closed']
    assert 'SECRET' not in ''.join(capfd.readouterr())


import pytest


@pytest.mark.parametrize('cancel', [KeyboardInterrupt, EOFError])
@pytest.mark.parametrize('stage', [0, 1, 2])
def test_cancel_preserves_existing_session(monkeypatch, tmp_path, capfd, cancel, stage):
    m = auth_module()
    from perplexity_web_mcp import auth
    class TotpNetwork(AuthNetwork):
        def get(self, url, **kwargs):
            if url.endswith('/callback-fixture'):
                return Response(302, headers={'Location': '/auth/totp-challenge?token=SECRET_CHALLENGE'})
            return super().get(url, **kwargs)
    network = TotpNetwork()
    monkeypatch.setattr(auth, 'Session', lambda **kw: network)
    store = m.SessionStore(tmp_path)
    store.save('OLD_FIXTURE')
    count = []
    def prompt(label):
        count.append(label)
        if len(count) - 1 == stage:
            raise cancel('SECRET')
        return '123456'
    assert m.login(store, prompt=prompt) == 'cancelled'
    assert store.read() == 'OLD_FIXTURE'
    if stage:
        assert network.closed
    assert 'SECRET' not in ''.join(capfd.readouterr())


@pytest.mark.parametrize('step', ['csrf', 'signin', 'otp', 'callback', 'cookie'])
def test_login_failure_paths_are_redacted_and_do_not_replace(monkeypatch, tmp_path, capfd, step):
    m = auth_module()
    from perplexity_web_mcp import auth
    class BrokenNetwork(AuthNetwork):
        def get(self, url, **kwargs):
            if step == 'csrf' and url.endswith('/api/auth/csrf'):
                return Response(503)
            if url.endswith('/callback-fixture'):
                if step == 'callback':
                    return Response(302, headers={'Location': '/?error=SECRET_REMOTE_ERROR'})
                if step == 'cookie':
                    return Response()
            return super().get(url, **kwargs)
        def post(self, url, **kwargs):
            print('SECRET_OUTPUT')
            os.write(2, b'SECRET_NATIVE_OUTPUT')
            if step == 'signin' and '/signin/email' in url:
                return Response(500)
            if step == 'otp' and '/otp-redirect-link' in url:
                return Response(401)
            return super().post(url, **kwargs)
    network = BrokenNetwork()
    monkeypatch.setattr(auth, 'Session', lambda **kw: network)
    store = m.SessionStore(tmp_path)
    store.save('OLD_FIXTURE')
    answers = iter(['fixture@example.invalid', '123456'])
    assert m.login(store, prompt=lambda label: next(answers)) == 'failed'
    assert store.read() == 'OLD_FIXTURE'
    assert 'SECRET' not in ''.join(capfd.readouterr())


def test_successful_totp_uses_sdk_cookie_extraction(monkeypatch, tmp_path, capfd):
    m = auth_module()
    from perplexity_web_mcp import auth
    class TotpNetwork(AuthNetwork):
        def get(self, url, **kwargs):
            if url.endswith('/callback-fixture'):
                return Response(302, headers={'Location': '/auth/totp-challenge?token=SECRET_CHALLENGE'})
            return super().get(url, **kwargs)
        def post(self, url, **kwargs):
            if '/totp-challenge/verify' in url:
                self.cookies['__Secure-next-auth.session-token.0'] = 'SECRET_CHUNK_'
                self.cookies['__Secure-next-auth.session-token.1'] = 'FIXTURE'
                return Response()
            return super().post(url, **kwargs)
    network = TotpNetwork()
    monkeypatch.setattr(auth, 'Session', lambda **kw: network)
    answers = iter(['fixture@example.invalid', '123456', '123456'])
    store = m.SessionStore(tmp_path)
    assert m.login(store, prompt=lambda label: next(answers)) == 'saved'
    assert store.read() == 'SECRET_CHUNK_FIXTURE'
    assert 'SECRET' not in ''.join(capfd.readouterr())


def test_fatal_totp_404_is_one_attempt_redacted_and_preserves_session(monkeypatch, tmp_path, capfd):
    m = auth_module()
    from perplexity_web_mcp import auth
    class Totp404(AuthNetwork):
        def get(self, url, **kwargs):
            if url.endswith('/callback-fixture'):
                return Response(302, headers={'Location': '/auth/totp-challenge?token=SECRET_CHALLENGE'})
            return super().get(url, **kwargs)
        def post(self, url, **kwargs):
            if '/totp-challenge/verify' in url:
                self.calls.append(('totp', url))
                print('SECRET_STDOUT')
                print('SECRET_STDERR', file=__import__('sys').stderr)
                os.write(2, b'SECRET_NATIVE_STDERR')
                return Response(404, {'error': 'SECRET_REMOTE_ERROR'})
            return super().post(url, **kwargs)
    network = Totp404()
    monkeypatch.setattr(auth, 'Session', lambda **kw: network)
    store = m.SessionStore(tmp_path)
    store.save('OLD_FIXTURE')
    answers = iter(['fixture@example.invalid', '123456', '123456'])
    assert m.login(store, prompt=lambda label: next(answers)) == 'failed'
    assert store.read() == 'OLD_FIXTURE'
    assert len([x for x in network.calls if x[0] == 'totp']) == 1
    assert network.closed
    assert 'SECRET' not in ''.join(capfd.readouterr())
