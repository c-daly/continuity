"""continuity CLI — minimal entry point for shell callers.

For hooks, scripts, and debugging. Mirrors the MCP server's tool surface
in command-line form so callers without an MCP client can still invoke
continuity capabilities.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from record_insight import record_insight  # noqa: E402
from resume_brief import resume_brief  # noqa: E402
from synthesis_pass import run_synthesis  # noqa: E402


def cmd_synthesize(argv, deps=None) -> int:
    """Run the synthesis pass: cluster observations, draft and write promotions.

    Wires real providers by default; `deps` lets tests inject fakes.
    """
    try:
        if deps is None:
            from memory_read_provider import MemoryReadProvider
            from vault_write_provider import VaultWriteProvider
            from vault_provider import VaultProvider
            from promotion import PromotionStore
            from llm_synthesis import ClaudeCliRunner, LLMClusterer, LLMDrafter

            vault_path = VaultProvider().vault_path
            runner = ClaudeCliRunner()
            deps = dict(reader=MemoryReadProvider(),
                        writer=VaultWriteProvider(vault_path=vault_path),
                        store=PromotionStore(vault_path),
                        clusterer=LLMClusterer(runner), drafter=LLMDrafter(runner),
                        vault_path=vault_path, today=None)

        res = run_synthesis(**deps)
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"synthesis: written {len(res.written)}, skipped {len(res.skipped)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="continuity",
        description="Cross-project surfacing and meta-concerns curation",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    rb = sub.add_parser(
        "resume-brief",
        help="Compose a session-start resume brief for a project",
    )
    rb.add_argument(
        "project",
        help="Project name (basename under <vault>/10-projects/)",
    )

    ri = sub.add_parser(
        "record-insight",
        help="Write a project-scoped insight (body read from stdin)",
    )
    ri.add_argument("--project", required=True, help="Project name")
    ri.add_argument("--title", required=True, help="Insight title")

    sub.add_parser(
        "synthesize",
        help="Run the synthesis pass: cluster observations, draft and write promotions",
    )

    args = parser.parse_args()

    if args.cmd == "resume-brief":
        print(resume_brief(args.project))
        return 0
    if args.cmd == "record-insight":
        body = sys.stdin.read()
        try:
            ref = record_insight(project=args.project, title=args.title, body=body)
        except (RuntimeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(ref)
        return 0
    if args.cmd == "synthesize":
        return cmd_synthesize([])
    return 1


if __name__ == "__main__":
    sys.exit(main())
