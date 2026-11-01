"""Preserve native search/auth and add one explicit asynchronous research tool."""
from .provider import PerplexityProProvider


def register(ctx) -> None:
    from tools.registry import registry
    from .research_tool import SCHEMA, handle
    import os
    import sqlite3
    from pathlib import Path
    if registry.get_entry('deep_research') is not None:
        raise RuntimeError('deep_research name collision; replacement is not allowed')
    registration = ctx.register_tool(
        name='deep_research', toolset='perplexity-pro-research', schema=SCHEMA, handler=handle,
        check_fn=lambda: (os.name == 'posix' and Path('/proc/self/fd').is_dir()
                          and all(hasattr(sqlite3.Connection, name) for name in ('serialize', 'deserialize'))),
        requires_env=[], is_async=False, description=SCHEMA['description'], emoji='🔬', override=False,
    )
    if registration is None:
        raise RuntimeError('deep_research registration was refused')
    ctx.register_web_search_provider(PerplexityProProvider())
    from .auth_cli import setup_parser, handle_args
    ctx.register_cli_command(
        name='perplexity-pro', help='Manage this profile Perplexity web session locally',
        setup_fn=setup_parser, handler_fn=handle_args,
        description='Local profile-only login/status/logout; never authenticate through chat.',
    )
