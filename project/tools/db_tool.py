from __future__ import annotations

from typing import Any, Dict

import oracledb
import pandas as pd

from ..settings import settings
from ..query_registry.registry import QueryRegistry


class DBTool:
    def __init__(self, registry: QueryRegistry):
        self.registry = registry

    def _dsn(self) -> str:
        if settings.oracle_dsn:
            return settings.oracle_dsn
        return oracledb.makedsn(settings.oracle_host, settings.oracle_port, service_name=settings.oracle_service)

    def query(self, query_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        q = self.registry.get(query_id)
        if not q:
            raise ValueError(f"unknown query_id: {query_id}")

        safe_params = self.registry.resolve_params(query_id, params, tz=settings.timezone)
        with oracledb.connect(user=settings.oracle_user, password=settings.oracle_password, dsn=self._dsn()) as conn:
            with conn.cursor() as cur:
                cur.execute(q.sql, safe_params)
                rows = cur.fetchall()
                cols = [d[0].lower() for d in cur.description]

        df = pd.DataFrame(rows, columns=cols)
        mode = (q.result or {}).get("mode", "table")

        if mode == "scalar":
            field = (q.result or {}).get("field", "")
            if df.empty:
                return {
                    "query_id": query_id,
                    "params": safe_params,
                    "mode": "scalar",
                    "value": None,
                    "rowcount": 0,
                    "empty_message": (q.result or {}).get("empty_message", "조회 결과가 없습니다."),
                }
            return {
                "query_id": query_id,
                "params": safe_params,
                "mode": "scalar",
                "value": df.iloc[0][field.lower()] if field.lower() in df.columns else None,
                "rowcount": len(df),
            }

        return {
            "query_id": query_id,
            "params": safe_params,
            "mode": "table",
            "rows": df.to_dict(orient="records"),
            "rowcount": len(df),
        }
