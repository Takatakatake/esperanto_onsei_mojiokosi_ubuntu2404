#!/usr/bin/env python3
"""Wrapper to run the cross-platform environment checks."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from transcriber.env_check import run_environment_check

    ready = run_environment_check()
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
