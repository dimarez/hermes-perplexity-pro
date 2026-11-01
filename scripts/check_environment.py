"""Metadata-only environment/session probe: never opens a credential file."""
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil

ROOT = Path(__file__).resolve().parents[1]


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def main():
    # Only existence and key membership, NOT values, file length or token validity.
    presence = {
        'standard_token_file_exists': (Path.home() / '.config/perplexity-web-mcp/token').is_file(),
        'session_env_key_present': 'PERPLEXITY_SESSION_TOKEN' in os.environ,
        'credentials_opened_by_probe': False,
        'authentication_validated': False,
        'live_queries_sent': 0,
    }
    sdk = metadata.distribution('perplexity-web-mcp-cli')
    source = json.loads(sdk.read_text('direct_url.json'))
    result = {
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'os': platform.freedesktop_os_release().get('PRETTY_NAME', platform.system()),
        'python': platform.python_version(),
        'hermes_cli_in_path': shutil.which('hermes') is not None,
        'host_installation_verification': 'UNAVAILABLE_FROM_THIS_DOCKER_RUNTIME',
        'sdk': {'version': sdk.version, 'public_source': source},
        'session_presence_only': presence,
        'mount_mapping': '/home/hermes/Develop -> /workspace/develop (from /proc/self/mountinfo)',
        'public_docs': [],
    }
    for name, url in (
        ('provider-page.html', 'https://hermes-agent.nousresearch.com/docs/developer-guide/web-search-provider-plugin'),
        ('plugins-page.html', 'https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/'),
    ):
        path = ROOT / 'docs' / name
        if not path.is_file():
            continue
        parser = PageText()
        parser.feed(path.read_text())
        text = '\n'.join(p.strip() for p in parser.parts if p.strip())
        excerpts = {}
        for term in ('register_web_search_provider', 'python_runtime', 'Direct-URL', 'web.search_backend'):
            index = text.find(term)
            if index >= 0:
                excerpts[term] = text[max(0, index - 80):index + 800]
        result['public_docs'].append({'url': url, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                      'contract_excerpts': excerpts})
    (ROOT / 'docs/environment.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
