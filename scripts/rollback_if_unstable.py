#!/usr/bin/env python3
"""Legacy wrapper for verify_and_revert.py.

Deprecated: use `verify_and_revert.py` directly.
Kept for backward compatibility with older skill installs and docs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main() -> int:
    cmd = [sys.executable, str(HERE / "verify_and_revert.py"), *sys.argv[1:]]
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
