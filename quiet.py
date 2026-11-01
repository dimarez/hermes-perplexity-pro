"""Suppress dependency output at both Python stream and OS descriptor layers.

Use only in a dedicated sidecar, never inside the main Hermes process.
"""
import contextlib
import logging
import os
import sys


@contextlib.contextmanager
def quiet_sdk():
    os.environ.update(PWM_TRACE='0', PWM_DEBUG='0', LOG_LEVEL='DISABLED', PYTHONFAULTHANDLER='0')
    os.environ.pop('PERPLEXITY_SESSION_TOKEN', None)
    logging.disable(logging.CRITICAL)
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    try:
        with open(os.devnull, 'w') as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                yield
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for descriptor in saved:
            os.close(descriptor)
