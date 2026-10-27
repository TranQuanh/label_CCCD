"""Force UTF-8 output so Vietnamese text does not crash the Windows console."""

from __future__ import annotations

import sys


def force_utf8_output() -> None:
    # Call before logging.basicConfig: handlers capture the stream at that point.
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            # Stream replaced by another object (pytest capture, custom pipe...).
            continue
        current = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if current == "utf8":
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
