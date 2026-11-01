"""Repeat isolated checks and record raw, non-secret test/doctor evidence."""
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    records = []
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    # No copied credentials: all tests use fixtures or an empty temporary HOME.
    with tempfile.TemporaryDirectory(prefix='perplexity-pro-check-') as temporary:
        env['HERMES_HOME'] = str(Path(temporary) / 'hermes')
        env['HOME'] = temporary
        env.update(PWM_TRACE='0', PWM_DEBUG='0', HERMES_ENABLE_PROJECT_PLUGINS='0')
        bundled = Path(temporary) / 'empty-bundled'
        bundled.mkdir()
        env['HERMES_BUNDLED_PLUGINS'] = str(bundled)
        env.pop('PERPLEXITY_SESSION_TOKEN', None)
        commands = [
            [sys.executable, '-m', 'pytest', '-q', 'tests', '--tb=short'],
            [sys.executable, '-m', 'hermes_cli.main', 'plugins', 'doctor', str(ROOT / 'plugin'), '--ci'],
            [sys.executable, '-m', 'hermes_cli.main', 'config', 'get', '--help'],
            [sys.executable, '-m', 'hermes_cli.main', 'config', 'set', '--help'],
            [sys.executable, '-m', 'hermes_cli.main', 'config', 'unset', '--help'],
            [sys.executable, '-m', 'hermes_cli.main', 'plugins', 'enable', '--help'],
            [sys.executable, '-m', 'hermes_cli.main', 'plugins', 'disable', '--help'],
            [sys.executable, '-m', 'hermes_cli.main', 'profile', '--help'],
            [str(Path(sys.executable).parent / 'pwm'), 'login', '--help'],
            [sys.executable, str(ROOT / 'scripts/check_compatibility.py'), '--help'],
            [sys.executable, str(ROOT / 'scripts/check_compatibility.py')],
            ['uv', 'pip', 'check', '--python', sys.executable],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
            record = {'command': command, 'source': str(ROOT), 'exit_status': result.returncode,
                      'stdout': result.stdout, 'observed_at': datetime.now(timezone.utc).isoformat()}
            records.append(record)
            print(result.stdout, end='')
        for folder in ('plugin', 'tests', 'scripts'):
            for path in (ROOT / folder).glob('*.py'):
                ast.parse(path.read_text(), filename=str(path))
        records.append({'command': 'ast.parse on plugin/tests/scripts *.py', 'source': str(ROOT),
                        'exit_status': 0, 'stdout': 'All Python files parsed successfully.',
                        'observed_at': datetime.now(timezone.utc).isoformat()})
    files = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
             for folder in ('plugin', 'tests', 'scripts') for p in (ROOT / folder).glob('*') if p.is_file()}
    for name in ('.gitignore', 'README.md', 'LICENSE', 'EVIDENCE.md', 'requirements-worker.txt',
                 'requirements-test.txt', 'requirements.lock.txt', 'requirements-worker.lock.txt', 'docs/SCOPE.md'):
        path = ROOT / name
        if path.is_file():
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {'schema': 'local_verification/v1', 'python': sys.version,
              'scope': 'Offline contract, actual loader/dispatcher, portable archive and dependency consistency. No live search.',
              'checks': records, 'source_sha256': files,
              'live_smoke': {'status': 'NOT_RUN_NOT_REQUESTED', 'queries_sent': 0,
                             'live_logins': 0, 'live_session_probes': 0},
              'host_installation': 'NOT_MODIFIED_NOT_VERIFIED', 'ci': 'NOT_RUN',
              'reference': {'hermes': 'f0888d77bf606ea5c96738d4deecbc0503f96bb1',
                            'sdk': 'e34b5082d6c16283358d8a1e3cbd7fa61c35fc0d'}}
    (ROOT / 'docs/verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Evidence:', ROOT / 'docs/verification.json')
    return 0 if all(r['exit_status'] == 0 for r in records) else 1


if __name__ == '__main__':
    raise SystemExit(main())
