"""Verify final archive integrity/readback and write downloadable checksum manifests."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    from build_release import VERSION
    release = ROOT / f'dist/hermes-perplexity-pro-{VERSION}.zip'
    digest = hashlib.sha256(release.read_bytes()).hexdigest()
    report = json.loads((ROOT / 'dist/verification-final.json').read_text())
    assert report['archive_sha256'] == digest
    assert report['live_search_queries'] == 0
    assert report['checks'] and all(check['exit_status'] == check.get('expected_exit_status', 0)
                                    for check in report['checks'])
    rows = []
    with zipfile.ZipFile(release) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == len(set(names))
        for name in sorted(names):
            path = Path(name)
            assert path.parts[0] == 'hermes-perplexity-pro' and '..' not in path.parts
            assert not any(part in ('.venv', '__pycache__', '.git', 'token', '.env') for part in path.parts)
            relative = Path(*path.parts[1:])
            data = archive.read(name)
            assert data == (ROOT / relative).read_bytes(), f'archive/source drift: {relative}'
            rows.append(f'{hashlib.sha256(data).hexdigest()}  {name}')
        evidence = json.loads(archive.read('hermes-perplexity-pro/docs/verification.json'))
        for name, expected in evidence['source_sha256'].items():
            assert hashlib.sha256(archive.read('hermes-perplexity-pro/' + name)).hexdigest() == expected, name
    (ROOT / 'dist/MANIFEST.sha256').write_text('\n'.join(rows) + '\n')
    (ROOT / 'dist/SHA256SUMS').write_text(f'{digest}  {release.name}\n')
    print(json.dumps({'archive': str(release), 'sha256': digest, 'files': len(rows),
        'archive_tested_exactly': True, 'source_readback_matches': True,
        'checksums': ['dist/MANIFEST.sha256', 'dist/SHA256SUMS']}, indent=2))


if __name__ == '__main__':
    main()
