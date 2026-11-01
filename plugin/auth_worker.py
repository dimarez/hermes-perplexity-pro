"""Terminal-only auth UI over the pinned SDK's protocol helpers; no copied HTTP.

Executed by the profile-owned interpreter. No token-bearing SDK CLI is invoked.
"""
from __future__ import annotations

from getpass import getpass, GetPassWarning
import warnings

if __package__:
    from .session import SessionStore, StoreError, ChangeUncertain
    from .quiet import quiet_sdk
else:
    from session import SessionStore, StoreError, ChangeUncertain
    from quiet import quiet_sdk


def status(store, online=False):
    try:
        token = store.read()
        if token is None:
            return 'missing'
        if not online:
            return 'present-unchecked'
        with quiet_sdk():
            from perplexity_web_mcp.cli.auth import probe_session, SessionState
            state, _ = probe_session(token)
        return {SessionState.VALID: 'valid', SessionState.EXPIRED: 'rejected',
                SessionState.UNREACHABLE: 'unreachable'}.get(state, 'unreachable')
    except (StoreError, OSError, UnicodeError):
        return 'storage-error'
    except ImportError:
        return 'dependency'
    except Exception:
        return 'unreachable'


def hidden_prompt(label):
    # getpass may fall back to echoed stdin if terminal echo control fails.
    # Promote that warning to failure before it can read any secret input.
    with warnings.catch_warnings():
        warnings.simplefilter('error', GetPassWarning)
        return getpass(label)


def login(store, prompt=hidden_prompt):
    session = None
    try:
        with quiet_sdk():
            from perplexity_web_mcp import auth
        # Validate storage before sending a verification email; never overwrite an
        # unsafe/symlink store or invalidate the previous session on failed login.
        store.read()
        email = prompt('Perplexity email (hidden): ').strip()
        if not email:
            return 'failed'
        with quiet_sdk():
            session, csrf = auth.create_auth_session()
            auth.request_verification_code(session, csrf, email)
        code = prompt('Email verification code (hidden): ').strip()
        with quiet_sdk():
            redirect = auth.resolve_redirect_url(session, email, code)
            challenge = auth.follow_auth_callback(session, redirect)
        if challenge:
            totp = prompt('Authenticator TOTP (hidden): ').strip()
            with quiet_sdk():
                auth.verify_totp(session, challenge, totp)
        with quiet_sdk():
            token = auth.extract_session_token(session)
            store.save(token)
        return 'saved'
    except (KeyboardInterrupt, EOFError):
        return 'cancelled'
    except ChangeUncertain:
        return 'changed-unconfirmed'
    except StoreError:
        return 'storage-error'
    except ImportError:
        return 'dependency'
    except Exception:
        # SDK ValueError includes raw response bodies, including fatal TOTP 404.
        # One attempt only: no unbounded prompt loop, no advice to disable 2FA.
        return 'failed'
    finally:
        if session is not None:
            with quiet_sdk():
                try:
                    session.close()
                except Exception:
                    # Closing the HTTP handle cannot undo a committed login.
                    pass


def main():
    import os
    from pathlib import Path
    import sys
    try:
        home = os.environ.get('HERMES_HOME', '')
        if not home or not Path(home).is_absolute():
            state = 'storage-error'
        elif len(sys.argv) != 2 or sys.argv[1] not in ('login', 'status'):
            state = 'runtime-error'
        elif sys.argv[1] == 'login':
            state = login(SessionStore(Path(home))) if sys.stdin.isatty() else 'terminal-required'
        else:
            state = status(SessionStore(Path(home)), online=True)
    except (KeyboardInterrupt, EOFError):
        state = 'cancelled'
    except Exception:
        state = 'runtime-error'
    print(state)


if __name__ == '__main__':
    main()
