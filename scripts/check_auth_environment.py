"""Record public contracts, mounts and baseline drift; never inspect credentials."""
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SDK_COMMIT = 'e34b5082d6c16283358d8a1e3cbd7fa61c35fc0d'
HERMES_COMMIT = 'f0888d77bf606ea5c96738d4deecbc0503f96bb1'


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, text):
        self.parts.append(text)


def main():
    refs = {}
    for name, expected in [('hermes-agent-reference', HERMES_COMMIT), ('perplexity-web-mcp', SDK_COMMIT)]:
        path = ROOT.parent / name
        commit = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        status = subprocess.check_output(['git', '-C', str(path), 'status', '--short'], text=True)
        assert commit == expected and not status
        refs[name] = {'commit': commit, 'tracked_sources_clean': True}
    sdk = metadata.distribution('perplexity-web-mcp-cli')
    commit = json.loads(sdk.read_text('direct_url.json'))['vcs_info']['commit_id']
    assert sdk.version == '0.16.1' and commit == SDK_COMMIT
    page = ROOT / 'docs/plugins-auth-page.html'
    parser = Text()
    parser.feed(page.read_text())
    text = '\n'.join(part.strip() for part in parser.parts if part.strip())
    index = text.index('ctx.register_cli_command()')
    baseline = ROOT / 'dist/hermes-perplexity-pro-0.1.0.zip'
    changes = []
    with zipfile.ZipFile(baseline) as archive:
        previous = {n.removeprefix('hermes-perplexity-pro/'): hashlib.sha256(archive.read(n)).hexdigest()
                    for n in archive.namelist()}
    for folder in ['plugin', 'tests', 'scripts']:
        for path in sorted((ROOT / folder).glob('*.py')):
            relative = str(path.relative_to(ROOT))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != previous.get(relative):
                changes.append({'path': relative, 'change': 'modified' if relative in previous else 'added'})
    mounts = [line for line in Path('/proc/self/mountinfo').read_text().splitlines()
              if '/workspace/develop' in line]
    assert mounts, 'Develop mount missing'
    report = {'schema': 'auth_contract_environment/v1', 'observed_at': datetime.now(timezone.utc).isoformat(),
        'python': platform.python_version(), 'os': platform.freedesktop_os_release()['PRETTY_NAME'],
        'mounts': mounts, 'references': refs,
        'sdk': {'version': sdk.version, 'commit': commit},
        'baseline_archive_sha256': hashlib.sha256(baseline.read_bytes()).hexdigest(),
        'changes_from_0_1_0': changes,
        'official_contract': {'url': 'https://hermes-agent.nousresearch.com/docs/developer-guide/plugins',
            'page_sha256': hashlib.sha256(page.read_bytes()).hexdigest(),
            'excerpt': text[index:index + 300]},
        'decision': 'Supported native CLI hook reused; no standalone launcher or copied auth protocol.',
        'real_credentials_read_or_copied': False, 'production_modified': False,
        'live_logins': 0, 'live_session_probes': 0, 'live_searches': 0}
    output = ROOT / 'docs/auth-environment.json'
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
