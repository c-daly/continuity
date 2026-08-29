#!/usr/bin/env python3
"""PreCompact Hook — continuity write-before-compact trigger.

Thin trigger only, mirroring ``session-end.py``: the capture logic lives in the
plugin (``lib/session_capture.pre_compact_capture``); this hook reads the
session signals, calls it, and surfaces the result via ``systemMessage``.

Why this exists alongside SessionEnd: SessionEnd is a single capture point at
the least reliable moment. A long session compacts repeatedly and may never end
cleanly, and once it has compacted the detail worth recording is already gone.
Compaction is the moment that detail is about to be lost.

Claude Code discovers this via ``hooks/hooks.json`` and runs it with the
session payload on stdin.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from session_capture import pre_compact_capture  # noqa: E402


def main() -> None:
    """Read session signals (tolerating empty/malformed stdin) and surface the
    plugin's write-before-compact capture request."""
    try:
        signals = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        signals = {}
    if not isinstance(signals, dict):
        signals = {}

    print(json.dumps({"systemMessage": pre_compact_capture(signals)}))


if __name__ == "__main__":
    main()
