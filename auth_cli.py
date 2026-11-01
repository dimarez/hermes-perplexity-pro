"""Native Hermes CLI hook. Imports only stdlib/local code, never the SDK."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import subprocess
import sys

from hermes_constants import get_hermes_home

from .session import SessionStore, StoreError, ChangeUncertain

MESSAGES = {
    'missing': (1, 'No profile session. Run hermes perplexity-pro login with the same HERMES_HOME/profile.'),
    'present-unchecked': (0, 'Local profile session present; validity not checked. Use status --online.'),
    'valid': (0, 'Session accepted by the SDK user probe; Pro entitlement and quota not checked.'),
    'rejected': (1, 'Session rejected/expired. Run hermes perplexity-pro login with the same HERMES_HOME/profile.'),
    'unreachable': (2, 'Session check unavailable; validity is unknown. Retry status --online later.'),
    'saved': (0, 'Profile session saved privately. Use status --online to check validity.'),
    'logged-out': (0, 'Removed only this profile local session; no server revocation was requested.'),
    'already-logged-out': (0, 'No local session for this profile; no server revocation was requested.'),
    'cancelled': (130, 'Operation cancelled. Check status before assuming the session is unchanged.'),
    'failed': (2, 'Login did not finish cleanly. No automatic retry. Check status before retrying login locally; keep 2FA enabled.'),
    'changed-unconfirmed': (2, 'Local session changed, but filesystem durability is unconfirmed. Check status; do not assume the previous session remains.'),
    'storage-error': (2, 'Unsafe or unreadable profile session store; no fallback was used.'),
    'dependency': (2, 'Prepare this profile plugin-runtimes/perplexity-pro with the pinned SDK; see README.'),
    'terminal-required': (2, 'Login requires your local interactive terminal; never send codes in chat or arguments.'),
    'runtime-error': (2, 'Isolated auth operation failed; details withheld.'),
}


def setup_parser(parser):
    sub = parser.add_subparsers(dest='perplexity_action', required=True)
    sub.add_parser('login', help='Log in yourself in this local terminal (hidden email/OTP/TOTP).')
    status = sub.add_parser('status', help='Check local session presence without network.')
    status.add_argument('--online', action='store_true', help='Explicit SDK validity probe; no search, no entitlement claim.')
    sub.add_parser('logout', help='Remove only this profile local session; not a server revoke.')


def child_environment(home):
    env = os.environ.copy()
    env.pop('PERPLEXITY_SESSION_TOKEN', None)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    env.update(HERMES_HOME=str(home), PWM_TRACE='0', PWM_DEBUG='0', LOG_LEVEL='DISABLED',
               PYTHONFAULTHANDLER='0', PYTHONDONTWRITEBYTECODE='1')
    return env


def local_operation(home, action):
    store = SessionStore(home)
    if action == 'logout':
        return 'logged-out' if store.logout() else 'already-logged-out'
    return 'present-unchecked' if store.read() is not None else 'missing'


@contextlib.contextmanager
def preserve_terminal():
    """Restore the getpass TTY even if a timed-out child is killed with SIGKILL."""
    import termios
    try:
        descriptor = os.open('/dev/tty', os.O_RDWR | os.O_NOCTTY)
    except OSError:
        # Same fallback terminal as getpass when there is no controlling TTY.
        descriptor = os.dup(sys.stdin.fileno())
    try:
        attributes = termios.tcgetattr(descriptor)
        try:
            yield
        finally:
            # Discard pending secret input as well as restoring echo.
            termios.tcsetattr(descriptor, termios.TCSAFLUSH, attributes)
    finally:
        os.close(descriptor)


def run_action(action, online=False):
    home = get_hermes_home()
    try:
        if action == 'login' and not sys.stdin.isatty():
            state = 'terminal-required'
        elif action == 'logout' or (action == 'status' and not online):
            state = local_operation(home, action)
        elif action == 'status' and local_operation(home, action) == 'missing':
            # Missing is a local fact even without the optional SDK interpreter.
            state = 'missing'
        else:
            python = home / 'plugin-runtimes/perplexity-pro/bin/python'
            with preserve_terminal() if action == 'login' else contextlib.nullcontext():
                result = subprocess.run([str(python), str(Path(__file__).with_name('auth_worker.py')), action],
                                        env=child_environment(home), text=True, encoding='utf-8',
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        timeout=600 if action == 'login' else 45, check=False)
            state = result.stdout.strip() if result.returncode == 0 else 'runtime-error'
            # Do not reflect arbitrary child output (including remote bodies).
            if state not in MESSAGES:
                state = 'runtime-error'
    except (KeyboardInterrupt, EOFError):
        state = 'cancelled'
    except FileNotFoundError:
        state = 'dependency'
    except subprocess.TimeoutExpired:
        state = 'unreachable' if action == 'status' else 'failed'
    except ChangeUncertain:
        state = 'changed-unconfirmed'
    except (StoreError, OSError, UnicodeError):
        state = 'storage-error'
    except Exception:
        state = 'runtime-error'
    code, message = MESSAGES[state]
    print(f'perplexity-pro/{state}: {message}')
    return code


def handle_args(args):
    raise SystemExit(run_action(args.perplexity_action, getattr(args, 'online', False)))
