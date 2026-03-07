from __future__ import annotations

from typing import Any, Dict


class ComputeTool:
    def diff(self, current: float | None, baseline: float | None) -> Dict[str, Any]:
        if current is None or baseline is None:
            return {"diff": None, "pct": None}
        d = current - baseline
        pct = (d / baseline * 100.0) if baseline else None
        return {"diff": d, "pct": pct}
