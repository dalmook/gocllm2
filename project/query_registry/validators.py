from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any


def normalize_yyyymm(value: Any, *, tz: str = "Asia/Seoul") -> str:
    if value is None:
        raise ValueError("yyyymm is required")
    s = str(value).strip()

    if re.fullmatch(r"\d{6}", s):
        return s

    if s in ("이번달", "이번 달", "금월"):
        return datetime.now(ZoneInfo(tz)).strftime("%Y%m")
    if s in ("지난달", "지난 달", "전월"):
        dt = datetime.now(ZoneInfo(tz))
        y, m = dt.year, dt.month - 1
        if m == 0:
            y -= 1
            m = 12
        return f"{y:04d}{m:02d}"

    month_map = {
        "1월": "01", "2월": "02", "3월": "03", "4월": "04", "5월": "05", "6월": "06",
        "7월": "07", "8월": "08", "9월": "09", "10월": "10", "11월": "11", "12월": "12",
    }
    if s in month_map:
        year = datetime.now(ZoneInfo(tz)).year
        return f"{year:04d}{month_map[s]}"

    raise ValueError(f"invalid yyyymm: {value}")


def validate_param_type(param_type: str, value: Any, *, tz: str = "Asia/Seoul") -> Any:
    t = (param_type or "string").lower()
    if t == "yyyymm":
        return normalize_yyyymm(value, tz=tz)
    if t == "int":
        return int(value)
    if t == "float":
        return float(value)
    return str(value)
