"""The MCP server's exposed surface.

`run_synthesis` shipped reachable only from the CLI — no hook, no MCP tool, not
in cron — so the pass existed and never ran. This pins the tool being exposed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))


def _server_source() -> str:
    return (Path(__file__).resolve().parent.parent / "lib" / "server.py").read_text()


def test_synthesize_is_exposed_as_a_tool():
    src = _server_source()
    assert "def synthesize(" in src
    decorated = src.split("def synthesize(")[0].rstrip().endswith("@mcp.tool()")
    assert decorated, "synthesize must carry @mcp.tool()"


def test_synthesize_uses_the_shared_dependency_wiring():
    """Not a second copy of the provider wiring — the CLI and the tool must run
    the same pass, or they diverge silently."""
    src = _server_source()
    assert "_default_synthesis_deps()" in src
    assert "ClaudeCliRunner" not in src, "server should not re-wire providers itself"


def test_cli_uses_the_same_shared_wiring():
    cli_src = (Path(__file__).resolve().parent.parent / "lib" / "cli.py").read_text()
    assert "default_synthesis_deps()" in cli_src
    assert "ClaudeCliRunner" not in cli_src


def test_default_synthesis_deps_supplies_every_run_synthesis_argument():
    import inspect
    from synthesis_pass import default_synthesis_deps, run_synthesis

    required = {
        name for name, p in inspect.signature(run_synthesis).parameters.items()
        if p.default is inspect.Parameter.empty
    }
    src = inspect.getsource(default_synthesis_deps)
    for name in required:
        assert f"{name}=" in src, f"default_synthesis_deps omits {name}"
