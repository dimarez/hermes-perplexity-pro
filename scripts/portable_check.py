"""Exercise the release in a fresh temporary profile and a freshly installed sidecar."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def child():
    from hermes_cli.plugins import discover_plugins
    from agent.web_search_registry import get_provider, get_active_search_provider
    from tools.web_tools import web_search_tool, _get_search_backend, _get_extract_backend
    assert not (Path.home() / '.config/perplexity-web-mcp/token').exists()
    assert 'PERPLEXITY_SESSION_TOKEN' not in os.environ
    discover_plugins()
    provider = get_provider('perplexity-pro')
    assert provider is not None, 'actual user plugin discovery did not register the provider'
    assert get_active_search_provider() is provider
    assert provider.is_available()
    assert provider.supports_search() and not provider.supports_extract()
    assert _get_search_backend() == 'perplexity-pro'
    expected_runtime = Path(os.environ['HERMES_HOME']) / 'plugin-runtimes/perplexity-pro/bin/python'
    assert provider.worker_python() == expected_runtime
    assert 'perplexity_web_mcp' not in sys.modules, 'SDK leaked into Hermes process'
    result = json.loads(web_search_tool('offline missing-session portable check', 5))
    assert result['success'] is False and '/auth:' in result['error'], result
    assert 'perplexity_web_mcp' not in sys.modules
    # Actual newly installed tool and fresh sidecar; no session means no HTTP.
    from model_tools import handle_function_call, get_tool_definitions
    import time
    definitions = get_tool_definitions(enabled_toolsets=['perplexity-pro-research'], quiet_mode=True, skip_tool_search_assembly=True)
    assert 'deep_research' in [entry['function']['name'] for entry in definitions]
    def research(arguments):
        return json.loads(handle_function_call('deep_research', arguments, session_id='portable-offline-session',
                                              enabled_toolsets=['perplexity-pro-research']))
    start = research({'action': 'start', 'query': 'offline missing-profile-session only', 'request_id': 'portable-once'})
    assert start['success'] is True, start
    job_id = start['data']['job_id']
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        research_result = research({'action': 'result', 'job_id': job_id})
        if research_result['data']['status'] == 'failed':
            break
        time.sleep(0.05)
    assert research_result['data']['code'] == 'auth', research_result
    assert 'perplexity_web_mcp' not in sys.modules
    print(json.dumps({'registration': 'real user plugin discovery', 'provider': provider.name,
        'runtime': str(expected_runtime), 'sdk_in_hermes_process': False,
        'native_dispatch': result, 'search_network_requests': 0,
        'note': 'Actual SDK subprocess in fresh empty HOME; missing session is expected, not live success.'}))


def main(archive_input=None, report_path=None):
    records = []
    # /tmp may be noexec: native SDK wheels need an executable filesystem.
    with tempfile.TemporaryDirectory(prefix='.perplexity-pro-portable-', dir=ROOT.parent) as temporary:
        base = Path(temporary)
        archive = Path(archive_input).resolve() if archive_input else base / 'release.zip'
        def run(command, env=None, cwd=None, expected=0):
            result = subprocess.run(command, text=True, capture_output=True, env=env, cwd=cwd, timeout=180)
            records.append({'command': command, 'exit_status': result.returncode,
                            'expected_exit_status': expected,
                            'stdout': result.stdout, 'stderr': result.stderr})
            if result.returncode != expected:
                raise RuntimeError('portable verification command failed: ' + json.dumps(records[-1]))
            return result
        if not archive_input:
            run([sys.executable, str(ROOT / 'scripts/build_release.py'), '--output', str(archive)])
        archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
        with zipfile.ZipFile(archive) as zipped:
            names = zipped.namelist()
            assert all('/.venv/' not in n and '__pycache__' not in n and not n.endswith('/token') for n in names)
            zipped.extractall(base / 'unpacked')
        moved = base / 'unpacked/hermes-perplexity-pro'
        profile = base / 'profile'
        plugin = profile / 'plugins/web/perplexity-pro'
        plugin.parent.mkdir(parents=True)
        shutil.copytree(moved / 'plugin', plugin)
        runtime = profile / 'plugin-runtimes/perplexity-pro'
        run(['uv', 'venv', '--python', '3.13', str(runtime)])
        run(['uv', 'pip', 'install', '--python', str(runtime / 'bin/python'),
             '-r', str(moved / 'requirements-worker.lock.txt'), '--quiet'])
        run(['uv', 'pip', 'check', '--python', str(runtime / 'bin/python')])
        home = base / 'empty-home'
        home.mkdir()
        (base / 'empty-bundled').mkdir()
        settings = {'plugins': {'enabled': []},
                    'web': {'search_backend': 'perplexity-pro', 'keyless_rescue': False,
                            'keyless_fallback': False}}
        (profile / 'config.yaml').write_text(json.dumps(settings))
        environment = os.environ.copy()
        environment.update(HOME=str(home), HERMES_HOME=str(profile),
            HERMES_BUNDLED_PLUGINS=str(base / 'empty-bundled'),
            HERMES_ENABLE_PROJECT_PLUGINS='0', PYTHONDONTWRITEBYTECODE='1')
        environment.pop('PERPLEXITY_SESSION_TOKEN', None)
        run([str(runtime / 'bin/python'), str(moved / 'scripts/check_sdk.py')], env=environment, cwd=moved)
        cli = [sys.executable, '-m', 'hermes_cli.main', '-p', 'default']
        run(cli + ['plugins', 'doctor', str(plugin), '--ci'], env=environment, cwd=moved)
        run(cli + ['plugins', 'enable', 'web/perplexity-pro'], env=environment, cwd=moved)
        # Read back the exact profile target after the real CLI config write.
        import yaml
        assert 'web/perplexity-pro' in yaml.safe_load((profile / 'config.yaml').read_text())['plugins']['enabled']
        for arguments in (['--help'], ['login', '--help'], ['status', '--help'], ['logout', '--help']):
            run(cli + ['perplexity-pro'] + arguments, env=environment, cwd=moved)
        for arguments in (['status'], ['status', '--online']):
            response = run(cli + ['perplexity-pro'] + arguments, env=environment, cwd=moved, expected=1)
            assert 'perplexity-pro/missing:' in response.stdout
        run(cli + ['perplexity-pro', 'logout'], env=environment, cwd=moved)
        run([sys.executable, str(moved / 'scripts/portable_check.py'), '--child'], env=environment, cwd=moved)
        run([sys.executable, '-m', 'pytest', '-q', 'tests', '--tb=short'], env=environment, cwd=moved)
    report = {'schema': 'portable_execution/v1', 'checks': records,
              'archive_sha256': archive_sha256,
              'production_modified': False, 'live_search_queries': 0}
    output = Path(report_path) if report_path else ROOT / 'docs/portable.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--archive', type=Path, help='Verify these exact archive bytes without rebuilding them.')
    parser.add_argument('--report', type=Path, help='Write the observed report outside the archive.')
    arguments = parser.parse_args()
    if arguments.child:
        child()
    else:
        main(arguments.archive, arguments.report)
