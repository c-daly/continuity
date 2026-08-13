#!/usr/bin/env python3
"""Session End Hook — continuity write-on-end trigger.

Thin trigger only: continuity (like any plugin) cannot observe session
lifecycle on its own, so this SessionEnd hook is the surface that detects
session end. The capture logic itself lives in the plugin
(``lib/session_capture.session_end_capture``); this hook just reads the
session signals, calls it, and surfaces the result via ``systemMessage``.

Claude Code discovers this via ``hooks/hooks.json`` and runs it with the
session payload on stdin.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from session_capture import session_end_capture  # noqa: E402


def main() -> None:
    """Read session signals (tolerating empty/malformed stdin) and surface the
    plugin's write-on-end capture request."""
    try:
        signals = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        signals = {}
    if not isinstance(signals, dict):
        signals = {}

    print(json.dumps({"systemMessage": session_end_capture(signals)}))


if __name__ == "__main__":
    main()
