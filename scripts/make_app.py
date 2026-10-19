#!/usr/bin/env python3
"""Build Kuulas.app (macOS launcher for .kuulas folders, WP72 step 1).

    uv run python scripts/make_app.py --dry-run        # print the plan
    uv run python scripts/make_app.py                  # build + register
    uv run python scripts/make_app.py --into DIR --no-register

Undo the registration: lsregister -u ~/Applications/Kuulas.app (see docs/desktop.md).
"""

from __future__ import annotations

import sys

from kuulas.macapp import build_main

if __name__ == "__main__":
    sys.exit(build_main())
