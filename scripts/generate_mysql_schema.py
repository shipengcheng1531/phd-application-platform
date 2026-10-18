#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PLATFORM_ROOT))

import server  # noqa: E402


def main() -> None:
    sys.stdout.write(server.mysql_schema_sql())


if __name__ == "__main__":
    main()
