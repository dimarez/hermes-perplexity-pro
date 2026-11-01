"""Build a minimal native Git installation tree without scanner evasions."""
import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ('__init__.py', 'auth_cli.py', 'auth_worker.py', 'plugin.yaml',
           'protocol.py', 'provider.py', 'quiet.py', 'research_jobs.py',
           'research_supervisor.py', 'research_tool.py', 'research_worker.py',
           'session.py', 'worker.py')


def build(output: Path, source: Path = ROOT) -> None:
    output = Path(output)
    source = Path(source)
    members = {name: source / 'plugin' / name for name in RUNTIME}
    members.update({'LICENSE': source / 'LICENSE',
                    'requirements-worker.lock.txt': source / 'requirements-worker.lock.txt',
                    'README.md': source / 'docs/PLUGIN_PACKAGE_README.md',
                    'SECURITY.md': source / 'docs/SECURITY.md'})
    # Validate the whole explicit input set before creating any output.
    data = {}
    for name, path in members.items():
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Install-tree source must be regular non-symlink files')
        data[name] = path.read_bytes()
    output.mkdir(parents=True, exist_ok=False)
    for name, content in data.items():
        (output / name).write_bytes(content)
    checksums = ''.join(f'{hashlib.sha256(data[name]).hexdigest()}  {name}\n' for name in sorted(data))
    (output / 'SHA256SUMS').write_text(checksums)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/install')
    args = parser.parse_args()
    build(args.output)
    print(args.output.resolve())
