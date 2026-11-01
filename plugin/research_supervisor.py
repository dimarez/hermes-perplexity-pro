"""Bound one SDK process independently of the short Hermes start/status calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

if __package__:
    from .research_jobs import JobStore, JobError, MAX_REPORT_BYTES, ERROR_CODES
else:
    from research_jobs import JobStore, JobError, MAX_REPORT_BYTES, ERROR_CODES

WORKER = Path(__file__).with_name('research_worker.py')


def child_environment(home):
    env = {name: os.environ[name] for name in ('PATH', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
                                              'REQUESTS_CA_BUNDLE', 'SYSTEMROOT') if name in os.environ}
    env.update(HOME=str(home), HERMES_HOME=str(home), PWM_TRACE='0', PWM_DEBUG='0', LOG_LEVEL='DISABLED',
               PYTHONFAULTHANDLER='0', PYTHONDONTWRITEBYTECODE='1')
    return env


def supervise(job_id):
    home = Path(os.environ.get('HERMES_HOME', ''))
    store = JobStore(home)
    try:
        job = store.claim(job_id)
        if job is None:
            return 0
        try:
            result = subprocess.run([sys.executable, str(WORKER)],
                input=json.dumps({'query': job['query'], 'timeout_seconds': job['timeout']}, ensure_ascii=False),
                text=True, encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=child_environment(home), timeout=job['timeout'], check=False)
            if result.returncode:
                payload = {'status': 'failed', 'code': 'runtime'}
            elif len(result.stdout.encode('utf-8')) > 2 * MAX_REPORT_BYTES + 100000:
                payload = {'status': 'failed', 'code': 'protocol'}
            else:
                try:
                    payload = json.loads(result.stdout)
                except ValueError:
                    payload = {'status': 'failed', 'code': 'protocol'}
        except subprocess.TimeoutExpired:
            # subprocess.run kills AND waits for this SDK child before returning.
            payload = {'status': 'failed', 'code': 'timeout'}
        except (OSError, UnicodeError):
            payload = {'status': 'failed', 'code': 'runtime'}
        try:
            store.finish(job_id, payload)
        except JobError as exc:
            code = str(exc) if str(exc) in ERROR_CODES else 'protocol'
            store.finish(job_id, {'status': 'failed', 'code': code})
        return 0
    except JobError:
        return 1


if __name__ == '__main__':
    raise SystemExit(supervise(sys.argv[1]) if len(sys.argv) == 2 else 1)
