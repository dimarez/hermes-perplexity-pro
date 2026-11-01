"""Read-only compatibility check; --live sends ONE public native web_search query."""
import argparse
import json


def check(live=False):
    try:
        from agent.web_search_provider import WebSearchProvider
        from hermes_cli.plugins import PluginContext, discover_plugins
        from agent.web_search_registry import get_active_search_provider
        from hermes_cli.config import load_config_readonly
        from tools.web_tools import _get_search_backend, web_search_tool
        assert hasattr(PluginContext, 'register_web_search_provider')
        assert hasattr(PluginContext, 'register_cli_command')
        assert hasattr(PluginContext, 'register_tool')
    except (ImportError, AttributeError, AssertionError):
        return 1, {'status': 'incompatible', 'error': 'Required Hermes web-provider APIs are unavailable.'}
    if not live:
        return 0, {'status': 'provider_api_available', 'session_validated': False,
                   'live_queries_sent': 0, 'note': 'Compatibility only; not installed/routed/authenticated evidence.'}
    discover_plugins()
    provider = get_active_search_provider()
    if provider is None or provider.name != 'perplexity-pro' or _get_search_backend() != 'perplexity-pro':
        return 1, {'status': 'wrong_route', 'error': 'Client-side perplexity-pro is not the active registered search backend.'}
    if not provider.is_available():
        return 1, {'status': 'runtime_missing', 'error': 'Prepare the profile-owned SDK runtime first.'}
    if (load_config_readonly().get('web') or {}).get('keyless_rescue', True) is not False:
        return 1, {'status': 'rescue_enabled', 'error': 'Disable web.keyless_rescue deliberately for a strict routing smoke test; restore its saved value afterwards.'}
    response = json.loads(web_search_tool('What is the official Python documentation website?', 2))
    if response.get('success') is not True:
        return 1, {'status': 'live_failed', 'client_backend': provider.name, 'search_calls': 1,
                   'error': 'The selected backend returned a failure; this is not a successful live search.'}
    return 0, {'status': 'live_ok', 'client_backend': provider.name, 'search_calls': 1,
               'data': response.get('data'), 'warning': 'Success does not establish Pro entitlement or remaining quota.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Send one fixed public web_search query; may consume Pro quota.')
    args = parser.parse_args()
    try:
        code, result = check(args.live)
    except Exception:
        code, result = 1, {'status': 'check_failed', 'error': 'Compatibility/routing check failed; raw exception withheld.'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
