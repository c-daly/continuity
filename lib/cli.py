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
    return 1


if __name__ == "__main__":
    sys.exit(main())
