#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project.query_registry.registry import QueryRegistry  # noqa: E402
from project.settings import settings  # noqa: E402


def main() -> int:
    reg = QueryRegistry()
    try:
        reg.load_from_dir(settings.query_dir)
    except Exception as e:
        print(f"[FAIL] query validation error: {e}")
        return 1

    rows = reg.list_for_planner()
    print(f"[OK] loaded {len(rows)} queries from {settings.query_dir}")
    for r in rows:
        print(f" - {r['id']}: {r['description']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
