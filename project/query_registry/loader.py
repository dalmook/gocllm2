from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List


def load_query_files(query_dir: str) -> List[Dict[str, Any]]:
    p = Path(query_dir)
    if not p.exists():
        return []

    items: List[Dict[str, Any]] = []
    for fp in sorted(p.glob("*.yml")) + sorted(p.glob("*.yaml")) + sorted(p.glob("*.json")):
        if fp.suffix in (".yml", ".yaml"):
            try:
                import yaml  # type: ignore
            except Exception:
                # PyYAML 미설치 시 YAML은 건너뛰고 JSON만 로드
                continue
            data = yaml.safe_load(fp.read_text(encoding="utf-8"))
        else:
            import json
            data = json.loads(fp.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid query file format: {fp}")
        data["__file__"] = str(fp)
        items.append(data)
    return items
