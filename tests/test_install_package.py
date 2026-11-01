"""The default Git install tree is minimal, complete and reviewable."""
import hashlib
import importlib.util
import shutil
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def builder():
    path = ROOT / 'scripts/build_install_tree.py'
    assert path.is_file(), 'minimal native install-tree builder is missing'
    spec = importlib.util.spec_from_file_location('install_tree_builder', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_minimal_tree_has_root_manifest_and_exact_runtime_bytes(tmp_path):
    m = builder()
    output = tmp_path / 'install'
    m.build(output)
    runtime = {p.name for p in (ROOT / 'plugin').glob('*') if p.is_file()}
    expected = runtime | {'README.md', 'SECURITY.md', 'LICENSE', 'requirements-worker.lock.txt', 'SHA256SUMS'}
    assert {p.name for p in output.iterdir()} == expected
    assert all(p.is_file() and not p.is_symlink() for p in output.iterdir())
    for name in runtime:
        assert (output / name).read_bytes() == (ROOT / 'plugin' / name).read_bytes()
    for row in (output / 'SHA256SUMS').read_text().splitlines():
        digest, name = row.split('  ', 1)
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    assert 'version: 0.3.2' in (output / 'plugin.yaml').read_text()


def source_fixture(tmp_path):
    source = tmp_path / 'source'
    (source / 'docs').mkdir(parents=True)
    shutil.copytree(ROOT / 'plugin', source / 'plugin')
    for name in ('LICENSE', 'requirements-worker.lock.txt'):
        shutil.copy2(ROOT / name, source / name)
    for name in ('PLUGIN_PACKAGE_README.md', 'SECURITY.md'):
        shutil.copy2(ROOT / 'docs' / name, source / 'docs' / name)
    return source


def test_install_tree_refuses_overwriting_existing_directory(tmp_path):
    output = tmp_path / 'existing'
    output.mkdir()
    sentinel = output / 'keep'
    sentinel.write_text('original')
    with pytest.raises(FileExistsError):
        builder().build(output)
    assert sentinel.read_text() == 'original'


def test_install_tree_refuses_symlink_source_before_creating_output(tmp_path):
    source = source_fixture(tmp_path)
    target = source / 'plugin/provider.py'
    original = tmp_path / 'original.py'
    target.rename(original)
    target.symlink_to(original)
    output = tmp_path / 'install'
    with pytest.raises(ValueError, match='non-symlink'):
        builder().build(output, source=source)
    assert not output.exists()


def test_unexpected_source_files_never_enter_install_tree(tmp_path):
    source = source_fixture(tmp_path)
    (source / 'plugin/unexpected.py').write_text('sentinel')
    (source / 'plugin/.env').write_text('sentinel')
    output = tmp_path / 'install'
    builder().build(output, source=source)
    assert not (output / 'unexpected.py').exists()
    assert not (output / '.env').exists()
