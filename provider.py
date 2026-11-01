"""Hermes search-only backend; keep the unofficial SDK out of the host process."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from urllib.parse import urlsplit

from agent.web_search_provider import WebSearchProvider
from hermes_constants import get_hermes_home

from .protocol import ERRORS, failure, valid_input


class PerplexityProProvider(WebSearchProvider):
    @property
    def name(self) -> str:
        return 'perplexity-pro'

    @property
    def display_name(self) -> str:
        return 'Perplexity Pro (unofficial web session)'

    def worker_python(self) -> Path:
        """Sidecar interpreter, deliberately independent of the Hermes PM environment."""
        relative = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
        return get_hermes_home() / 'plugin-runtimes' / 'perplexity-pro' / relative

    def is_available(self) -> bool:
        # Interpreter readiness only: no SDK imports, auth/network/quota probes.
        return self.worker_python().is_file()

    def search(self, query: str, limit: int = 5) -> dict:
        if not valid_input(query, limit):
            return failure('input')
        env = os.environ.copy()
        env.pop('PERPLEXITY_SESSION_TOKEN', None)
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        env.update(HERMES_HOME=str(get_hermes_home()), PWM_TRACE='0', PWM_DEBUG='0', LOG_LEVEL='DISABLED',
                   PYTHONFAULTHANDLER='0', PYTHONDONTWRITEBYTECODE='1')
        try:
            result = subprocess.run(
                [str(self.worker_python()), str(Path(__file__).with_name('worker.py'))],
                input=json.dumps({'query': query, 'limit': limit}),
                text=True, encoding='utf-8', stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=env, timeout=90, check=False,
            )
        except subprocess.TimeoutExpired:
            return failure('timeout')
        except FileNotFoundError:
            return failure('dependency')
        except (OSError, UnicodeError):
            return failure('runtime')
        if result.returncode != 0:
            return failure('runtime')
        try:
            response = json.loads(result.stdout)
        except (ValueError, TypeError):
            return failure('protocol')
        if not isinstance(response, dict):
            return failure('protocol')
        if response.get('success') is False:
            # Only messages from our static vocabulary may cross this boundary.
            for code in ERRORS:
                if response == failure(code):
                    return failure(code)
            return failure('protocol')
        data = response.get('data')
        if response.get('success') is not True or not isinstance(data, dict) or not isinstance(data.get('web'), list):
            return failure('protocol')
        rows = []
        for row in data['web'][:limit]:
            if not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in ('title', 'url', 'description')):
                return failure('protocol')
            if type(row.get('position')) is not int or row['position'] < 1:
                return failure('protocol')
            try:
                url = urlsplit(row['url'])
                if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
                    return failure('protocol')
            except ValueError:
                return failure('protocol')
            rows.append({k: row[k] for k in ('title', 'url', 'description', 'position')})
        return {'success': True, 'data': {'web': rows}}
