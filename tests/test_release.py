"""Release is portable and may be checked away from the development directory."""
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_portable_release(tmp_path):
    script = ROOT / 'scripts/build_release.py'
    assert script.is_file(), 'release builder is not implemented'
    output = tmp_path / 'release.zip'
    subprocess.run([sys.executable, str(script), '--output', str(output)], check=True)
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert all('.venv/' not in n and '__pycache__/' not in n and '/token' not in n for n in names)
        assert 'hermes-perplexity-pro/plugin/plugin.yaml' in names
        assert 'hermes-perplexity-pro/README.md' in names
        assert not any('/dr01/' in n or '/extra-deps/' in n or '__pycache__' in n for n in names)
        archive.extractall(tmp_path / 'unpacked')
    moved = tmp_path / 'unpacked/hermes-perplexity-pro'
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '-q', 'tests', '--ignore=tests/test_release.py', '--tb=short'],
        cwd=moved, env=os.environ.copy(), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
    )
    assert result.returncode == 0, result.stdout
    assert 'passed' in result.stdout and 'failed' not in result.stdout
