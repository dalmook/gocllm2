from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .loader import load_query_files
from .validators import validate_param_type


_BIND_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")


@dataclass
class QueryDef:
    id: str
    description: str
    sql: str
    params: Dict[str, Dict[str, Any]]
    result: Dict[str, Any]
    file: str = ""


class QueryRegistry:
    def __init__(self) -> None:
        self._queries: Dict[str, QueryDef] = {}

    def load_from_dir(self, query_dir: str) -> None:
        self._queries.clear()
        for item in load_query_files(query_dir):
            q = QueryDef(
                id=item["id"],
                description=item.get("description", ""),
                sql=item["sql"],
                params=item.get("params", {}),
                result=item.get("result", {"mode": "table"}),
                file=item.get("__file__", ""),
            )
            self._validate_query(q)
            if q.id in self._queries:
                raise ValueError(f"Duplicate query id: {q.id}")
            self._queries[q.id] = q

    def list_for_planner(self) -> list[dict[str, str]]:
        return [{"id": q.id, "description": q.description} for q in self._queries.values()]

    def get(self, query_id: str) -> Optional[QueryDef]:
        return self._queries.get(query_id)

    def resolve_params(self, query_id: str, given: Dict[str, Any], *, tz: str = "Asia/Seoul") -> Dict[str, Any]:
        q = self._queries[query_id]
        result: Dict[str, Any] = {}
        for name, spec in q.params.items():
            required = bool(spec.get("required", False))
            if name in given and given[name] not in (None, ""):
                result[name] = validate_param_type(spec.get("type", "string"), given[name], tz=tz)
                continue
            if "default" in spec:
                result[name] = validate_param_type(spec.get("type", "string"), spec["default"], tz=tz)
                continue
            if required:
                alias_hint = "/".join(spec.get("aliases", []))
                raise ValueError(f"필수값 누락: {name} ({alias_hint})")
        return result

    def _validate_query(self, q: QueryDef) -> None:
        binds = set(_BIND_RE.findall(q.sql))
        param_keys = set(q.params.keys())
        if binds != param_keys:
            raise ValueError(
                f"Bind/params mismatch in {q.id}: sql={sorted(binds)} params={sorted(param_keys)} file={q.file}"
            )
