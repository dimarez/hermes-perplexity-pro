"""Actual native tool dispatch and detached local pipeline with synthetic output."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import pytest
from test_provider import PLUGIN


def test_native_async_pipeline_saves_full_report_and_cleans_process(monkeypatch, tmp_path):
    from hermes_cli.plugin_dev import _doctor_runtime
    from tools.registry import registry
    report = '# OFFLINE PIPELINE FIXTURE\n' + 'x' * 5000
    child = tmp_path / 'synthetic_sdk.py'
    child.write_text('import json, sys\nrequest=json.load(sys.stdin)\nprint(json.dumps(' + repr({
        'status': 'completed', 'full_report': True, 'report': report,
        'sources': [{'title': 'Fixture source', 'url': 'https://example.org/'}]}) + '))\n')
    bridge = tmp_path / 'synthetic_runtime.py'
    bridge.write_text('import sys\nsys.path.insert(0,' + repr(str(PLUGIN)) + ')\n'
        'import research_supervisor as s\nfrom pathlib import Path\ns.WORKER=Path(' + repr(str(child)) + ')\n'
        'raise SystemExit(s.supervise(sys.argv[2]))\n')
    processes = []
    with tempfile.TemporaryDirectory(prefix='.research-fixture-', dir=Path(sys.prefix)) as executable_dir, _doctor_runtime(PLUGIN):
        # Doctor/unpacked source /tmp may be noexec. Use the standalone test venv
        # filesystem for the synthetic executable, not the relocated source tree.
        home = Path(os.environ['HERMES_HOME'])
        runtime = home / 'plugin-runtimes/perplexity-pro/bin/python'
        runtime.parent.mkdir(parents=True)
        wrapper = Path(executable_dir) / 'python'
        import shlex
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(str(sys.executable)) + ' ' + shlex.quote(str(bridge)) + ' "$@"\n')
        wrapper.chmod(0o700)
        runtime.symlink_to(wrapper)
        entry = registry.get_entry('deep_research')
        original = entry.handler.__globals__['subprocess'].Popen
        def capture(*args, **kwargs):
            try:
                process = original(*args, **kwargs)
            except OSError as exc:
                pytest.fail('Synthetic runtime launch failed: ' + repr(exc))
            processes.append(process)
            return process
        monkeypatch.setattr(entry.handler.__globals__['subprocess'], 'Popen', capture)
        from model_tools import get_tool_definitions, handle_function_call
        definitions = get_tool_definitions(enabled_toolsets=['perplexity-pro-research'], quiet_mode=True, skip_tool_search_assembly=True)
        assert [d['function']['name'] for d in definitions] == ['deep_research']
        def call(arguments, session='fixture-session'):
            return json.loads(handle_function_call('deep_research', arguments, session_id=session,
                                                  enabled_toolsets=['perplexity-pro-research']))
        response = call({'action': 'start', 'query': 'synthetic local pipeline', 'request_id': 'pipeline-once'})
        assert response['success'] is True, response
        job_id = response['data']['job_id']
        try:
            # Bounded test harness watcher, not model polling or a production scheduler.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                result = call({'action': 'result', 'job_id': job_id})
                if result['data']['status'] == 'completed':
                    break
                time.sleep(0.05)
            assert result['data']['status'] == 'completed', result
            assert result['data']['full_report'] is True and result['data']['truncated'] is True
            assert len(result['data']['preview']) == 4000
            assert Path(result['data']['report_path']).read_text() == report
            assert call({'action': 'result', 'job_id': job_id}, session='foreign')['code'] == 'not_found'
            repeated = call({'action': 'start', 'query': 'synthetic local pipeline', 'request_id': 'pipeline-once'})
            assert repeated['data']['job_id'] == job_id and repeated['data']['created'] is False
            assert len(processes) == 1
        finally:
            for process in processes:
                try:
                    process.wait(timeout=5)
                except Exception:
                    process.kill()
                    process.wait(timeout=5)
                    raise
        assert all(process.returncode == 0 for process in processes)


def test_native_research_availability_does_not_probe_process_filesystem(monkeypatch):
    from hermes_cli.plugin_dev import _doctor_runtime
    from tools.registry import registry
    original = Path.is_dir
    process_path_checks = []
    def without_process_filesystem(path):
        if path.parts[:2] == ('/', 'proc'):
            process_path_checks.append(str(path))
            return False
        return original(path)
    monkeypatch.setattr(Path, 'is_dir', without_process_filesystem)
    with _doctor_runtime(PLUGIN):
        entry = registry.get_entry('deep_research')
        assert entry is not None and entry.check_fn() is True
    assert process_path_checks == []


@pytest.mark.parametrize('toolset', ['perplexity-pro-research', 'foreign-research'])
def test_real_plugin_refuses_occupied_name_even_in_same_toolset(toolset):
    from hermes_cli.plugin_dev import doctor_plugin
    from tools.registry import registry
    assert registry.get_entry('deep_research') is None
    handler = lambda args: '{"fixture":true}'
    registry.register('deep_research', toolset, {'name': 'deep_research', 'parameters': {}}, handler)
    previous = registry.get_entry('deep_research')
    try:
        report = doctor_plugin(PLUGIN)
        assert not report.ok
        assert registry.get_entry('deep_research') is previous
    finally:
        registry.deregister('deep_research')
