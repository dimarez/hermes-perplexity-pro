"""Import-only sidecar diagnostic: no token store access or HTTP."""
import contextlib
import json
import os
import re
import sys


def main():
    os.environ.update(PWM_TRACE='0', PWM_DEBUG='0', LOG_LEVEL='DISABLED')
    try:
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            from perplexity_web_mcp.config import ClientConfig, ConversationConfig
            from perplexity_web_mcp.core import Perplexity, Conversation
            from perplexity_web_mcp.models import Models
            import sqlite3
            assert all(hasattr(sqlite3.Connection, name) for name in ('serialize', 'deserialize'))
            assert hasattr(Conversation, '_fetch_research_report')
        result = {'status': 'sdk_import_ok', 'model_id': Models.SONAR.identifier,
                  'research_model_id': Models.DEEP_RESEARCH.identifier,
                  'token_store_accessed': False, 'network_calls': 0}
        code = 0
    except ImportError as error:
        name = getattr(error, 'name', None)
        result = {'status': 'sdk_import_failed', 'error_type': type(error).__name__,
                  'python': sys.version,
                  'missing_module': name if isinstance(name, str) and re.fullmatch(r'[\w.]+', name) else None}
        code = 1
    except Exception:
        result, code = {'status': 'sdk_import_failed', 'error': 'Non-import failure; details withheld.'}, 1
    print(json.dumps(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
